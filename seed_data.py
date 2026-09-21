import sys
import os

# Asegurar que el entorno Flask se cargue correctamente
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from app import create_app
from app.db import get_db_connection

app = create_app()

with app.app_context():
    conn = get_db_connection()
    cursor = conn.cursor()

    print("Iniciando inserción de datos...")

    # 1. Insertar Unidades de Medida
    unidades = [
        ('g', 'Gramos'),
        ('ml', 'Mililitros'),
        ('ud', 'Unidades')
    ]
    unidades_dict = {}
    for abrev, nombre in unidades:
        cursor.execute("SELECT ID FROM UnidadesMedida WHERE Abreviatura = ?", abrev)
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO UnidadesMedida (Nombre, Abreviatura) OUTPUT INSERTED.ID VALUES (?, ?)", nombre, abrev)
            unidades_dict[abrev] = cursor.fetchone()[0]
        else:
            unidades_dict[abrev] = row.ID

    # 2. Insertar Categorías
    categorias = ['Harinas', 'Lácteos', 'Grasas', 'Azúcares', 'Levaduras/Químicos', 'Saborizantes', 'Rellenos/Otros', 'Empaques', 'Panadería', 'Repostería']
    categorias_dict = {}
    for cat in categorias:
        cursor.execute("SELECT ID FROM Categorias WHERE Nombre = ?", cat)
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT INTO Categorias (Nombre, Descripcion) OUTPUT INSERTED.ID VALUES (?, ?)", cat, f'Categoría {cat}')
            categorias_dict[cat] = cursor.fetchone()[0]
        else:
            categorias_dict[cat] = row.ID

    # 3. Insertar Materia Prima
    materia_prima = [
        ('Harina Fuerte (Alta Proteína)', 'Harinas', 'g'),
        ('Harina Suave (Repostería)', 'Harinas', 'g'),
        ('Premezcla Pastel de Chocolate', 'Harinas', 'g'),
        ('Premezcla Pastel Vainilla', 'Harinas', 'g'),
        ('Fécula de Maíz (Maicena)', 'Harinas', 'g'),
        ('Leche Fluida Entera', 'Lácteos', 'ml'),
        ('Leche Evaporada', 'Lácteos', 'g'),
        ('Leche Condensada', 'Lácteos', 'g'),
        ('Crema Dulce (Para Batir/Chantilly)', 'Lácteos', 'ml'),
        ('Mantequilla Lavada', 'Lácteos', 'g'),
        ('Queso Mozzarella Rallado', 'Lácteos', 'g'),
        ('Leche en Polvo', 'Lácteos', 'g'),
        ('Manteca Vegetal', 'Grasas', 'g'),
        ('Margarina Industrial (Clásica)', 'Grasas', 'g'),
        ('Margarina para Hojaldre', 'Grasas', 'g'),
        ('Aceite Vegetal', 'Grasas', 'ml'),
        ('Azúcar Blanca Sulfatada', 'Azúcares', 'g'),
        ('Azúcar Glas (Pulverizada)', 'Azúcares', 'g'),
        ('Azúcar Moreno', 'Azúcares', 'g'),
        ('Levadura Fresca (Prensada)', 'Levaduras/Químicos', 'g'),
        ('Levadura Seca Instantánea', 'Levaduras/Químicos', 'g'),
        ('Polvo para Hornear', 'Levaduras/Químicos', 'g'),
        ('Sal Fina Yodada', 'Levaduras/Químicos', 'g'),
        ('Propionato de Calcio (Conservante)', 'Levaduras/Químicos', 'g'),
        ('Bicarbonato de Sodio', 'Levaduras/Químicos', 'g'),
        ('Esencia de Vainilla Oscura', 'Saborizantes', 'ml'),
        ('Esencia de Vainilla Clara', 'Saborizantes', 'ml'),
        ('Canela Molida', 'Saborizantes', 'g'),
        ('Cacao Puro en Polvo', 'Saborizantes', 'g'),
        ('Colorante Amarillo Huevo', 'Saborizantes', 'ml'),
        ('Mermelada de Piña Horneable', 'Rellenos/Otros', 'g'),
        ('Mermelada de Fresa', 'Rellenos/Otros', 'g'),
        ('Dulce de Leche (Manjar)', 'Rellenos/Otros', 'g'),
        ('Chocolate Cobertura (Tableta)', 'Rellenos/Otros', 'g'),
        ('Cerezas en Almíbar', 'Rellenos/Otros', 'g'),
        ('Jamón Prensado (Embutido)', 'Rellenos/Otros', 'g'),
        ('Salsa de Tomate (Pizza)', 'Rellenos/Otros', 'ml'),
        ('Domo Plástico para Pastel 1 Lb', 'Empaques', 'ud'),
        ('Base de Cartón 10"', 'Empaques', 'ud'),
        ('Capacillos de Papel', 'Empaques', 'ud'),
        ('Bolsa Plástica Transparente (Pan)', 'Empaques', 'ud')
    ]

    insumos_dict = {}
    for nombre, cat_nombre, abrev_unidad in materia_prima:
        cursor.execute("SELECT ID FROM MateriaPrima WHERE Nombre = ?", nombre)
        row = cursor.fetchone()
        if not row:
            cursor.execute("""
                INSERT INTO MateriaPrima (Nombre, UnidadMedidaID, StockActual, StockMinimo) 
                OUTPUT INSERTED.ID 
                VALUES (?, ?, 0, 10)
            """, nombre, unidades_dict[abrev_unidad])
            insumos_dict[nombre] = cursor.fetchone()[0]
        else:
            insumos_dict[nombre] = row.ID

    # 4. Insertar Productos y Recetas
    recetas = [
        {
            'nombre': 'Bolillo',
            'categoria': 'Panadería',
            'ingredientes': [
                ('Harina Fuerte (Alta Proteína)', 2000),
                ('Agua', 1100), # Not in DB, mapped to Leche or needs skip
                ('Levadura Fresca (Prensada)', 60),
                ('Sal Fina Yodada', 40),
                ('Azúcar Blanca Sulfatada', 40),
                ('Manteca Vegetal', 100)
            ]
        },
        {
            'nombre': 'Concha de Vainilla',
            'categoria': 'Panadería',
            'ingredientes': [
                ('Harina Fuerte (Alta Proteína)', 1000),
                ('Levadura Fresca (Prensada)', 40),
                ('Azúcar Blanca Sulfatada', 250),
                ('Manteca Vegetal', 150),
                ('Sal Fina Yodada', 10),
                ('Esencia de Vainilla Oscura', 10),
                ('Harina Suave (Repostería)', 300),
                ('Azúcar Glas (Pulverizada)', 300),
                ('Manteca Vegetal', 300)
            ]
        },
        {
            'nombre': 'Dona de Chocolate',
            'categoria': 'Panadería',
            'ingredientes': [
                ('Harina Fuerte (Alta Proteína)', 1000),
                ('Leche Fluida Entera', 450),
                ('Levadura Fresca (Prensada)', 40),
                ('Azúcar Blanca Sulfatada', 150),
                ('Manteca Vegetal', 100),
                ('Aceite Vegetal', 1000),
                ('Chocolate Cobertura (Tableta)', 400)
            ]
        },
        {
            'nombre': 'Panuelito',
            'categoria': 'Panadería',
            'ingredientes': [
                ('Harina Fuerte (Alta Proteína)', 1000),
                ('Sal Fina Yodada', 20),
                ('Margarina para Hojaldre', 800),
                ('Mermelada de Piña Horneable', 800),
                ('Azúcar Blanca Sulfatada', 100)
            ]
        },
        {
            'nombre': 'Milanesa',
            'categoria': 'Panadería',
            'ingredientes': [
                ('Harina Fuerte (Alta Proteína)', 1000),
                ('Levadura Fresca (Prensada)', 30),
                ('Azúcar Blanca Sulfatada', 300),
                ('Manteca Vegetal', 150),
                ('Sal Fina Yodada', 15),
                ('Colorante Amarillo Huevo', 2)
            ]
        },
        {
            'nombre': 'Pan Pizza',
            'categoria': 'Panadería',
            'ingredientes': [
                ('Harina Fuerte (Alta Proteína)', 1000),
                ('Aceite Vegetal', 50),
                ('Levadura Fresca (Prensada)', 30),
                ('Sal Fina Yodada', 20),
                ('Salsa de Tomate (Pizza)', 300),
                ('Queso Mozzarella Rallado', 800),
                ('Jamón Prensado (Embutido)', 400)
            ]
        },
        {
            'nombre': 'Galleta de Jamon',
            'categoria': 'Panadería',
            'ingredientes': [
                ('Harina Fuerte (Alta Proteína)', 1000),
                ('Sal Fina Yodada', 20),
                ('Margarina para Hojaldre', 600),
                ('Jamón Prensado (Embutido)', 500)
            ]
        },
        {
            'nombre': 'Pastel de Chocolate (1 Lb)',
            'categoria': 'Repostería',
            'ingredientes': [
                ('Premezcla Pastel de Chocolate', 500),
                ('Aceite Vegetal', 100),
                ('Dulce de Leche (Manjar)', 200),
                ('Crema Dulce (Para Batir/Chantilly)', 350),
                ('Base de Cartón 10"', 1),
                ('Domo Plástico para Pastel 1 Lb', 1)
            ]
        },
        {
            'nombre': 'Pastel Tres Leches (1 Lb)',
            'categoria': 'Repostería',
            'ingredientes': [
                ('Harina Suave (Repostería)', 250),
                ('Azúcar Blanca Sulfatada', 250),
                ('Polvo para Hornear', 10),
                ('Esencia de Vainilla Clara', 5),
                ('Leche Evaporada', 400),
                ('Leche Condensada', 395),
                ('Leche Fluida Entera', 200),
                ('Crema Dulce (Para Batir/Chantilly)', 300),
                ('Cerezas en Almíbar', 50),
                ('Domo Plástico para Pastel 1 Lb', 1)
            ]
        },
        {
            'nombre': 'Selva Negra',
            'categoria': 'Repostería',
            'ingredientes': [
                ('Premezcla Pastel de Chocolate', 500),
                ('Aceite Vegetal', 100),
                ('Mermelada de Fresa', 150),
                ('Crema Dulce (Para Batir/Chantilly)', 400),
                ('Cerezas en Almíbar', 100),
                ('Chocolate Cobertura (Tableta)', 100),
                ('Base de Cartón 10"', 1),
                ('Domo Plástico para Pastel 1 Lb', 1)
            ]
        }
    ]

    for rec in recetas:
        # Insertar Producto
        cursor.execute("SELECT ID FROM Productos WHERE Nombre = ?", rec['nombre'])
        row = cursor.fetchone()
        if not row:
            cursor.execute("""
                INSERT INTO Productos (Nombre, CategoriaID, PrecioBase, EsFicticio, Activo) 
                OUTPUT INSERTED.ID 
                VALUES (?, ?, 150.00, 0, 1)
            """, rec['nombre'], categorias_dict[rec['categoria']])
            producto_id = cursor.fetchone()[0]
        else:
            producto_id = row.ID
            # Borrar receta existente
            cursor.execute("DELETE FROM RecetaProducto WHERE ProductoID = ?", producto_id)

        # Agrupar ingredientes repetidos (como Manteca Vegetal en la Concha)
        ing_dict = {}
        for ing_nombre, cantidad in rec['ingredientes']:
            if ing_nombre == 'Agua':
                continue # Agua is free and not tracked usually, or we can add it later
            ing_dict[ing_nombre] = ing_dict.get(ing_nombre, 0) + cantidad

        # Insertar Receta
        for ing_nombre, cantidad in ing_dict.items():
            if ing_nombre in insumos_dict:
                cursor.execute("""
                    INSERT INTO RecetaProducto (ProductoID, MateriaPrimaID, CantidadNecesaria)
                    VALUES (?, ?, ?)
                """, producto_id, insumos_dict[ing_nombre], cantidad)
            else:
                print(f"Advertencia: Ingrediente '{ing_nombre}' no encontrado para receta '{rec['nombre']}'")

    conn.commit()
    conn.close()
    print("Datos insertados exitosamente.")
