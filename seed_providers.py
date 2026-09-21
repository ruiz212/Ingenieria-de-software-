import sys
import os
import random

# Asegurar que el entorno Flask se cargue correctamente
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from app import create_app
from app.db import get_db_connection

app = create_app()

with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()

    print("Agregando proveedores y actualizando inventario...")

    # 1. Proveedores Reales de Nicaragua
    proveedores = [
        ('PriceSmart Nicaragua', '2268-1234', 1),
        ('Agricorp', '2255-8888', 1),
        ('Eskimo S.A. / Lala', '2277-9999', 1),
        ('Dicegsa', '2249-1111', 1),
        ('Levapan Nicaragua', '2222-3333', 1),
        ('Cargill / Tip Top Industrial', '2299-4444', 1),
        ('Comercializadora San José', '2244-7777', 1)
    ]

    for p in proveedores:
        cursor.execute("SELECT ID FROM Proveedores WHERE Nombre = ?", p[0])
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO Proveedores (Nombre, Telefono, Activo)
                VALUES (?, ?, ?)
            """, p)

    # 2. Inyectar Stock Masivo a la Materia Prima
    cursor.execute("SELECT ID, Nombre, UnidadMedidaID FROM MateriaPrima")
    insumos = cursor.fetchall()
    
    # UnidadMedidaID: asumiendo que 1 es g, 2 es ml, 3 es ud (basado en el script anterior)
    cursor.execute("SELECT ID, Abreviatura FROM UnidadesMedida")
    unidades = {row.Abreviatura: row.ID for row in cursor.fetchall()}

    for insumo in insumos:
        unidad = insumo.UnidadMedidaID
        stock_agregar = 0
        
        # Si es gramos (ej. saco de harina 50lb son ~22,600g, pondremos 100,000g = ~4 sacos)
        if unidad == unidades.get('g'):
            stock_agregar = random.randint(50000, 150000) # Entre 50kg y 150kg
        
        # Si es ml (ej. galón son ~3785ml, pondremos 50,000ml = ~13 galones)
        elif unidad == unidades.get('ml'):
            stock_agregar = random.randint(20000, 80000) # Entre 20 y 80 litros
            
        # Si es unidades (domos, cartones, bolsas)
        elif unidad == unidades.get('ud'):
            stock_agregar = random.randint(1000, 5000) # Entre 1,000 y 5,000 unidades

        # Actualizar stock en la BD
        cursor.execute("""
            UPDATE MateriaPrima 
            SET StockActual = StockActual + ?, StockMinimo = ? 
            WHERE ID = ?
        """, stock_agregar, 5000, insumo.ID)

    conn.commit()
    conn.close()
    
    print(f"Se inyectó stock a {len(insumos)} insumos exitosamente.")
    print("Proveedores de Nicaragua agregados correctamente.")
