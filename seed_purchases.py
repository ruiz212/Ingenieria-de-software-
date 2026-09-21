import sys
import os
import random
from datetime import datetime, timedelta

# Asegurar que el entorno Flask se cargue correctamente
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from app import create_app
from app.db import get_db_connection

app = create_app()

with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()

    print("Registrando historial de compras...")

    # Obtener Proveedores
    cursor.execute("SELECT ID, Nombre FROM Proveedores")
    proveedores = {row.Nombre: row.ID for row in cursor.fetchall()}
    
    # Mapeo de categorías/nombres a proveedores para que sea realista
    def obtener_proveedor_id(nombre_insumo):
        nombre_insumo = nombre_insumo.lower()
        if 'harina' in nombre_insumo or 'azúcar' in nombre_insumo or 'azucar' in nombre_insumo:
            return proveedores.get('Agricorp', random.choice(list(proveedores.values())))
        elif 'leche' in nombre_insumo or 'queso' in nombre_insumo or 'mantequilla' in nombre_insumo or 'crema' in nombre_insumo:
            return proveedores.get('Eskimo S.A. / Lala', random.choice(list(proveedores.values())))
        elif 'levadura' in nombre_insumo or 'colorante' in nombre_insumo or 'esencia' in nombre_insumo or 'polvo' in nombre_insumo:
            return proveedores.get('Dicegsa', random.choice(list(proveedores.values())))
        elif 'manteca' in nombre_insumo or 'aceite' in nombre_insumo or 'jamón' in nombre_insumo:
            return proveedores.get('Cargill / Tip Top Industrial', random.choice(list(proveedores.values())))
        elif 'domo' in nombre_insumo or 'cartón' in nombre_insumo or 'capacillo' in nombre_insumo or 'bolsa' in nombre_insumo:
            return proveedores.get('Comercializadora San José', random.choice(list(proveedores.values())))
        elif 'premezcla' in nombre_insumo:
            return proveedores.get('PriceSmart Nicaragua', random.choice(list(proveedores.values())))
        else:
            return proveedores.get('Levapan Nicaragua', random.choice(list(proveedores.values())))

    # Obtener materias primas con su stock actual (asumiendo que ese fue el monto "comprado" inicial)
    cursor.execute("SELECT ID, Nombre, StockActual, UnidadMedidaID FROM MateriaPrima WHERE StockActual > 0")
    insumos = cursor.fetchall()
    
    # Para saber qué unidad es cada ID
    cursor.execute("SELECT ID, Abreviatura FROM UnidadesMedida")
    unidades = {row.ID: row.Abreviatura for row in cursor.fetchall()}

    compras_registradas = 0
    for insumo in insumos:
        # Solo registrar si no hay compras previas para evitar duplicados en caso de re-ejecución
        cursor.execute("SELECT COUNT(*) FROM ComprasMateriaPrima WHERE MateriaPrimaID = ?", insumo.ID)
        if cursor.fetchone()[0] == 0:
            proveedor_id = obtener_proveedor_id(insumo.Nombre)
            
            # Generar un costo razonable
            abrev = unidades.get(insumo.UnidadMedidaID, 'g')
            cantidad = float(insumo.StockActual)
            costo_total = 0.0
            
            if abrev == 'g':
                # Ej: 1 kg cuesta entre 30 y 100 córdobas. O sea, 1 gramo cuesta 0.03 a 0.1
                costo_total = cantidad * random.uniform(0.03, 0.15)
            elif abrev == 'ml':
                # Ej: 1 litro cuesta entre 40 y 150 córdobas. O sea, 1 ml cuesta 0.04 a 0.15
                costo_total = cantidad * random.uniform(0.04, 0.15)
            elif abrev == 'ud':
                # Ej: 1 caja cuesta entre 2 y 10 córdobas
                costo_total = cantidad * random.uniform(2.0, 10.0)
                
            # Fecha de compra (hace 1 a 7 días)
            dias_atras = random.randint(1, 7)
            fecha_compra = datetime.now() - timedelta(days=dias_atras)
            
            cursor.execute("""
                INSERT INTO ComprasMateriaPrima (MateriaPrimaID, ProveedorID, Cantidad, CostoTotal, Fecha)
                VALUES (?, ?, ?, ?, ?)
            """, insumo.ID, proveedor_id, cantidad, round(costo_total, 2), fecha_compra)
            
            compras_registradas += 1

    conn.commit()
    conn.close()
    
    print(f"Se registraron {compras_registradas} compras exitosamente para cuadrar el inventario inicial.")
