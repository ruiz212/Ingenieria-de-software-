"""
Seed script: 3 años de historia comercial, nómina, ventas y DGI para Panadería Amada (Brajher's Cake).
Periodo histórico: Noviembre 2023 - Noviembre 2026 (36 meses).
"""
import os
import sys
import random
import hashlib
import json
from datetime import datetime, date, timedelta, time
from decimal import Decimal
import pyodbc
from dotenv import load_dotenv

load_dotenv()
CONNECTION_STRING = os.environ.get(
    'DB_CONNECTION_STRING',
    r'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLDEV;DATABASE=PanaderiaDB;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;'
)

random.seed(20261105)


def get_conn():
    return pyodbc.connect(CONNECTION_STRING)


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ==============================================================================
# 1. MATERIAS PRIMAS NICARAGÜENSES
# ==============================================================================
MATERIAS_PRIMAS_NICA = [
    # (Nombre, UnidadMedidaID: 5=Gramo, 6=Litro/ml, 3=Unidad, StockActual, StockMinimo)
    ("Queso Seco Chontaleño (Rallado)", 5, Decimal('45000.00'), Decimal('10000.00')),
    ("Harina de Maíz Nixtamalizado", 5, Decimal('35000.00'), Decimal('8000.00')),
    ("Cacao Nicaragüense Tostado y Molido", 5, Decimal('25000.00'), Decimal('5000.00')),
    ("Harina de Maíz Tostado para Pinolillo", 5, Decimal('20000.00'), Decimal('4000.00')),
    ("Harina de Cebada Nicaragüense", 5, Decimal('18000.00'), Decimal('4000.00')),
    ("Café Molido Matagalpa Especial", 5, Decimal('15000.00'), Decimal('3000.00')),
    ("Banano Maduro Criollo", 5, Decimal('30000.00'), Decimal('5000.00')),
    ("Huevos de Granja Frescos", 3, Decimal('1200.00'), Decimal('200.00')),
    ("Jarabe de Frambuesa (Cebada)", 6, Decimal('8000.00'), Decimal('2000.00')),
    ("Vaso Desechable 16oz con Tapa", 3, Decimal('2500.00'), Decimal('500.00')),
    ("Vaso Térmico 8oz (Café)", 3, Decimal('1800.00'), Decimal('400.00')),
    ("Bolsa de Papel Kraft (Panadería)", 3, Decimal('5000.00'), Decimal('1000.00')),
]


def seed_materias_primas(cur):
    log("Verificando materias primas típicas nicaragüenses...")
    mp_map = {}
    for nombre, um_id, stock, stock_min in MATERIAS_PRIMAS_NICA:
        cur.execute("SELECT ID FROM produccion.MateriaPrima WHERE Nombre = ?", nombre)
        row = cur.fetchone()
        if row:
            mp_map[nombre] = row[0]
        else:
            cur.execute("""
                SET NOCOUNT ON; INSERT INTO produccion.MateriaPrima (Nombre, UnidadMedidaID, StockActual, StockMinimo)
                VALUES (?, ?, ?, ?);
                SELECT SCOPE_IDENTITY();
            """, nombre, um_id, stock, stock_min)
            mp_map[nombre] = int(cur.fetchone()[0])
    cur.execute("SELECT ID, Nombre FROM produccion.MateriaPrima")
    for r in cur.fetchall():
        mp_map[r[1]] = r[0]
    return mp_map


