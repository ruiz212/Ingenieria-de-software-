"""
Script de población profesional y realista de ventas, ingresos, turnos, arqueos y contabilidad
para Panadería Amada (Brajher's Cake).
"""

import sys
import os
import random
import uuid
import json
from decimal import Decimal
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

# Cargar entorno y base de datos
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv('panaderia_amada/.env')

sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from app import create_app
from app.db import get_db_connection
from app.services.contabilidad_service import ContabilidadService, amount
from app.services.fiscal_service import next_invoice, configuration, audit
from app.utils.qr import generar_qr_base64


def descomponer_denominaciones(monto_total, moneda='NIO'):
    """Descompone un monto exacto en billetes y monedas físicas válidas."""
    if moneda == 'NIO':
        denominaciones = [
            Decimal('1000.00'), Decimal('500.00'), Decimal('200.00'),
            Decimal('100.00'), Decimal('50.00'), Decimal('20.00'),
            Decimal('10.00'), Decimal('5.00'), Decimal('1.00')
        ]
    else:
        denominaciones = [
            Decimal('100.00'), Decimal('50.00'), Decimal('20.00'),
            Decimal('10.00'), Decimal('5.00'), Decimal('1.00')
        ]
    
    resto = monto_total
    resultado = []
    for denom in denominaciones:
        if resto >= denom:
            cant = int(resto // denom)
            sub = denom * cant
            resto -= sub
            resultado.append({
                'tipo': moneda,
                'denominacion': denom,
                'cantidad': cant,
                'subtotal': sub
            })
    return resultado


def poblar_ventas_e_ingresos():
    app = create_app()

    with app.app_context():
        conn = get_db_connection()
        cursor = conn.cursor()

        print("=================================================================")
        print("  INICIANDO POBLACIÓN DE VENTAS, INGRESOS, ARQUEOS Y CONTABILIDAD")
        print("=================================================================")

        # 1. Configuración fiscal y tipo de cambio
        config = configuration(cursor)
        serie = config.get('fiscal_serie', 'FAC')
        tipo_cambio_usd = Decimal(str(config.get('tipo_cambio_usd', '36.62')))

        # 2. Cerrar turnos antiguos de agosto que quedaron abiertos
        cursor.execute("""
            UPDATE ventas.TurnosCaja
            SET Cerrado = 1,
                FechaCierre = '2026-08-09 23:00:00',
                EfectivoCalculado = ISNULL((SELECT SUM(Monto) FROM ventas.Pagos WHERE TurnoReceptorID = ventas.TurnosCaja.ID AND MetodoPago = 'Efectivo'), 0),
                TransferenciasCalculadas = ISNULL((SELECT SUM(Monto) FROM ventas.Pagos WHERE TurnoReceptorID = ventas.TurnosCaja.ID AND MetodoPago = 'Transferencia'), 0),
                TotalVentaNeta = ISNULL((SELECT SUM(Total) FROM ventas.Facturas WHERE TurnoID = ventas.TurnosCaja.ID), 0)
            WHERE ID IN (1, 2) AND Cerrado = 0
        """)
        conn.commit()
        print("-> Turnos antiguos de agosto cerrados y conciliados.")

        # 3. Poblar clientes CRM realistas de Nicaragua
        clientes_nuevos = [
            ('Doña Martha Solís', '88712345'),
            ('Lic. Francisco Chamorro', '89234567'),
            ('Dra. Claudia Barreto', '87123456'),
            ('Ing. Javier Toruño', '84567890'),
            ('Carmen Arróliga', '86345678'),
            ('Alejandro Blandón', '88901234'),
            ('Patricia Marenco', '85123456'),
            ('Marcos Talavera', '87456123'),
            ('Lucía Vado', '89012345'),
            ('Gabriel Centeno', '86789012'),
            ('Silvia Fonseca', '88345671'),
            ('Dr. Donald Espinoza', '84129876'),
            ('Auxiliadora Morales', '89561234'),
            ('Xiomara Rivas', '87234589'),
            ('Manuel Baldizón', '86451290'),
            ('Dra. Sonia Palacios', '88112233'),
            ('Lic. Ricardo Sequeira', '87554433')
        ]
        for nombre, tel in clientes_nuevos:
            cursor.execute("SELECT ID FROM crm.Clientes WHERE Telefono = ?", tel)
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO crm.Clientes (Nombre, Telefono, NivelConfianzaID, TotalCompras, CreadoEn)
                    VALUES (?, ?, 1, 0, DATEADD(DAY, -45, GETDATE()))
                """, nombre, tel)
        conn.commit()

        cursor.execute("SELECT ID, Nombre, Telefono FROM crm.Clientes")
        clientes_db = cursor.fetchall()
        cliente_mostrador_id = 1
        clientes_registrados = [c for c in clientes_db if c.ID != cliente_mostrador_id]
        print(f"-> Clientes disponibles en CRM: {len(clientes_db)}")

        # 4. Usuarios cajeros y vendedores
        cursor.execute("SELECT ID, Username FROM seguridad.Usuarios WHERE RolID IN (1, 2, 3)")
        usuarios_vendedores = [r.ID for r in cursor.fetchall()]
        if not usuarios_vendedores:
            usuarios_vendedores = [1]
        
        # ID 6 es cajera principal, o 2 si no existe
        cajera_hoy_id = 6 if 6 in usuarios_vendedores else (2 if 2 in usuarios_vendedores else usuarios_vendedores[0])

        # 5. Catálogo de productos
        cursor.execute("SELECT ID, Nombre, PrecioBase, CategoriaID FROM catalogo.Productos WHERE Activo = 1")
        productos_todos = cursor.fetchall()
        prod_map = {p.ID: p for p in productos_todos}

        prods_pan = [p for p in productos_todos if p.ID in (1, 4, 5, 6, 7)]
        prods_salados = [p for p in productos_todos if p.ID in (2, 3, 7)]
        prods_bebidas = [p for p in productos_todos if p.ID in (8, 9)]
        prods_pasteles = [p for p in productos_todos if p.ID in (10, 11, 13)]

        # Clientes corporativos con RUC
        empresas_ruc = [
            ('Distribuidora San Carlos S.A.', 'J0310000123456'),
            ('Clínica Médica Familiar Santa María', 'J0510000987654'),
            ('Consultoría y Servicios Jurídicos Managua', 'J0810000456123'),
            ('Colegio Bautista El Shaddai', 'J0210000678912'),
            ('Taller y Repuestos Centroamericanos', 'J0410000789123'),
            ('Ferretería La Económica Managua', 'J0310000889911')
        ]

        notas_encargos = [
            ('Pastel Tres Leches tradicional húmedo decorado con fresas y dedicatoria', 'Feliz Cumpleaños Mamá con decorado floral'),
            ('Pastel de Chocolate 1 Lb con doble relleno de fudge y dedicatoria', 'Felicidades Graduado Ing. Roberto'),
            ('Selva Negra con cerezas marrasquino y virutas de chocolate amargo', 'Feliz Aniversario 15 años María y Carlos'),
            ('Pastel temático infantil con decoración de Paw Patrol en merengue italiano', 'Feliz 4to Añito Mateo'),
            ('Pastel Tres Leches húmedo tradicional para evento bautizo con cruz blanca', 'Bautizo de Sofia Milagros'),
            ('Pastel de Cumpleaños con rosas celestes y dedicatoria personalizada', 'Feliz Cumpleaños Dra. Claudia Barreto'),
            ('Pastel de Chocolate decorado con fresas naturales y dedicatoria dorada', 'Feliz 50 Años Don Manuel')
        ]

        # 6. Preparar calendario de simulación: 1 al 25 de Octubre de 2026
        hoy = date(2026, 10, 25)
        hora_actual = 20 # 8:00 PM de hoy

        dias_a_procesar = []
        for d in range(1, 26):
            dia_actual = date(2026, 10, d)
            dias_a_procesar.append(dia_actual)

        print(f"-> Procesando 25 días operativos de Octubre 2026 (hasta hoy {hoy}).")

        total_facturas_insertadas = 0
        total_monto_facturado = Decimal('0.00')

        # Procesar día a día
        for dia_operativo in dias_a_procesar:
            es_hoy = (dia_operativo == hoy)
            es_fin_de_semana = dia_operativo.weekday() in (5, 6)

            # A. Obtener o crear TurnoCaja para este día
            cursor.execute("""
                SELECT ID, Cerrado FROM ventas.TurnosCaja 
                WHERE CONVERT(date, FechaApertura) = ?
            """, dia_operativo)
            turno_row = cursor.fetchone()

            if turno_row:
                turno_id = turno_row.ID
                turno_cerrado = turno_row.Cerrado
                cursor.execute("SELECT UsuarioID FROM ventas.TurnosCaja WHERE ID = ?", turno_id)
                cajero_dia = cursor.fetchone()[0]
            else:
                cajero_dia = cajera_hoy_id if es_hoy else random.choice(usuarios_vendedores)
                hora_apertura = datetime(dia_operativo.year, dia_operativo.month, dia_operativo.day, 6, 30, 0)
                
                cursor.execute("""
                    INSERT INTO ventas.TurnosCaja (UsuarioID, FechaApertura, Cerrado)
                    OUTPUT INSERTED.ID
                    VALUES (?, ?, ?)
                """, cajero_dia, hora_apertura, 0 if es_hoy else 1)
                turno_id = cursor.fetchone()[0]
                turno_cerrado = (not es_hoy)

            # Reasignar facturas existentes de este día al turno correspondiente
            cursor.execute("""
                UPDATE ventas.Facturas 
                SET TurnoID = ? 
                WHERE CONVERT(date, FechaHora) = ? AND (TurnoID IS NULL OR TurnoID <= 2)
            """, turno_id, dia_operativo)
            cursor.execute("""
                UPDATE p
                SET p.TurnoReceptorID = ?
                FROM ventas.Pagos p
                JOIN ventas.Facturas f ON p.FacturaID = f.ID
                WHERE CONVERT(date, f.FechaHora) = ? AND (p.TurnoReceptorID IS NULL OR p.TurnoReceptorID <= 2)
            """, turno_id, dia_operativo)

            # B. Determinar cuántas ventas adicionales generar para este día
            cursor.execute("""
                SELECT COUNT(*) FROM ventas.Facturas WHERE CONVERT(date, FechaHora) = ?
            """, dia_operativo)
            ventas_existentes = cursor.fetchone()[0]

            if es_hoy:
                # Hoy debe tener un flujo en vivo robusto y completo (28 a 34 ventas)
                meta_ventas = 30
            elif dia_operativo in (date(2026, 10, 22), date(2026, 10, 23), date(2026, 10, 24)):
                # Días que tenían 0 ventas
                meta_ventas = 24 if es_fin_de_semana else 18
            else:
                # Días que ya tenían 2-6 ventas: sumar 8-12 más para llegar a volumen realista
                meta_ventas = ventas_existentes + (random.randint(12, 18) if es_fin_de_semana else random.randint(8, 12))

            ventas_a_generar = max(0, meta_ventas - ventas_existentes)
            if ventas_a_generar == 0:
                continue

            # Generar horarios realistas para las ventas del día
            horas_ventas = []
            max_hora = min(hora_actual, 19) if es_hoy else 19

            for _ in range(ventas_a_generar):
                franja = random.choices(['manana', 'mediodia', 'tarde', 'noche'], weights=[0.35, 0.25, 0.25, 0.15])[0]
                if franja == 'manana':
                    h = random.randint(7, 10)
                elif franja == 'mediodia':
                    h = random.randint(11, 14)
                elif franja == 'tarde':
                    h = random.randint(15, 17)
                else:
                    h = random.randint(18, max(18, max_hora))
                
                if es_hoy and h > max_hora:
                    h = random.randint(7, max_hora)
                m = random.randint(0, 59)
                s = random.randint(0, 59)
                horas_ventas.append(datetime(dia_operativo.year, dia_operativo.month, dia_operativo.day, h, m, s))

            horas_ventas.sort()

            # Insertar cada venta del día
            for fecha_venta in horas_ventas:
                # Tipo de venta
                prob = random.random()
                es_encargo = False
                es_ruc = False
                tipo_canasta = 'mostrador'

                if prob < 0.12:
                    es_encargo = True
                    tipo_canasta = 'encargo'
                elif prob < 0.17:
                    es_ruc = True
                    tipo_canasta = 'ruc'
                else:
                    sub_prob = random.random()
                    if sub_prob < 0.35:
                        tipo_canasta = 'pan_diario'
                    elif sub_prob < 0.60:
                        tipo_canasta = 'merienda_cafe'
                    elif sub_prob < 0.80:
                        tipo_canasta = 'desayuno_salado'
                    elif sub_prob < 0.92:
                        tipo_canasta = 'surtido_dulce'
                    else:
                        tipo_canasta = 'pastel_vitrina'

                # Asignar usuario vendedor
                usuario_id = cajera_hoy_id if es_hoy else random.choice(usuarios_vendedores)

                # Asignar cliente
                if es_encargo or es_ruc or random.random() < 0.35:
                    cliente_obj = random.choice(clientes_registrados)
                    cliente_id = cliente_obj.ID
                    nom_cliente = cliente_obj.Nombre
                    tel_cliente = cliente_obj.Telefono or '88887766'
                else:
                    cliente_id = cliente_mostrador_id
                    nom_cliente = 'Cliente General'
                    tel_cliente = '88888888'

                # Armar carrito de productos
                carrito = []
                if tipo_canasta == 'encargo':
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
                    if random.random() < 0.40:
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
                elif tipo_canasta == 'pastel_vitrina':
                    pastel = random.choice(prods_pasteles)
                    carrito.append({
                        'id': pastel.ID,
                        'nombre': pastel.Nombre,
                        'cantidad': 1,
                        'precio': float(pastel.PrecioBase),
                        'precio_lista': float(pastel.PrecioBase),
                        'descuento': 0.0,
                        'subtotal': float(pastel.PrecioBase),
                        'iva': 0.0,
                        'tasa_iva': 0.0,
                        'motivo_exencion': None,
                        'detalle_ingredientes': {'precio_base': float(pastel.PrecioBase), 'ingredientes': []}
                    })
                elif tipo_canasta == 'ruc':
                    # Pedido grande para empresas
                    bolillo = prod_map.get(1)
                    if bolillo:
                        b_cant = random.randint(20, 40)
                        carrito.append({
                            'id': bolillo.ID,
                            'nombre': bolillo.Nombre,
                            'cantidad': b_cant,
                            'precio': float(bolillo.PrecioBase),
                            'precio_lista': float(bolillo.PrecioBase),
                            'descuento': 0.0,
                            'subtotal': float(bolillo.PrecioBase * b_cant),
                            'iva': 0.0,
                            'tasa_iva': 0.0,
                            'motivo_exencion': None,
                            'detalle_ingredientes': {'precio_base': float(bolillo.PrecioBase), 'ingredientes': []}
                        })
                    pan_dulce = random.choice([p for p in prods_pan if p.ID != 1])
                    pd_cant = random.randint(10, 20)
                    carrito.append({
                        'id': pan_dulce.ID,
                        'nombre': pan_dulce.Nombre,
                        'cantidad': pd_cant,
                        'precio': float(pan_dulce.PrecioBase),
                        'precio_lista': float(pan_dulce.PrecioBase),
                        'descuento': 0.0,
                        'subtotal': float(pan_dulce.PrecioBase * pd_cant),
                        'iva': 0.0,
                        'tasa_iva': 0.0,
                        'motivo_exencion': None,
                        'detalle_ingredientes': {'precio_base': float(pan_dulce.PrecioBase), 'ingredientes': []}
                    })
                    cafe = prod_map.get(8)
                    if cafe:
                        c_cant = random.randint(5, 12)
                        carrito.append({
                            'id': cafe.ID,
                            'nombre': cafe.Nombre,
                            'cantidad': c_cant,
                            'precio': float(cafe.PrecioBase),
                            'precio_lista': float(cafe.PrecioBase),
                            'descuento': 0.0,
                            'subtotal': float(cafe.PrecioBase * c_cant),
                            'iva': 0.0,
                            'tasa_iva': 0.0,
                            'motivo_exencion': None,
                            'detalle_ingredientes': {'precio_base': float(cafe.PrecioBase), 'ingredientes': []}
                        })
                else:
                    # Canastas regulares de panadería
                    items_elegidos = []
                    if tipo_canasta == 'pan_diario':
                        bolillo = prod_map.get(1)
                        if bolillo:
                            items_elegidos.append((bolillo, random.randint(8, 20)))
                        pan_dulce = random.choice([p for p in prods_pan if p.ID != 1])
                        items_elegidos.append((pan_dulce, random.randint(2, 5)))
                    elif tipo_canasta == 'merienda_cafe':
                        cafe = prod_map.get(8)
                        if cafe:
                            items_elegidos.append((cafe, random.randint(1, 2)))
                        dulce = random.choice([p for p in prods_pan if p.ID in (4, 5, 6)])
                        items_elegidos.append((dulce, random.randint(1, 3)))
                    elif tipo_canasta == 'desayuno_salado':
                        salado = random.choice(prods_salados)
                        items_elegidos.append((salado, random.randint(1, 3)))
                        bebida = random.choice(prods_bebidas)
                        items_elegidos.append((bebida, random.randint(1, 2)))
                    else: # surtido_dulce
                        seleccionados = random.sample([p for p in prods_pan if p.ID != 1], min(3, len(prods_pan)-1))
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

                # Calcular subtotales
                subtotal = sum(Decimal(str(item['subtotal'])) for item in carrito)
                iva = Decimal('0.00')
                total = subtotal + iva

                # Método de pago
                p_rand = random.random()
                if es_ruc or (p_rand < 0.28 and total >= Decimal('100.00')):
                    metodo_pago = 'Transferencia'
                    banco = random.choice(['BAC', 'LAFISE', 'BANPRO', 'BDF'])
                    ref_num = f'{banco}-{random.randint(100000, 999999)}'
                    pagos_payload = [{'metodo': 'Transferencia', 'monto': float(total), 'referencia': ref_num}]
                elif p_rand < 0.88:
                    metodo_pago = 'Efectivo'
                    pagos_payload = [{'metodo': 'Efectivo', 'monto': float(total), 'referencia': ''}]
                else:
                    metodo_pago = 'Efectivo USD'
                    monto_usd = round(total / tipo_cambio_usd, 2)
                    pagos_payload = [{
                        'metodo': 'Efectivo USD',
                        'monto': float(total),
                        'referencia': f'${monto_usd:.2f} USD',
                        'tipo_cambio': float(tipo_cambio_usd)
                    }]

                # Generar número consecutivo fiscal
                numero_factura = next_invoice(cursor, serie)
                codigo_seguimiento = uuid.uuid4().hex[:10].upper()
                clave_solicitud = str(uuid.uuid4())

                # 1. Insertar Factura
                cursor.execute("""
                    INSERT INTO ventas.Facturas (
                        NumeroFactura, CodigoSeguimiento, UsuarioID, ClienteID, TurnoID,
                        Subtotal, IVA, Total, EsEncargo, IncluyeRUC, ClaveSolicitud, FechaHora, EstadoFiscal
                    )
                    OUTPUT INSERTED.ID
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Emitida')
                """, (
                    numero_factura, codigo_seguimiento, usuario_id, cliente_id, turno_id,
                    subtotal, iva, total, 1 if es_encargo else 0, 1 if es_ruc else 0,
                    clave_solicitud, fecha_venta
                ))
                factura_id = cursor.fetchone()[0]

                # 2. Insertar DetalleFacturas
                for item in carrito:
                    cursor.execute("""
                        INSERT INTO ventas.DetalleFacturas (FacturaID, ProductoID, Cantidad, PrecioUnitario, Subtotal)
                        VALUES (?, ?, ?, ?, ?)
                    """, (factura_id, item['id'], item['cantidad'], item['precio'], item['subtotal']))

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

                # 4. Si incluye RUC, insertar en ventas.FacturasRUC
                ruc_info = None
                if es_ruc:
                    empresa_nom, empresa_ruc = random.choice(empresas_ruc)
                    cursor.execute("""
                        INSERT INTO ventas.FacturasRUC (FacturaID, RazonSocial, NumeroRUC)
                        VALUES (?, ?, ?)
                    """, (factura_id, empresa_nom, empresa_ruc))
                    ruc_info = {'numero': empresa_ruc, 'razon_social': empresa_nom}

                # 5. Si es encargo, insertar en ventas.Encargos
                encargo_info = {}
                if es_encargo:
                    esp, notita = random.choice(notas_encargos)
                    # Si es hoy o días anteriores
                    dias_adelante = random.choice([0, 1, 2, 3])
                    fecha_entrega = fecha_venta + timedelta(days=dias_adelante)

                    if fecha_entrega.date() < hoy:
                        estado_encargo = 'Entregado'
                    elif fecha_entrega.date() == hoy:
                        estado_encargo = random.choice(['Listo', 'Entregado'])
                    else:
                        estado_encargo = random.choice(['Pendiente', 'Listo'])

                    cursor.execute("""
                        INSERT INTO ventas.Encargos (
                            FacturaID, FechaEntrega, Estado, PoliticasAceptadas,
                            NotasCliente, Especificaciones, TelefonoContacto
                        )
                        VALUES (?, ?, ?, 1, ?, ?, ?)
                    """, (factura_id, fecha_entrega, estado_encargo, notita, esp, tel_cliente))

                    encargo_info = {
                        'adelanto': float(total),
                        'saldo': 0.0,
                        'metodo_adelanto': metodo_pago,
                        'monto_recibido': float(total),
                        'referencia': pagos_payload[0].get('referencia', ''),
                        'fecha_entrega': fecha_entrega.strftime('%Y-%m-%d'),
                        'nombre_cliente': nom_cliente,
                        'telefono': tel_cliente,
                        'especificaciones': esp
                    }

                # 6. Contabilizar Venta en Contabilidad General (Partida Doble NIIF)
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

                # 7. DocumentoJSON inmutable para reimpresión y verificación
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
                    'ruc': ruc_info,
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

                total_facturas_insertadas += 1
                total_monto_facturado += total

            # C. Si el día ya pasó (no es hoy), cerrar el TurnoCaja y registrar el ArqueoCaja
            if not es_hoy:
                cursor.execute("""
                    SELECT ISNULL(SUM(Total), 0) FROM ventas.Facturas WHERE TurnoID = ?
                """, turno_id)
                venta_neta = Decimal(str(cursor.fetchone()[0]))

                cursor.execute("""
                    SELECT 
                        ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo' THEN p.Monto ELSE 0 END), 0) AS TotalEfectivo,
                        ISNULL(SUM(CASE WHEN p.MetodoPago = 'Transferencia' THEN p.Monto ELSE 0 END), 0) AS TotalTransferencias,
                        ISNULL(SUM(CASE WHEN p.MetodoPago = 'Efectivo USD' THEN p.Monto ELSE 0 END), 0) AS TotalUSD_NIO
                    FROM ventas.Pagos p
                    JOIN ventas.Facturas f ON p.FacturaID = f.ID
                    WHERE f.TurnoID = ?
                """, turno_id)
                row_totales = cursor.fetchone()
                efectivo_calc = Decimal(str(row_totales[0]))
                transf_calc = Decimal(str(row_totales[1]))
                usd_calc_nio = Decimal(str(row_totales[2]))
                usd_dolares = round(usd_calc_nio / tipo_cambio_usd, 2)

                hora_cierre = datetime(dia_operativo.year, dia_operativo.month, dia_operativo.day, 20, 30, 0)

                cursor.execute("""
                    UPDATE ventas.TurnosCaja
                    SET Cerrado = 1,
                        FechaCierre = ?,
                        EfectivoCalculado = ?,
                        TransferenciasCalculadas = ?,
                        TotalVentaNeta = ?
                    WHERE ID = ?
                """, (hora_cierre, efectivo_calc, transf_calc, venta_neta, turno_id))

                # Verificar si ya existe arqueo para este turno
                cursor.execute("SELECT ID FROM ventas.ArqueoCaja WHERE TurnoID = ?", turno_id)
                arq_existente = cursor.fetchone()
                if not arq_existente and (efectivo_calc > 0 or transf_calc > 0):
                    # Simular arqueo cerrado y cuadrado
                    cursor.execute("""
                        INSERT INTO ventas.ArqueoCaja (
                            TurnoID, UsuarioID, EfectivoContado, TransferenciasContadas,
                            DolaresContados, TipoCambioUsado, EfectivoSistema, TransferenciasSistema,
                            DiferenciaEfectivo, DiferenciaTransferencias, Observaciones,
                            FechaArqueo, VerificadoPorID, FechaVerificacion, EstadoArqueo,
                            RequiereJustificacion
                        )
                        OUTPUT INSERTED.ID
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0.00, 0.00, 'Arqueo de cierre de turno conciliado.', ?, 1, ?, 'Cerrado', 0)
                    """, (
                        turno_id, cajero_dia, efectivo_calc, transf_calc,
                        usd_dolares, tipo_cambio_usd, efectivo_calc, transf_calc,
                        hora_cierre, hora_cierre + timedelta(minutes=10)
                    ))
                    arqueo_id = cursor.fetchone()[0]

                    # Desglose de denominaciones físicas contadas
                    denoms = descomponer_denominaciones(efectivo_calc, 'NIO')
                    for d in denoms:
                        cursor.execute("""
                            INSERT INTO ventas.ArqueoDetalleDenominacion (ArqueoID, TipoMoneda, Denominacion, Cantidad)
                            VALUES (?, ?, ?, ?)
                        """, (arqueo_id, d['tipo'], d['denominacion'], d['cantidad']))
                    
                    if usd_dolares > 0:
                        denoms_usd = descomponer_denominaciones(usd_dolares, 'USD')
                        for d in denoms_usd:
                            cursor.execute("""
                                INSERT INTO ventas.ArqueoDetalleDenominacion (ArqueoID, TipoMoneda, Denominacion, Cantidad)
                                VALUES (?, ?, ?, ?)
                            """, (arqueo_id, d['tipo'], d['denominacion'], d['cantidad']))

            # Commit al final de cada día para asegurar persistencia
            conn.commit()
            print(f"  -> Día {dia_operativo}: {ventas_a_generar} ventas generadas exitosamente. (Turno {turno_id})")

        # 7. Actualizar fidelización de todos los clientes según compras acumuladas
        cursor.execute("""
            UPDATE crm.Clientes
            SET TotalCompras = (
                SELECT COUNT(*) FROM ventas.Facturas WHERE ClienteID = crm.Clientes.ID
            )
            WHERE ID > 1
        """)
        cursor.execute("""
            UPDATE crm.Clientes
            SET NivelConfianzaID = CASE 
                WHEN TotalCompras >= 10 THEN 3 
                WHEN TotalCompras >= 4 THEN 2 
                ELSE 1 
            END
            WHERE ID > 1
        """)
        conn.commit()

        # 8. Reporte final de resumen
        print("\n=================================================================")
        print("           POBLACIÓN REALISTA COMPLETADA CON ÉXITO")
        print("=================================================================")
        print(f"Facturas nuevas insertadas: {total_facturas_insertadas}")
        print(f"Monto nuevo facturado: C$ {total_monto_facturado:,.2f}")
        
        # Consultar totales globales actuales en base de datos
        cursor.execute("SELECT COUNT(*), SUM(Total) FROM ventas.Facturas")
        tot_f, tot_m = cursor.fetchone()
        print(f"Total global en Facturas: {tot_f} facturas | Total: C$ {tot_m:,.2f}")

        cursor.execute("SELECT COUNT(*) FROM ventas.TurnosCaja")
        print(f"Total Turnos de Caja: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM ventas.ArqueoCaja")
        print(f"Total Arqueos de Caja con desglose: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM contabilidad.AsientosDiario")
        print(f"Total Asientos Contables Diario: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM ventas.Encargos")
        print(f"Total Encargos: {cursor.fetchone()[0]}")

        cursor.execute("SELECT COUNT(*) FROM ventas.FacturasRUC")
        print(f"Total Facturas con RUC: {cursor.fetchone()[0]}")

        cursor.execute("""
            SELECT COUNT(*), SUM(Total) FROM ventas.Facturas 
            WHERE CONVERT(date, FechaHora) = '2026-10-25'
        """)
        r_hoy = cursor.fetchone()
        print(f"Ventas registradas para HOY (2026-10-25): {r_hoy[0]} ventas por C$ {r_hoy[1]:,.2f}")

        conn.close()


if __name__ == '__main__':
    poblar_ventas_e_ingresos()
