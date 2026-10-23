"""
Script para poblar datos realistas de ventas en Panadería Amada.
Genera un historial completo de facturas, detalles de venta, pagos,
asientos contables, encargos y bitácora fiscal en los últimos 30 días,
incluyendo ventas del día de hoy para visualización en vivo del Dashboard y Reportes.
"""

import os
import sys
import random
import uuid
import json
from decimal import Decimal
from datetime import datetime, date, timedelta

# Asegurar que el entorno Flask se cargue correctamente
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from app import create_app
from app.db import get_db_connection
from app.services.contabilidad_service import ContabilidadService, amount
from app.services.fiscal_service import next_invoice, configuration, audit
from app.utils.qr import generar_qr_base64


def poblar_ventas():
    app = create_app()

    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor()

        print("=== Iniciando población de datos de ventas ===")

        # 1. Obtener configuración fiscal
        config = configuration(cursor)
        serie = config.get('fiscal_serie', 'FAC')
        tipo_cambio_usd = Decimal(config.get('tipo_cambio_usd', '36.62'))

        # 2. Asegurar clientes adicionales realistas en CRM
        clientes_muestra = [
            ('Carlos Mendoza', '88776655'),
            ('Sofía Gutiérrez', '84992211'),
            ('Roberto Díaz', '87654321'),
            ('Elena Martínez', '83332211')
        ]
        for nombre, tel in clientes_muestra:
            cursor.execute("SELECT ID FROM crm.Clientes WHERE Telefono = ?", tel)
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO crm.Clientes (Nombre, Telefono, NivelConfianzaID, TotalCompras, CreadoEn)
                    VALUES (?, ?, 1, 0, DATEADD(DAY, -40, GETDATE()))
                """, nombre, tel)

        # Cargar todos los clientes
        cursor.execute("SELECT ID, Nombre, Telefono FROM crm.Clientes")
        clientes_db = cursor.fetchall()
        cliente_mostrador_id = 1
        clientes_registrados = [c for c in clientes_db if c.ID != cliente_mostrador_id]

        # 3. Obtener usuarios cajeros / vendedores
        cursor.execute("SELECT ID, Username FROM seguridad.Usuarios WHERE RolID IN (1, 2, 3)")
        usuarios_vendedores = [r.ID for r in cursor.fetchall()]
        if not usuarios_vendedores:
            usuarios_vendedores = [1]

        # 4. Obtener productos activos por categoría
        cursor.execute("""
            SELECT ID, Nombre, PrecioBase, CategoriaID 
            FROM catalogo.Productos 
            WHERE Activo = 1
        """)
        productos_todos = cursor.fetchall()
        prod_map = {p.ID: p for p in productos_todos}

        # Separar por tipo para construir canastas realistas
        # IDs conocidos:
        # 1: Bolillo (C$ 5)
        # 2: Pan Pizza (C$ 15)
        # 3: Galleta de Jamon (C$ 8)
        # 4: Panuelito (C$ 10)
        # 5: Concha de Vainilla (C$ 12)
        # 6: Dona de Chocolate (C$ 10)
        # 7: Milanesa (C$ 25)
        # 8: Cafe Americano (C$ 20)
        # 9: Gaseosa (C$ 15)
        # 10: Pastel Tres Leches (1 Lb) (C$ 350)
        # 11: Pastel de Chocolate (1 Lb) (C$ 400)
        # 13: Selva Negra (C$ 380)
        prods_pan = [p for p in productos_todos if p.ID in (1, 4, 5, 6, 7)]
        prods_salados = [p for p in productos_todos if p.ID in (2, 3, 7)]
        prods_bebidas = [p for p in productos_todos if p.ID in (8, 9)]
        prods_pasteles = [p for p in productos_todos if p.ID in (10, 11, 13)]

        # Turno 1 es la caja activa principal
        turno_id = 1

        # 5. Generar calendario de ventas de los últimos 30 días
        fecha_actual = datetime.now()
        hoy = fecha_actual.date()
        fechas_simuladas = []

        # Para los últimos 29 días (hace 29 días hasta ayer)
        for dias_atras in range(29, 0, -1):
            dia = hoy - timedelta(days=dias_atras)
            es_fin_de_semana = dia.weekday() in (5, 6) # Sábado o Domingo
            # 2 a 3 ventas por día de semana, 4 a 6 ventas en fin de semana
            num_ventas = random.randint(4, 6) if es_fin_de_semana else random.randint(2, 4)

            for _ in range(num_ventas):
                # Distribuir en horas pico: mañana (7-10), mediodía (12-14), tarde (15-18)
                franja = random.choices(['manana', 'mediodia', 'tarde'], weights=[0.4, 0.25, 0.35])[0]
                if franja == 'manana':
                    hora = random.randint(7, 10)
                elif franja == 'mediodia':
                    hora = random.randint(12, 14)
                else:
                    hora = random.randint(15, 18)
                minuto = random.randint(0, 59)
                segundo = random.randint(0, 59)
                fechas_simuladas.append(datetime(dia.year, dia.month, dia.day, hora, minuto, segundo))

        # Para hoy (ventas frescas para el dashboard)
        # Horas anteriores a la hora actual
        hora_actual = min(fecha_actual.hour, 18)
        num_ventas_hoy = 8
        for _ in range(num_ventas_hoy):
            hora = random.randint(7, max(8, hora_actual))
            minuto = random.randint(0, 59)
            segundo = random.randint(0, 59)
            fechas_simuladas.append(datetime(hoy.year, hoy.month, hoy.day, hora, minuto, segundo))

        # Ordenar cronológicamente
        fechas_simuladas.sort()

        print(f"Total de facturas a generar: {len(fechas_simuladas)} distribuidas en los últimos 30 días.")

        facturas_insertadas = 0
        total_monto_ventas = Decimal('0.00')

        notas_encargos = [
            'Feliz Cumpleaños Mamá con decorado floral',
            'Dedicatoria: Felicidades Graduado Roberto',
            'Decoración temática infantil Spider-Man',
            'Pastel de aniversario 10 años, letras doradas',
            'Sin merengue excesivo, con extra chocolate y cerezas',
            'Pastel Tres Leches húmedo tradicional para bautizo'
        ]

        for fecha_venta in fechas_simuladas:
            # Determinar tipo de venta:
            # 85% venta normal mostrador, 15% venta de pastel/encargo
            es_encargo_prob = random.random() < 0.15
            usuario_id = random.choice(usuarios_vendedores)

            # Cliente
            if es_encargo_prob and clientes_registrados:
                cliente_obj = random.choice(clientes_registrados)
                cliente_id = cliente_obj.ID
                es_encargo = True
            else:
                # 75% mostrador general, 25% cliente registrado
                if random.random() < 0.25 and clientes_registrados:
                    cliente_obj = random.choice(clientes_registrados)
                    cliente_id = cliente_obj.ID
                else:
                    cliente_id = cliente_mostrador_id
                es_encargo = False

            # Generar Carrito de Productos
            carrito = []
            if es_encargo:
                # Venta con pastel principal
                pastel = random.choice(prods_pasteles)
                cant = 1
                precio = pastel.PrecioBase
                sub = precio * cant
                carrito.append({
                    'id': pastel.ID,
                    'nombre': pastel.Nombre,
                    'cantidad': cant,
                    'precio': float(precio),
                    'precio_lista': float(precio),
                    'descuento': 0.0,
                    'subtotal': float(sub),
                    'iva': 0.0,
                    'tasa_iva': 0.0,
                    'motivo_exencion': None,
                    'detalle_ingredientes': {'precio_base': float(precio), 'ingredientes': []}
                })
                # A veces agregan algo de panadería o bebida
                if random.random() < 0.4:
                    bebida = random.choice(prods_bebidas)
                    b_cant = random.randint(1, 3)
                    b_sub = bebida.PrecioBase * b_cant
                    carrito.append({
                        'id': bebida.ID,
                        'nombre': bebida.Nombre,
                        'cantidad': b_cant,
                        'precio': float(bebida.PrecioBase),
                        'precio_lista': float(bebida.PrecioBase),
                        'descuento': 0.0,
                        'subtotal': float(b_sub),
                        'iva': 0.0,
                        'tasa_iva': 0.0,
                        'motivo_exencion': None,
                        'detalle_ingredientes': {'precio_base': float(bebida.PrecioBase), 'ingredientes': []}
                    })
            else:
                # Venta regular de mostrador
                # Tipo de canasta:
                estilo = random.choice(['pan_diario', 'merienda_cafe', 'desayuno_salado', 'surtido_dulce'])
                items_elegidos = []

                if estilo == 'pan_diario':
                    # Mucho bolillo + un poco de pan dulce
                    bolillo = prod_map.get(1)
                    if bolillo:
                        items_elegidos.append((bolillo, random.randint(6, 15)))
                    pan_dulce = random.choice(prods_pan)
                    if pan_dulce.ID != 1:
                        items_elegidos.append((pan_dulce, random.randint(2, 5)))

                elif estilo == 'merienda_cafe':
                    # Café + dona/concha/pañuelito
                    cafe = prod_map.get(8)
                    if cafe:
                        items_elegidos.append((cafe, random.randint(1, 2)))
                    dulce = random.choice([p for p in prods_pan if p.ID in (4, 5, 6)])
                    items_elegidos.append((dulce, random.randint(1, 3)))

                elif estilo == 'desayuno_salado':
                    # Pan pizza o galleta jamón + gaseosa o café
                    salado = random.choice(prods_salados)
                    items_elegidos.append((salado, random.randint(1, 3)))
                    bebida = random.choice(prods_bebidas)
                    items_elegidos.append((bebida, random.randint(1, 2)))

                else: # surtido dulce
                    # Variedad de 2 a 3 tipos de pan dulce
                    seleccionados = random.sample(prods_pan, min(3, len(prods_pan)))
                    for p in seleccionados:
                        items_elegidos.append((p, random.randint(2, 4)))

                for prod, cant in items_elegidos:
                    sub = prod.PrecioBase * cant
                    carrito.append({
                        'id': prod.ID,
                        'nombre': prod.Nombre,
                        'cantidad': cant,
                        'precio': float(prod.PrecioBase),
                        'precio_lista': float(prod.PrecioBase),
                        'descuento': 0.0,
                        'subtotal': float(sub),
                        'iva': 0.0,
                        'tasa_iva': 0.0,
                        'motivo_exencion': None,
                        'detalle_ingredientes': {'precio_base': float(prod.PrecioBase), 'ingredientes': []}
                    })

            # Totales de la venta
            subtotal = sum(Decimal(str(item['subtotal'])) for item in carrito)
            iva = Decimal('0.00') # Régimen pendiente/exento
            total = subtotal + iva

            # Método de pago
            p_rand = random.random()
            if p_rand < 0.65:
                metodo_pago = 'Efectivo'
                pagos_payload = [{'metodo': 'Efectivo', 'monto': float(total), 'referencia': ''}]
            elif p_rand < 0.90:
                metodo_pago = 'Transferencia'
                banco = random.choice(['BAC', 'LAFISE', 'BANPRO', 'BDF'])
                ref_num = f'{banco}-{random.randint(100000, 999999)}'
                pagos_payload = [{'metodo': 'Transferencia', 'monto': float(total), 'referencia': ref_num}]
            else:
                metodo_pago = 'Efectivo USD'
                pagos_payload = [{'metodo': 'Efectivo USD', 'monto': float(total), 'referencia': '', 'tipo_cambio': float(tipo_cambio_usd)}]

            # Generar número consecutivo fiscal
            numero_factura = next_invoice(cursor, serie)
            codigo_seguimiento = uuid.uuid4().hex[:10].upper()
            clave_solicitud = str(uuid.uuid4())

            # 1. Insertar Factura
            cursor.execute("""
                INSERT INTO ventas.Facturas (
                    NumeroFactura, CodigoSeguimiento, UsuarioID, ClienteID, TurnoID,
                    Subtotal, IVA, Total, EsEncargo, IncluyeRUC, ClaveSolicitud, FechaHora
                )
                OUTPUT INSERTED.ID
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """, (
                numero_factura, codigo_seguimiento, usuario_id, cliente_id, turno_id,
                subtotal, iva, total, 1 if es_encargo else 0, clave_solicitud, fecha_venta
            ))
            factura_id = cursor.fetchone()[0]

            # 2. Insertar DetalleFacturas
            for item in carrito:
                cursor.execute("""
                    INSERT INTO ventas.DetalleFacturas (FacturaID, ProductoID, Cantidad, PrecioUnitario, Subtotal)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    factura_id, item['id'], item['cantidad'], item['precio'], item['subtotal']
                ))

            # 3. Insertar Pagos
            for p in pagos_payload:
                cursor.execute("""
                    INSERT INTO ventas.Pagos (
                        FacturaID, MetodoPago, Monto, FechaPago, NombreTransferente,
                        MonedaRegistro, TipoCambioAplicado, TurnoReceptorID, UsuarioReceptorID
                    )
                    VALUES (?, ?, ?, ?, ?, 'NIO', ?, ?, ?)
                """, (
                    factura_id, p['metodo'], p['monto'], fecha_venta,
                    p.get('referencia') or None,
                    tipo_cambio_usd if p['metodo'] == 'Efectivo USD' else None,
                    turno_id, usuario_id
                ))

            # 4. Si es encargo, insertar en ventas.Encargos
            encargo_info = {}
            if es_encargo:
                dias_entrega = random.randint(1, 5)
                fecha_entrega = fecha_venta + timedelta(days=dias_entrega)
                if fecha_entrega.date() < hoy:
                    estado_encargo = 'Entregado'
                elif fecha_entrega.date() == hoy:
                    estado_encargo = random.choice(['Listo', 'Entregado'])
                else:
                    estado_encargo = random.choice(['Pendiente', 'Listo'])

                notas = random.choice(notas_encargos)
                # Teléfono del cliente
                cursor.execute("SELECT Telefono, Nombre FROM crm.Clientes WHERE ID = ?", cliente_id)
                cl_data = cursor.fetchone()
                tel_contacto = cl_data.Telefono if cl_data and cl_data.Telefono else '88888888'
                nom_contacto = cl_data.Nombre if cl_data else 'Cliente'

                cursor.execute("""
                    INSERT INTO ventas.Encargos (
                        FacturaID, FechaEntrega, Estado, PoliticasAceptadas,
                        NotasCliente, Especificaciones, TelefonoContacto
                    )
                    VALUES (?, ?, ?, 1, ?, 'Elaboración artesanal panadería', ?)
                """, (factura_id, fecha_entrega, estado_encargo, notas, tel_contacto))

                encargo_info = {
                    'adelanto': float(total),
                    'saldo': 0.0,
                    'metodo_adelanto': metodo_pago,
                    'monto_recibido': float(total),
                    'referencia': pagos_payload[0].get('referencia', ''),
                    'fecha_entrega': fecha_entrega.strftime('%Y-%m-%d'),
                    'nombre_cliente': nom_contacto,
                    'telefono': tel_contacto,
                    'especificaciones': 'Elaboración artesanal panadería'
                }

            # 5. Incrementar compras de cliente registrado para actualizar fidelización
            if cliente_id > 1:
                cursor.execute("""
                    UPDATE crm.Clientes 
                    SET TotalCompras = ISNULL(TotalCompras, 0) + 1 
                    WHERE ID = ?
                """, cliente_id)
                cursor.execute("""
                    UPDATE crm.Clientes 
                    SET NivelConfianzaID = CASE 
                        WHEN TotalCompras >= 10 THEN 3 
                        WHEN TotalCompras >= 3 THEN 2 
                        ELSE 1 
                    END 
                    WHERE ID = ?
                """, cliente_id)

            # 6. Generar Asiento Contable
            entry = ContabilidadService.contabilizar_venta(
                cursor=cursor,
                usuario_id=usuario_id,
                numero_factura=numero_factura,
                subtotal=subtotal,
                iva=iva,
                total=total,
                pagos=[{'metodo': p['metodo'], 'monto': p['monto']} for p in pagos_payload],
                es_encargo=es_encargo,
                adelanto=total if es_encargo else 0,
                ip='127.0.0.1',
                fecha=fecha_venta
            )

            # 7. Generar DocumentoJSON
            link = f"http://brajherscake.local/seguimiento/{codigo_seguimiento}"
            document = {
                'id': factura_id,
                'numero_factura': numero_factura,
                'codigo_seguimiento': codigo_seguimiento,
                'solicitud_hash': uuid.uuid4().hex,
                'fecha': fecha_venta.strftime('%d/%m/%Y'),
                'hora': fecha_venta.strftime('%H:%M:%S'),
                'zona_horaria': 'America/Managua',
                'productos': carrito,
                'subtotal': float(subtotal),
                'iva': float(iva),
                'total': float(total),
                'cambio': 0.0,
                'es_encargo': es_encargo,
                'encargo_detalles': encargo_info if es_encargo else None,
                'tipo_cambio': str(tipo_cambio_usd),
                'pagos': pagos_payload,
                'qr_image': generar_qr_base64(link),
                'url_seguimiento': link,
                'asiento_id': entry['asiento_id'],
                'emisor': {k: v for k, v in config.items() if k.startswith('fiscal_')},
                'ruc': None,
                'condicion': 'Contado',
                'aviso': 'COMPROBANTE DE VENTA - PANADERÍA AMADA',
                'url_impresion': f'/admin/fiscal/facturas/{factura_id}/imprimir'
            }

            cursor.execute("""
                UPDATE ventas.Facturas 
                SET DocumentoJSON = ? 
                WHERE ID = ?
            """, (json.dumps(document, ensure_ascii=False), factura_id))

            # 8. Auditoría fiscal
            audit(cursor, usuario_id, 'EMISION', 'Factura', factura_id, {'numero': numero_factura, 'total': float(total)}, '127.0.0.1')

            facturas_insertadas += 1
            total_monto_ventas += total

            if facturas_insertadas % 10 == 0:
                print(f"  -> {facturas_insertadas} facturas insertadas... (Última: {numero_factura} por C${total})")

        conn.commit()
        conn.close()

        print("\n=== Inserción de ventas completada con éxito ===")
        print(f"Facturas generadas: {facturas_insertadas}")
        print(f"Monto total facturado: C$ {total_monto_ventas:,.2f}")
        print("Todos los asientos contables de diario y bitácoras fiscales fueron creados en equilibrio.")


if __name__ == '__main__':
    poblar_ventas()