# ==============================================================================
# 2. PRODUCTOS Y RECETAS TÍPICOS DE BARRIO EN NICARAGUA
# ==============================================================================
# Categorías: 1=Pan Salado, 2=Pan Dulce, 3=Reposteria, 4=Bebidas, 6=Galletas
PRODUCTOS_NICA = [
    # (Nombre, CategoriaID, PrecioBase, TasaIVA, MotivoExencion, [ (MateriaPrima, CantidadNecesaria) ])
    (
        "Pan Simple Tradicional (Unidad)", 1, Decimal('2.50'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Fuerte (Alta Proteína)", Decimal('45.00')), ("Levadura Seca Instantánea", Decimal('1.20')),
         ("Manteca Vegetal", Decimal('2.50')), ("Sal Fina Yodada", Decimal('0.80'))]
    ),
    (
        "Bolsa de Pan Simple (8 Unidades)", 1, Decimal('20.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Fuerte (Alta Proteína)", Decimal('360.00')), ("Levadura Seca Instantánea", Decimal('9.60')),
         ("Manteca Vegetal", Decimal('20.00')), ("Bolsa Plástica Transparente (Pan)", Decimal('1.00'))]
    ),
    (
        "Pico Dulce con Queso Tradicional", 2, Decimal('10.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Suave (Repostería)", Decimal('50.00')), ("Queso Seco Chontaleño (Rallado)", Decimal('18.00')),
         ("Azúcar Blanca Sulfatada", Decimal('15.00')), ("Mantequilla Lavada", Decimal('8.00')),
         ("Levadura Seca Instantánea", Decimal('1.50'))]
    ),
    (
        "Perrerreche de Maíz y Queso", 2, Decimal('15.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina de Maíz Nixtamalizado", Decimal('60.00')), ("Queso Seco Chontaleño (Rallado)", Decimal('25.00')),
         ("Azúcar Moreno", Decimal('20.00')), ("Mantequilla Lavada", Decimal('12.00')),
         ("Leche Fluida Entera", Decimal('30.00')), ("Canela Molida", Decimal('1.00'))]
    ),
    (
        "Semita Criolla con Azúcar", 2, Decimal('8.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Suave (Repostería)", Decimal('45.00')), ("Azúcar Blanca Sulfatada", Decimal('14.00')),
         ("Manteca Vegetal", Decimal('10.00')), ("Levadura Seca Instantánea", Decimal('1.20'))]
    ),
    (
        "Polvorón Nica de Canela", 6, Decimal('7.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Suave (Repostería)", Decimal('35.00')), ("Azúcar Blanca Sulfatada", Decimal('12.00')),
         ("Manteca Vegetal", Decimal('12.00')), ("Canela Molida", Decimal('0.80'))]
    ),
    (
        "Oreja Crujiente de Azúcar", 2, Decimal('10.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Suave (Repostería)", Decimal('40.00')), ("Margarina para Hojaldre", Decimal('20.00')),
         ("Azúcar Blanca Sulfatada", Decimal('15.00')), ("Sal Fina Yodada", Decimal('0.50'))]
    ),
    (
        "Pan de Banano Casero (Porción)", 2, Decimal('18.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Suave (Repostería)", Decimal('45.00')), ("Banano Maduro Criollo", Decimal('50.00')),
         ("Azúcar Moreno", Decimal('18.00')), ("Margarina Industrial (Clásica)", Decimal('12.00')),
         ("Canela Molida", Decimal('0.50')), ("Polvo para Hornear", Decimal('1.00'))]
    ),
    (
        "Pan de Banano Entero (Molde)", 2, Decimal('140.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Suave (Repostería)", Decimal('350.00')), ("Banano Maduro Criollo", Decimal('400.00')),
         ("Azúcar Moreno", Decimal('140.00')), ("Margarina Industrial (Clásica)", Decimal('90.00')),
         ("Canela Molida", Decimal('4.00')), ("Polvo para Hornear", Decimal('8.00'))]
    ),
    (
        "Quesadilla Tradicional de Queso", 2, Decimal('15.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina de Maíz Nixtamalizado", Decimal('50.00')), ("Queso Seco Chontaleño (Rallado)", Decimal('30.00')),
         ("Leche Fluida Entera", Decimal('25.00')), ("Mantequilla Lavada", Decimal('10.00')),
         ("Azúcar Blanca Sulfatada", Decimal('12.00'))]
    ),
    (
        "Pan de Yema Tradicional", 2, Decimal('6.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Suave (Repostería)", Decimal('40.00')), ("Mantequilla Lavada", Decimal('8.00')),
         ("Azúcar Blanca Sulfatada", Decimal('8.00')), ("Levadura Seca Instantánea", Decimal('1.00')),
         ("Colorante Amarillo Huevo", Decimal('0.20'))]
    ),
    (
        "Queque Casero de Vainilla (Porción)", 2, Decimal('25.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Suave (Repostería)", Decimal('60.00')), ("Azúcar Blanca Sulfatada", Decimal('25.00')),
         ("Mantequilla Lavada", Decimal('15.00')), ("Leche Fluida Entera", Decimal('20.00')),
         ("Esencia de Vainilla Clara", Decimal('1.50')), ("Polvo para Hornear", Decimal('1.50'))]
    ),
    (
        "Empanada Dulce de Piña", 2, Decimal('12.00'), Decimal('0.00'),
        "Exento Canasta Básica Art. 127 numeral 1 LCT",
        [("Harina Suave (Repostería)", Decimal('45.00')), ("Mermelada de Piña Horneable", Decimal('25.00')),
         ("Manteca Vegetal", Decimal('15.00')), ("Azúcar Blanca Sulfatada", Decimal('8.00'))]
    ),
    (
        "Torta Tres Leches Personal", 3, Decimal('75.00'), Decimal('15.00'), None,
        [("Premezcla Pastel Vainilla", Decimal('70.00')), ("Leche Evaporada", Decimal('40.00')),
         ("Leche Condensada", Decimal('40.00')), ("Crema Dulce (Para Batir/Chantilly)", Decimal('30.00')),
         ("Canela Molida", Decimal('0.50')), ("Cerezas en Almíbar", Decimal('5.00'))]
    ),
    (
        "Pio Quinto Tradicional (Porción)", 3, Decimal('45.00'), Decimal('15.00'), None,
        [("Harina de Maíz Nixtamalizado", Decimal('40.00')), ("Leche Fluida Entera", Decimal('60.00')),
         ("Azúcar Blanca Sulfatada", Decimal('25.00')), ("Canela Molida", Decimal('1.00')),
         ("Esencia de Vainilla Oscura", Decimal('1.00'))]
    ),
    (
        "Pastel 1 Lb Vainilla con Dulce de Leche", 3, Decimal('380.00'), Decimal('15.00'), None,
        [("Premezcla Pastel Vainilla", Decimal('450.00')), ("Dulce de Leche (Manjar)", Decimal('200.00')),
         ("Crema Dulce (Para Batir/Chantilly)", Decimal('250.00')), ("Domo Plástico para Pastel 1 Lb", Decimal('1.00')),
         ("Base de Cartón 10\"", Decimal('1.00'))]
    ),
    (
        "Pastel 2 Lbs Fiesta de Chocolate", 3, Decimal('750.00'), Decimal('15.00'), None,
        [("Premezcla Pastel de Chocolate", Decimal('900.00')), ("Chocolate Cobertura (Tableta)", Decimal('300.00')),
         ("Crema Dulce (Para Batir/Chantilly)", Decimal('450.00')), ("Cerezas en Almíbar", Decimal('30.00')),
         ("Base de Cartón 10\"", Decimal('1.00'))]
    ),
    (
        "Cacao con Leche Frío 16oz", 4, Decimal('35.00'), Decimal('15.00'), None,
        [("Cacao Nicaragüense Tostado y Molido", Decimal('35.00')), ("Leche Fluida Entera", Decimal('300.00')),
         ("Azúcar Blanca Sulfatada", Decimal('25.00')), ("Canela Molida", Decimal('0.50')),
         ("Vaso Desechable 16oz con Tapa", Decimal('1.00'))]
    ),
    (
        "Pinolillo con Leche Frío 16oz", 4, Decimal('30.00'), Decimal('15.00'), None,
        [("Harina de Maíz Tostado para Pinolillo", Decimal('30.00')), ("Leche Fluida Entera", Decimal('300.00')),
         ("Azúcar Blanca Sulfatada", Decimal('25.00')), ("Vaso Desechable 16oz con Tapa", Decimal('1.00'))]
    ),
    (
        "Fresco de Cebada Nica 16oz", 4, Decimal('25.00'), Decimal('15.00'), None,
        [("Harina de Cebada Nicaragüense", Decimal('25.00')), ("Leche Fluida Entera", Decimal('200.00')),
         ("Azúcar Blanca Sulfatada", Decimal('25.00')), ("Jarabe de Frambuesa (Cebada)", Decimal('10.00')),
         ("Vaso Desechable 16oz con Tapa", Decimal('1.00'))]
    ),
    (
        "Café con Leche Caliente 8oz", 4, Decimal('25.00'), Decimal('15.00'), None,
        [("Café Molido Matagalpa Especial", Decimal('15.00')), ("Leche Fluida Entera", Decimal('150.00')),
         ("Azúcar Blanca Sulfatada", Decimal('10.00')), ("Vaso Térmico 8oz (Café)", Decimal('1.00'))]
    ),
    (
        "Café Negro Matagalpino 8oz", 4, Decimal('15.00'), Decimal('15.00'), None,
        [("Café Molido Matagalpa Especial", Decimal('18.00')), ("Azúcar Blanca Sulfatada", Decimal('10.00')),
         ("Vaso Térmico 8oz (Café)", Decimal('1.00'))]
    ),
    (
        "Gaseosa Milca Roja 500ml", 4, Decimal('22.00'), Decimal('15.00'), None, []
    ),
    (
        "Gaseosa Coca Cola 500ml", 4, Decimal('25.00'), Decimal('15.00'), None, []
    ),
]


def seed_productos_y_recetas(cur, mp_map):
    log("Insertando catálogo de productos nicaragüenses y recetas...")
    prod_map = {}
    for nombre, cat_id, precio, tasa_iva, motivo, receta in PRODUCTOS_NICA:
        cur.execute("SELECT ID FROM catalogo.Productos WHERE Nombre = ?", nombre)
        row = cur.fetchone()
        if row:
            prod_id = row[0]
            cur.execute("""
                UPDATE catalogo.Productos
                SET CategoriaID = ?, PrecioBase = ?, TasaIVA = ?, MotivoExencion = ?, Activo = 1
                WHERE ID = ?
            """, cat_id, precio, tasa_iva, motivo, prod_id)
        else:
            cur.execute("""
                SET NOCOUNT ON; INSERT INTO catalogo.Productos (Nombre, CategoriaID, PrecioBase, EsFicticio, PorcentajeDescuento,
                                                Activo, CreadoEn, TasaIVA, MotivoExencion)
                VALUES (?, ?, ?, 0, 0, 1, '2023-11-01', ?, ?);
                SELECT SCOPE_IDENTITY();
            """, nombre, cat_id, precio, tasa_iva, motivo)
            prod_id = int(cur.fetchone()[0])
        prod_map[nombre] = {"id": prod_id, "precio": precio, "tasa_iva": tasa_iva, "cat": cat_id}

        # Asociar receta
        for mat_nombre, cant in receta:
            mat_id = mp_map.get(mat_nombre)
            if mat_id:
                cur.execute("""
                    SELECT 1 FROM produccion.RecetaProducto WHERE ProductoID = ? AND MateriaPrimaID = ?
                """, prod_id, mat_id)
                if not cur.fetchone():
                    cur.execute("""
                        INSERT INTO produccion.RecetaProducto (ProductoID, MateriaPrimaID, CantidadNecesaria)
                        VALUES (?, ?, ?)
                    """, prod_id, mat_id, cant)

    # Añadir productos existentes al mapa para ventas
    cur.execute("SELECT ID, Nombre, PrecioBase, TasaIVA, CategoriaID FROM catalogo.Productos WHERE Activo = 1")
    for r in cur.fetchall():
        prod_map[r[1]] = {"id": r[0], "precio": Decimal(str(r[2])), "tasa_iva": Decimal(str(r[3] or 0)), "cat": r[4]}
    return prod_map


# ==============================================================================
# 3. PROVEEDORES LOCALES
# ==============================================================================
PROVEEDORES_NICA = [
    ("Harinera Monisa S.A.", "+505 2249-1000", True),
    ("Lácteos Prolacsa / Chontales", "+505 2512-2233", True),
    ("Distribuidora San Sebastián (Insumos Repostería)", "+505 2266-4455", True),
    ("Central de Abastos El Mayoreo (Granos y Frutas)", "+505 8899-7711", True),
    ("Café Las Flores Matagalpa", "+505 2772-8899", True),
    ("Embotelladora Nacional (Coca Cola & Milca)", "+505 2269-0011", True),
]


def seed_proveedores(cur):
    log("Insertando proveedores locales de insumos...")
    prov_ids = []
    for nombre, tel, activo in PROVEEDORES_NICA:
        cur.execute("SELECT ID FROM produccion.Proveedores WHERE Nombre = ?", nombre)
        row = cur.fetchone()
        if row:
            prov_ids.append(row[0])
        else:
            cur.execute("""
                SET NOCOUNT ON; INSERT INTO produccion.Proveedores (Nombre, Telefono, Activo)
                VALUES (?, ?, ?);
                SELECT SCOPE_IDENTITY();
            """, nombre, tel, activo)
            prov_ids.append(int(cur.fetchone()[0]))
    return prov_ids


# ==============================================================================
# 4. CLIENTES NICARAGÜENSES DEL BARRIO Y CIUDAD
# ==============================================================================
CLIENTES_NICA = [
    ("Doña Rosa", "Mendoza Guido", "+505 8845-1201", "Femenino"),
    ("Carlos Alberto", "Centeno Altamirano", "+505 8712-3490", "Masculino"),
    ("Lic. Marlene", "Espinoza Somarriba", "+505 8420-9911", "Femenino"),
    ("Don Silvio", "Baltodano Jarquín", "+505 8891-2345", "Masculino"),
    ("Prof. Claudia", "Gutiérrez Blandón", "+505 8604-5512", "Femenino"),
    ("Ing. Roberto", "López Solís", "+505 8411-8890", "Masculino"),
    ("Yolanda del Socorro", "Navarrete Calero", "+505 8734-1189", "Femenino"),
    ("Javier Enrique", "Mayorga Zeledón", "+505 8922-3344", "Masculino"),
    ("María Auxiliadora", "Pérez Morales", "+505 8815-4422", "Femenino"),
    ("Dr. Fernando", "Argüello Lacayo", "+505 8409-7733", "Masculino"),
    ("Norma Elena", "Torres Vado", "+505 8623-4411", "Femenino"),
    ("Marcos Antonio", "Reyes Carcache", "+505 8790-2210", "Masculino"),
    ("Brenda Lucía", "Castillo Arana", "+505 8833-6677", "Femenino"),
    ("Gustavo Adolfo", "Sequeira Munguía", "+505 8456-1122", "Masculino"),
    ("Esperanza del Carmen", "Hernández Rivas", "+505 8788-9900", "Femenino"),
    ("Denis José", "Montenegro Dávila", "+505 8820-4455", "Masculino"),
    ("Silvia Regina", "Téllez Barberena", "+505 8619-3388", "Femenino"),
    ("Guillermo", "García Chamorro", "+505 8433-2211", "Masculino"),
    ("Fabiola Patricia", "Umaña Romero", "+505 8755-6644", "Femenino"),
    ("Ricardo José", "Salgado Valle", "+505 8866-1133", "Masculino"),
    ("Carmen María", "Pineda Cuadra", "+505 8644-8822", "Femenino"),
    ("Héctor Manuel", "Báez Orozco", "+505 8488-7711", "Masculino"),
    ("Lilliam de los Ángeles", "Mejía Solórzano", "+505 8701-4455", "Femenino"),
    ("Álvaro José", "Fletes Fonseca", "+505 8877-2299", "Masculino"),
    ("Patricia Auxiliadora", "Vargas Benavides", "+505 8632-1177", "Femenino"),
    ("Manuel Salvador", "Borge Rostrán", "+505 8477-9933", "Masculino"),
    ("Geraldine", "Midence Arévalo", "+505 8766-3322", "Femenino"),
    ("César Augusto", "Bermúdez Cardenal", "+505 8802-5544", "Masculino"),
    ("Vilma Rosa", "Cabrera Talavera", "+505 8655-7799", "Femenino"),
    ("Edwin Ramón", "Zepeda Obando", "+505 8499-1144", "Masculino"),
]


def seed_clientes(cur):
    log("Insertando clientes nicaragüenses frecuentes...")
    client_ids = [1]  # Cliente Invitado
    for nombre, apellidos, tel, gen in CLIENTES_NICA:
        cur.execute("SELECT ID FROM crm.Clientes WHERE Telefono = ?", tel)
        row = cur.fetchone()
        if row:
            client_ids.append(row[0])
        else:
            cur.execute("""
                SET NOCOUNT ON; INSERT INTO crm.Clientes (Nombre, Apellidos, Telefono, NivelConfianzaID, TotalCompras,
                                          CreadoEn, EsInvitado, Genero, FechaNacimiento)
                VALUES (?, ?, ?, 2, 0, '2023-11-01', 0, ?, '1988-06-15');
                SELECT SCOPE_IDENTITY();
            """, nombre, apellidos, tel, gen)
            client_ids.append(int(cur.fetchone()[0]))
    return client_ids


# ==============================================================================
# 5. RECURSOS HUMANOS: HISTORIA DE EMPLEADOS Y NÓMINAS (3 AÑOS)
# ==============================================================================
EMPLEADOS_NICA = [
    # (NombreCompleto, Cedula, Cargo, SalarioBase, FechaIngreso, UsuarioID)
    ("Don José Santos Flores", "001-120568-0021A", "Maestro Panadero", Decimal('14500.00'), date(2023, 11, 1), 7),
    ("Katherine Vanessa Morales", "001-240899-0045B", "Cajero", Decimal('9500.00'), date(2023, 11, 1), 6),
    ("Martha Lorena Gutiérrez", "001-150385-0012F", "Panadero Senior", Decimal('13000.00'), date(2024, 2, 1), None),
    ("Bryan Alexander Ruiz", "001-091102-0033K", "Panadero", Decimal('8800.00'), date(2024, 6, 1), None),
    ("Carlos Manuel Alemán", "001-180795-0019T", "Limpieza", Decimal('9200.00'), date(2024, 10, 1), None),
    ("Mayling Junieth García", "001-030401-0028R", "Cajero", Decimal('9500.00'), date(2025, 3, 1), 16),
    ("Noel Antonio López", "001-280990-0015W", "Panadero", Decimal('12000.00'), date(2025, 9, 1), 10),
]


def calcular_nomina_nica(salario_mensual):
    """
    Cálculo legal nicaragüense:
    - INSS Laboral: 7%
    - IR Mensual Ley 822: Exento los primeros C$ 100,000 anuales (después de INSS).
      Ingreso neto anual = (Salario - INSS) * 12.
    - INSS Patronal: 21.5%
    - INATEC: 2%
    - Provisiones: Vacaciones (1/12), Aguinaldo (1/12), Indemnización (1/12)
    """
    bruto = salario_mensual
    inss_lab = round(bruto * Decimal('0.07'), 2)
    imponible_mensual = bruto - inss_lab
    imponible_anual = imponible_mensual * 12

    ir_anual = Decimal('0.00')
    if imponible_anual > Decimal('500000.00'):
        ir_anual = Decimal('82500.00') + (imponible_anual - Decimal('500000.00')) * Decimal('0.30')
    elif imponible_anual > Decimal('350000.00'):
        ir_anual = Decimal('45000.00') + (imponible_anual - Decimal('350000.00')) * Decimal('0.25')
    elif imponible_anual > Decimal('200000.00'):
        ir_anual = Decimal('15000.00') + (imponible_anual - Decimal('200000.00')) * Decimal('0.20')
    elif imponible_anual > Decimal('100000.00'):
        ir_anual = (imponible_anual - Decimal('100000.00')) * Decimal('0.15')

    ir_mensual = round(ir_anual / 12, 2)
    neto = bruto - inss_lab - ir_mensual

    inss_pat = round(bruto * Decimal('0.215'), 2)
    inatec = round(bruto * Decimal('0.02'), 2)
    vac = round(bruto / 12, 2)
    agui = round(bruto / 12, 2)
    indem = round(bruto / 12, 2)
    costo_total = bruto + inss_pat + inatec + vac + agui + indem

    return {
        "bruto": bruto, "inss_lab": inss_lab, "ir": ir_mensual, "neto": neto,
        "inss_pat": inss_pat, "inatec": inatec, "vac": vac, "agui": agui, "indem": indem,
        "costo_total": costo_total
    }


def seed_rrhh_3_years(cur):
    log("Verificando empleados y generando 3 años de nóminas históricas...")
    empleados_db = []
    for nom, ced, cargo, sal, fingreso, uid in EMPLEADOS_NICA:
        cur.execute("SELECT ID FROM rrhh.Empleados WHERE Cedula = ?", ced)
        row = cur.fetchone()
        if row:
            emp_id = row[0]
        else:
            cur.execute("""
                SET NOCOUNT ON; INSERT INTO rrhh.Empleados (NombreCompleto, Cedula, FechaNacimiento, Genero, Direccion,
                                           Telefono, NumeroINSS, Cargo, FechaIngreso, TipoContrato,
                                           TipoJornada, SalarioBase, FormaPago, EstadoEmpleado, ConsentimientoDatos,
                                           CreadoEn, UsuarioID, HoraEntrada, HoraSalida)
                VALUES (?, ?, '1985-05-12', 'Masculino', 'Managua, Nicaragua', '+505 8888-0000',
                        '12345678', ?, ?, 'Indefinido', 'Diurna', ?, 'Mensual', 'Activo', 1,
                        ?, ?, '06:00:00', '14:00:00');
                SELECT SCOPE_IDENTITY();
            """, nom, ced, cargo, fingreso, sal, fingreso.isoformat(), uid)
            emp_id = int(cur.fetchone()[0])
        empleados_db.append((emp_id, nom, sal, fingreso))

    # Generar nóminas mensuales desde Noviembre 2023 hasta Octubre 2026 (36 meses)
    total_nominas = 0
    start_date = date(2023, 11, 1)
    end_date = date(2026, 10, 31)

    curr_year = 2023
    curr_month = 11

    while True:
        # Fin de mes
        if curr_month in (1, 3, 5, 7, 8, 10, 12):
            last_day = 31
        elif curr_month in (4, 6, 9, 11):
            last_day = 30
        else:
            last_day = 29 if (curr_year % 4 == 0) else 28

        p_inicio = date(curr_year, curr_month, 1)
        p_fin = date(curr_year, curr_month, last_day)

        if p_inicio > end_date:
            break

        for emp_id, nom, sal, fingreso in empleados_db:
            if fingreso <= p_fin:
                cur.execute("""
                    SELECT ID FROM rrhh.Nomina
                    WHERE EmpleadoID = ? AND PeriodoInicio = ? AND PeriodoFin = ?
                """, emp_id, p_inicio, p_fin)
                if not cur.fetchone():
                    calc = calcular_nomina_nica(sal)
                    cur.execute("""
                        SET NOCOUNT ON; INSERT INTO rrhh.Nomina (
                            EmpleadoID, PeriodoInicio, PeriodoFin, SalarioBruto, HorasExtras, MontoHorasExtras,
                            OtrosIngresos, TotalDevengado, INSSLaboral, IRMensual, PensionAlimenticia,
                            ValesDescontados, OtrasDeducciones, TotalDeducciones, SalarioNeto, INSSPatronal,
                            INATEC, Estado, FechaGeneracion, GeneradoPor, ProvisionVacaciones,
                            ProvisionAguinaldo, ProvisionIndemnizacion, CostoTotalEmpresa, PromedioAsistencia, PromedioPuntualidad
                        ) VALUES (
                            ?, ?, ?, ?, 0, 0,
                            0, ?, ?, ?, 0,
                            0, 0, ?, ?, ?,
                            ?, 'Pagada', ?, 1, ?,
                            ?, ?, ?, 98.50, 96.00
                        );
                        SELECT SCOPE_IDENTITY();
                    """,
                        emp_id, p_inicio, p_fin, calc["bruto"], calc["bruto"], calc["inss_lab"],
                        calc["ir"], (calc["inss_lab"] + calc["ir"]), calc["neto"], calc["inss_pat"],
                        calc["inatec"], f"{p_fin} 17:00:00", calc["vac"], calc["agui"], calc["indem"],
                        calc["costo_total"]
                    )
                    nom_id = int(cur.fetchone()[0])
                    # Detalle
                    cur.execute("""
                        INSERT INTO rrhh.DetalleNomina (NominaID, Concepto, Tipo, Monto, Descripcion)
                        VALUES (?, 'Sueldo Ordinario', 'Ingreso', ?, 'Sueldo base mensual del periodo'),
                               (?, 'INSS Laboral (7%)', 'Deduccion', ?, 'Deducción de seguridad social'),
                               (?, 'IR Salarial', 'Deduccion', ?, 'Retención de impuesto sobre la renta');
                    """, nom_id, calc["bruto"], nom_id, calc["inss_lab"], nom_id, calc["ir"])
                    total_nominas += 1

        curr_month += 1
        if curr_month > 12:
            curr_month = 1
            curr_year += 1

    log(f"Nóminas procesadas/aseguradas: {total_nominas}")


# ==============================================================================
# 6. HISTORIA DE VENTAS, TURNOS DE CAJA Y FACTURAS (36 MESES)
# ==============================================================================
def seed_ventas_3_years(cur, prod_map, client_ids):
    log("Generando 3 años de turnos de caja, facturas, detalles y pagos (Nov 2023 - Oct 2026)...")

    # Lista de productos de alta rotación para armar canastas de compras
    pan_salado_keys = ["Pan Simple Tradicional (Unidad)", "Bolsa de Pan Simple (8 Unidades)", "Bolillo"]
    pan_dulce_keys = [
        "Pico Dulce con Queso Tradicional", "Perrerreche de Maíz y Queso", "Semita Criolla con Azúcar",
        "Polvorón Nica de Canela", "Oreja Crujiente de Azúcar", "Pan de Banano Casero (Porción)",
        "Quesadilla Tradicional de Queso", "Pan de Yema Tradicional", "Panuelito", "Concha de Vainilla"
    ]
    bebidas_keys = [
        "Cacao con Leche Frío 16oz", "Pinolillo con Leche Frío 16oz", "Fresco de Cebada Nica 16oz",
        "Café con Leche Caliente 8oz", "Café Negro Matagalpino 8oz", "Gaseosa Milca Roja 500ml", "Gaseosa Coca Cola 500ml"
    ]
    pasteles_keys = [
        "Torta Tres Leches Personal", "Pio Quinto Tradicional (Porción)", "Pastel Tres Leches (1 Lb)",
        "Pastel 1 Lb Vainilla con Dulce de Leche"
    ]

    total_facturas_insertadas = 0
    total_monto_ventas = Decimal('0.00')

    curr_date = date(2023, 11, 1)
    end_date = date(2026, 8, 1)  # Desde Nov 2023 hasta Ago 2026 (cubriendo los 33 meses que faltaban antes de las existentes)

    factura_seq = 1000

    while curr_date <= end_date:
        # Determinar estacionalidad y año
        year = curr_date.year
        month = curr_date.month
        day = curr_date.day

        # Crecimiento de negocio:
        # Año 1 (2023-2024): 4 a 8 ventas por día simulado
        # Año 2 (2024-2025): 8 a 14 ventas por día
        # Año 3 (2025-2026): 12 a 20 ventas por día
        if year == 2023 or (year == 2024 and month < 11):
            base_ventas = random.randint(4, 7)
        elif year == 2024 or (year == 2025 and month < 11):
            base_ventas = random.randint(7, 12)
        else:
            base_ventas = random.randint(11, 18)

        # Pico festivo nicaragüense:
        # Mayo (Día de la Madre: 28-31 mayo): +60% ventas
        # Diciembre (Purísima 6-8 dic, Navidad 22-25 dic): +80% ventas
        if (month == 5 and day >= 26) or (month == 12 and (6 <= day <= 8 or 20 <= day <= 25)):
            base_ventas = int(base_ventas * 1.8)

        # Crear Turno de Caja para el día
        apertura = datetime.combine(curr_date, time(6, 0))
        cierre = datetime.combine(curr_date, time(20, 0))

        # Check si ya existe turno para este día
        cur.execute("SELECT ID FROM ventas.TurnosCaja WHERE FechaApertura >= ? AND FechaApertura < ?",
                    apertura, apertura + timedelta(days=1))
        row_turno = cur.fetchone()
        if row_turno:
            turno_id = row_turno[0]
        else:
            cur.execute("""
                SET NOCOUNT ON; INSERT INTO ventas.TurnosCaja (UsuarioID, FechaApertura, FechaCierre, EfectivoCalculado,
                                              TransferenciasCalculadas, TotalVentaNeta, Cerrado)
                VALUES (6, ?, ?, 0, 0, 0, 1);
                SELECT SCOPE_IDENTITY();
            """, apertura, cierre)
            turno_id = int(cur.fetchone()[0])

        turno_efectivo = Decimal('0.00')
        turno_transf = Decimal('0.00')

        # Insertar ventas del día
        for v in range(base_ventas):
            factura_seq += 1
            num_fac = f"FAC-HIST-{factura_seq:05d}"
            seg_code = hashlib.sha256(num_fac.encode()).hexdigest()[:10].upper()
            hora_venta = apertura + timedelta(minutes=random.randint(15, 800))
            cliente_id = random.choice(client_ids) if random.random() > 0.4 else 1

            # Armar carrito de compras coherente
            items = []
            # 1) Pan diario siempre
            p_pan = random.choice(pan_salado_keys)
            items.append((p_pan, random.randint(1, 4)))

            # 2) Pan dulce
            if random.random() > 0.25:
                p_dulce = random.choice(pan_dulce_keys)
                items.append((p_dulce, random.randint(1, 6)))

            # 3) Bebida (cacao, café, fresco)
            if random.random() > 0.4:
                p_beb = random.choice(bebidas_keys)
                items.append((p_beb, random.randint(1, 2)))

            # 4) Ocasional pastel o repostería
            if random.random() > 0.75:
                p_past = random.choice(pasteles_keys)
                items.append((p_past, 1))

            subtotal_fac = Decimal('0.00')
            iva_fac = Decimal('0.00')
            detalles_insert = []

            for p_nombre, qty in items:
                p_info = prod_map.get(p_nombre)
                if not p_info:
                    continue
                p_id = p_info["id"]
                p_precio = p_info["precio"]
                p_tasa = p_info["tasa_iva"]

                line_sub = round(p_precio * qty, 2)
                subtotal_fac += line_sub
                if p_tasa > 0:
                    iva_fac += round(line_sub * (p_tasa / Decimal('100.00')), 2)
                detalles_insert.append((p_id, qty, p_precio, line_sub))

            total_fac = subtotal_fac + iva_fac
            metodo_pago = "Efectivo" if (year == 2023 or random.random() > 0.3) else "Transferencia"

            # Insertar Factura
            cur.execute("""
                SET NOCOUNT ON; INSERT INTO ventas.Facturas (
                    NumeroFactura, CodigoSeguimiento, FechaHora, UsuarioID, ClienteID, TurnoID,
                    Subtotal, IVA, Total, EsEncargo, IncluyeRUC, EstadoFiscal
                ) VALUES (?, ?, ?, 6, ?, ?, ?, ?, ?, 0, 0, 'Emitida');
                SELECT SCOPE_IDENTITY();
            """, num_fac, seg_code, hora_venta, cliente_id, turno_id, subtotal_fac, iva_fac, total_fac)
            fac_id = int(cur.fetchone()[0])

            # Insertar Detalles
            for p_id, qty, unit_pr, l_sub in detalles_insert:
                cur.execute("""
                    INSERT INTO ventas.DetalleFacturas (FacturaID, ProductoID, Cantidad, PrecioUnitario, Subtotal)
                    VALUES (?, ?, ?, ?, ?)
                """, fac_id, p_id, qty, unit_pr, l_sub)

            # Insertar Pago
            cur.execute("""
                INSERT INTO ventas.Pagos (
                    FacturaID, MetodoPago, Monto, FechaPago, MonedaRegistro, TipoCambioAplicado,
                    TurnoReceptorID, UsuarioReceptorID
                ) VALUES (?, ?, ?, ?, 'NIO', 36.62, ?, 6)
            """, fac_id, metodo_pago, total_fac, hora_venta, turno_id)

            if metodo_pago == "Efectivo":
                turno_efectivo += total_fac
            else:
                turno_transf += total_fac

            total_facturas_insertadas += 1
            total_monto_ventas += total_fac

        # Actualizar totales del turno
        cur.execute("""
            UPDATE ventas.TurnosCaja
            SET EfectivoCalculado = EfectivoCalculado + ?,
                TransferenciasCalculadas = TransferenciasCalculadas + ?,
                TotalVentaNeta = TotalVentaNeta + ?
            WHERE ID = ?
        """, turno_efectivo, turno_transf, (turno_efectivo + turno_transf), turno_id)

        # Avanzar día
        curr_date += timedelta(days=1)

    log(f"Facturas históricas insertadas: {total_facturas_insertadas} (Monto total: C$ {total_monto_ventas:,.2f})")


# ==============================================================================
# 7. PERÍODOS Y REVISIONES FISCALES DGI (36 MESES)
# ==============================================================================
def seed_fiscal_dgi_3_years(cur):
    log("Generando y aprobando 36 períodos de auditoría fiscal DGI (Nov 2023 - Oct 2026)...")
    curr_year = 2023
    curr_month = 11

    periodos_creados = 0
    for _ in range(36):
        if curr_month in (1, 3, 5, 7, 8, 10, 12):
            ld = 31
        elif curr_month in (4, 6, 9, 11):
            ld = 30
        else:
            ld = 29 if (curr_year % 4 == 0) else 28

        f_desde = date(curr_year, curr_month, 1)
        f_hasta = date(curr_year, curr_month, ld)

        # Periodo
        cur.execute("SELECT ID FROM fiscal.DGI_Periodos WHERE Desde = ? AND Hasta = ?", f_desde, f_hasta)
        row = cur.fetchone()
        if row:
            per_id = row[0]
        else:
            cur.execute("""
                SET NOCOUNT ON; INSERT INTO fiscal.DGI_Periodos (Desde, Hasta, Estado, CreadoPor, CreadoEn)
                VALUES (?, ?, 'Aprobado', 1, SYSUTCDATETIME());
                SELECT SCOPE_IDENTITY();
            """, f_desde, f_hasta)
            per_id = int(cur.fetchone()[0])
            periodos_creados += 1

        # Resumen de ventas del periodo para el Formulario DGI 106
        cur.execute("""
            SELECT ISNULL(SUM(Subtotal), 0), ISNULL(SUM(IVA), 0), ISNULL(SUM(Total), 0)
            FROM ventas.Facturas
            WHERE FechaHora >= ? AND FechaHora < ? AND (EstadoFiscal IS NULL OR EstadoFiscal = 'Emitida')
        """, datetime.combine(f_desde, time(0, 0)), datetime.combine(f_hasta + timedelta(days=1), time(0, 0)))
        ventas_row = cur.fetchone()
        subt = float(ventas_row[0])
        iva = float(ventas_row[1])
        tot = float(ventas_row[2])

        anticipo_ir = round(subt * 0.01, 2)  # 1% anticipo IR s/ventas brutas régimen general

        # Revision DGI F-106
        cur.execute("SELECT ID FROM fiscal.DGI_Revisiones WHERE PeriodoID = ? AND Obligacion = 'F-106 Declaracion Mensual'", per_id)
        if not cur.fetchone():
            snapshot = {
                "periodo": f"{curr_year}-{curr_month:02d}",
                "ventas_exentas_canasta_basica": round(subt * 0.65, 2),
                "ventas_gravadas_reposteria_bebidas": round(subt * 0.35, 2),
                "iva_debito_15": iva,
                "anticipo_ir_mensual_1": anticipo_ir,
                "total_facturado": tot
            }
            resultado = {
                "valido": True,
                "estado": "Aprobado",
                "fecha_revision": f"{f_hasta}T18:00:00",
                "nota": "Conciliación fiscal DGI conforme a Ley de Concertación Tributaria de Nicaragua."
            }
            huella = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:64]
            cur.execute("""
                INSERT INTO fiscal.DGI_Revisiones (
                    PeriodoID, Obligacion, Version, Motor, Huella, SnapshotJSON, ResultadoJSON,
                    Estado, CreadoPor, CreadoEn, RevisadoPor, RevisadoEn, NotaRevision, AprobadoPor, AprobadoEn
                ) VALUES (
                    ?, 'F-106 Declaracion Mensual', 1, 'MotorFiscalNica_V1', ?, ?, ?,
                    'Aprobada', 1, SYSUTCDATETIME(), 1, SYSUTCDATETIME(),
                    'Validación mensual conforme con cierres de caja y libro de ventas.', 1, SYSUTCDATETIME()
                )
            """, per_id, huella, json.dumps(snapshot), json.dumps(resultado))

        curr_month += 1
        if curr_month > 12:
            curr_month = 1
            curr_year += 1

    log(f"Períodos DGI asegurados: {periodos_creados} nuevos.")


# ==============================================================================
# 8. CONTABILIDAD: 36 MESES DE ASIENTOS DE DIARIO CUADRADOS
# ==============================================================================
def seed_contabilidad_3_years(cur):
    log("Generando períodos contables y asientos de diario cuadrados (36 meses)...")
    curr_year = 2023
    curr_month = 11

    asientos_creados = 0
    for _ in range(36):
        if curr_month in (1, 3, 5, 7, 8, 10, 12):
            ld = 31
        elif curr_month in (4, 6, 9, 11):
            ld = 30
        else:
            ld = 29 if (curr_year % 4 == 0) else 28

        f_desde = date(curr_year, curr_month, 1)
        f_hasta = date(curr_year, curr_month, ld)

        # Periodo Contable
        cur.execute("SELECT ID FROM contabilidad.PeriodosContables WHERE Mes = ? AND Anio = ?", curr_month, curr_year)
        row = cur.fetchone()
        if row:
            cont_per_id = row[0]
        else:
            cur.execute("""
                SET NOCOUNT ON; INSERT INTO contabilidad.PeriodosContables (Mes, Anio, Estado, FechaApertura, FechaCierre, CerradoPor, CierreUtilidad, CerradoEn)
                VALUES (?, ?, 'Cerrado', ?, ?, 1, 15000.00, ?);
                SELECT SCOPE_IDENTITY();
            """, curr_month, curr_year, f_desde, f_hasta, datetime.combine(f_hasta, time(23, 59)))
            cont_per_id = int(cur.fetchone()[0])

        # Obtener ventas del mes para generar asiento
        cur.execute("""
            SELECT ISNULL(SUM(Subtotal), 0), ISNULL(SUM(IVA), 0), ISNULL(SUM(Total), 0)
            FROM ventas.Facturas
            WHERE FechaHora >= ? AND FechaHora < ? AND (EstadoFiscal IS NULL OR EstadoFiscal = 'Emitida')
        """, datetime.combine(f_desde, time(0, 0)), datetime.combine(f_hasta + timedelta(days=1), time(0, 0)))
        ventas_row = cur.fetchone()
        subt = Decimal(str(ventas_row[0]))
        iva = Decimal(str(ventas_row[1]))
        tot = Decimal(str(ventas_row[2]))

        if tot > 0:
            ref = f"VENTAS-{curr_year}-{curr_month:02d}"
            cur.execute("SELECT ID FROM contabilidad.AsientosDiario WHERE ReferenciaExterna = ?", ref)
            if not cur.fetchone():
                fecha_asiento = datetime.combine(f_hasta, time(18, 0))
                # Asiento de Ventas Mensuales:
                # DEBE: Caja General (C$) [ID=1] = Total
                # HABER: Ventas de Pan y Repostería [ID=7] = Subtotal
                # HABER: IVA Débito Fiscal (15%) [ID=5] = IVA
                cur.execute("""
                    SET NOCOUNT ON; INSERT INTO contabilidad.AsientosDiario (
                        PeriodoID, Fecha, Descripcion, ReferenciaExterna, TipoDocumento,
                        Estado, UsuarioID, FechaCreacion, NumeroComprobante
                    ) VALUES (
                        ?, ?, ?, ?, 'ComprobanteDiario',
                        'Mayorizado', 1, ?, ?
                    );
                    SELECT SCOPE_IDENTITY();
                """, cont_per_id, fecha_asiento, f"Cierre mensual de ventas {curr_month:02d}/{curr_year}",
                    ref, fecha_asiento, f"CD-{curr_year}{curr_month:02d}-01")
                asiento_id = int(cur.fetchone()[0])

                # Detalle asiento (100% balanceado Debe = Haber)
                cur.execute("""
                    INSERT INTO contabilidad.DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                    VALUES (?, 1, ?, 0.00, 'Ingreso total a Caja por ventas de panadería y repostería'),
                           (?, 7, 0.00, ?, 'Ventas netas del periodo'),
                           (?, 5, 0.00, ?, 'IVA débito fiscal generado');
                """, asiento_id, tot, asiento_id, subt, asiento_id, iva)
                asientos_creados += 1

                # Asiento de Costo de Ventas e Inventario:
                # Costo estimado ~45% de las ventas
                costo_mat = round(subt * Decimal('0.45'), 2)
                ref_costo = f"COSTO-{curr_year}-{curr_month:02d}"
                cur.execute("""
                    SET NOCOUNT ON; INSERT INTO contabilidad.AsientosDiario (
                        PeriodoID, Fecha, Descripcion, ReferenciaExterna, TipoDocumento,
                        Estado, UsuarioID, FechaCreacion, NumeroComprobante
                    ) VALUES (
                        ?, ?, ?, ?, 'ComprobanteDiario',
                        'Mayorizado', 1, ?, ?
                    );
                    SELECT SCOPE_IDENTITY();
                """, cont_per_id, fecha_asiento, f"Costo de producción y materia prima {curr_month:02d}/{curr_year}",
                    ref_costo, fecha_asiento, f"CD-{curr_year}{curr_month:02d}-02")
                asiento_costo_id = int(cur.fetchone()[0])

                # DEBE: Costo de Materia Prima Consumida [ID=8]
                # HABER: Inventario de Materia Prima [ID=21]
                cur.execute("""
                    INSERT INTO contabilidad.DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                    VALUES (?, 8, ?, 0.00, 'Reconocimiento de costo de harina, manteca, queso e insumos'),
                           (?, 21, 0.00, ?, 'Descargo de inventario por producción vendida');
                """, asiento_costo_id, costo_mat, asiento_costo_id, costo_mat)
                asientos_creados += 1

        curr_month += 1
        if curr_month > 12:
            curr_month = 1
            curr_year += 1

    log(f"Asientos de diario creados: {asientos_creados}")


# ==============================================================================
# MAIN RUNNER
# ==============================================================================
def main():
    log("======================================================================")
    log("INICIANDO INSERCIÓN HISTÓRICA DE 3 AÑOS (NOV 2023 - NOV 2026)")
    log("Panadería Amada (Brajher's Cake) - Managua, Nicaragua")
    log("======================================================================")

    conn = get_conn()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # 1. Materias primas
        mp_map = seed_materias_primas(cur)
        conn.commit()

        # 2. Productos y recetas
        prod_map = seed_productos_y_recetas(cur, mp_map)
        conn.commit()

        # 3. Proveedores
        prov_ids = seed_proveedores(cur)
        conn.commit()

        # 4. Clientes
        client_ids = seed_clientes(cur)
        conn.commit()

        # 5. Recursos Humanos
        seed_rrhh_3_years(cur)
        conn.commit()

        # 6. Ventas y Facturas
        seed_ventas_3_years(cur, prod_map, client_ids)
        conn.commit()

        # 7. DGI Fiscal
        seed_fiscal_dgi_3_years(cur)
        conn.commit()

        # 8. Contabilidad
        seed_contabilidad_3_years(cur)
        conn.commit()

        log("======================================================================")
        log("¡INSERCIÓN HISTÓRICA DE 3 AÑOS COMPLETADA CON ÉXITO!")
        log("======================================================================")

    except Exception:
        conn.rollback()
        log("ERROR CRÍTICO: Se realizó rollback de la transacción.")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
