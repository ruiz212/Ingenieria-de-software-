import os
import sys
import json
import hashlib
from datetime import datetime, date, timedelta, time
from decimal import Decimal
import pyodbc
from dotenv import load_dotenv

load_dotenv()
CONNECTION_STRING = os.environ.get(
    'DB_CONNECTION_STRING',
    r'DRIVER={ODBC Driver 17 for SQL Server};SERVER=localhost\SQLDEV;DATABASE=PanaderiaDB;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;'
)

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def main():
    log("Iniciando generación de DGI Fiscal y Contabilidad para los 36 meses...")
    conn = pyodbc.connect(CONNECTION_STRING)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # ==============================================================================
        # 1. PERÍODOS Y REVISIONES FISCALES DGI (36 MESES)
        # ==============================================================================
        log("Generando y aprobando 36 períodos de auditoría fiscal DGI (Nov 2023 - Oct 2026)...")
        curr_year = 2023
        curr_month = 11
        periodos_dgi = 0

        for _ in range(36):
            if curr_month in (1, 3, 5, 7, 8, 10, 12):
                ld = 31
            elif curr_month in (4, 6, 9, 11):
                ld = 30
            else:
                ld = 29 if (curr_year % 4 == 0) else 28

            f_desde = date(curr_year, curr_month, 1)
            f_hasta = date(curr_year, curr_month, ld)

            cur.execute("SELECT ID FROM fiscal.DGI_Periodos WHERE Desde = ? AND Hasta = ?", f_desde, f_hasta)
            row = cur.fetchone()
            if row:
                per_id = row[0]
            else:
                cur.execute("""
                    SET NOCOUNT ON;
                    INSERT INTO fiscal.DGI_Periodos (Desde, Hasta, Estado, CreadoPor, CreadoEn)
                    VALUES (?, ?, 'Cerrado', 1, SYSUTCDATETIME());
                    SELECT SCOPE_IDENTITY();
                """, f_desde, f_hasta)
                per_id = int(cur.fetchone()[0])
                periodos_dgi += 1

            # Resumen de ventas del periodo
            cur.execute("""
                SELECT ISNULL(SUM(Subtotal), 0), ISNULL(SUM(IVA), 0), ISNULL(SUM(Total), 0)
                FROM ventas.Facturas
                WHERE FechaHora >= ? AND FechaHora < ? AND (EstadoFiscal IS NULL OR EstadoFiscal = 'Emitida')
            """, datetime.combine(f_desde, time(0, 0)), datetime.combine(f_hasta + timedelta(days=1), time(0, 0)))
            ventas_row = cur.fetchone()
            subt = float(ventas_row[0])
            iva = float(ventas_row[1])
            tot = float(ventas_row[2])
            anticipo_ir = round(subt * 0.01, 2)

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
                    "estado": "APROBADO",
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
                        'APROBADO', 1, SYSUTCDATETIME(), 1, SYSUTCDATETIME(),
                        'Validación mensual conforme con cierres de caja y libro de ventas.', 1, SYSUTCDATETIME()
                    )
                """, per_id, huella, json.dumps(snapshot), json.dumps(resultado))

            curr_month += 1
            if curr_month > 12:
                curr_month = 1
                curr_year += 1

        conn.commit()
        log(f"Períodos DGI generados y asegurados con éxito: {periodos_dgi}")

        # ==============================================================================
        # 2. CONTABILIDAD: 36 MESES DE ASIENTOS DE DIARIO CUADRADOS
        # ==============================================================================
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

            cur.execute("SELECT ID FROM contabilidad.PeriodosContables WHERE Mes = ? AND Anio = ?", curr_month, curr_year)
            row = cur.fetchone()
            if row:
                cont_per_id = row[0]
            else:
                cur.execute("""
                    SET NOCOUNT ON;
                    INSERT INTO contabilidad.PeriodosContables (Mes, Anio, Estado, FechaApertura, FechaCierre, CerradoPor, CierreUtilidad, CerradoEn)
                    VALUES (?, ?, 'Cerrado', ?, ?, 1, 15000.00, ?);
                    SELECT SCOPE_IDENTITY();
                """, curr_month, curr_year, f_desde, f_hasta, datetime.combine(f_hasta, time(23, 59)))
                cont_per_id = int(cur.fetchone()[0])

            # Ventas del mes
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
                    cur.execute("""
                        SET NOCOUNT ON;
                        INSERT INTO contabilidad.AsientosDiario (
                            PeriodoID, Fecha, Descripcion, ReferenciaExterna, TipoDocumento,
                            Estado, UsuarioID, FechaCreacion, NumeroComprobante
                        ) VALUES (
                            ?, ?, ?, ?, 'ComprobanteDiario',
                            'Contabilizado', 1, ?, ?
                        );
                        SELECT SCOPE_IDENTITY();
                    """, cont_per_id, fecha_asiento, f"Cierre mensual de ventas {curr_month:02d}/{curr_year}",
                        ref, fecha_asiento, f"CD-{curr_year}{curr_month:02d}-01")
                    asiento_id = int(cur.fetchone()[0])

                    if iva > 0:
                        cur.execute("""
                            INSERT INTO contabilidad.DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                            VALUES (?, 1, ?, 0.00, 'Ingreso total a Caja por ventas de panadería y repostería'),
                                   (?, 7, 0.00, ?, 'Ventas netas del periodo'),
                                   (?, 5, 0.00, ?, 'IVA débito fiscal generado');
                        """, asiento_id, tot, asiento_id, subt, asiento_id, iva)
                    else:
                        cur.execute("""
                            INSERT INTO contabilidad.DetalleAsientos (AsientoID, CuentaID, Debe, Haber, Descripcion)
                            VALUES (?, 1, ?, 0.00, 'Ingreso total a Caja por ventas de panadería'),
                                   (?, 7, 0.00, ?, 'Ventas netas del periodo (exentas)');
                        """, asiento_id, tot, asiento_id, subt)
                    asientos_creados += 1

                    costo_mat = round(subt * Decimal('0.45'), 2)
                    ref_costo = f"COSTO-{curr_year}-{curr_month:02d}"
                    cur.execute("""
                        SET NOCOUNT ON;
                        INSERT INTO contabilidad.AsientosDiario (
                            PeriodoID, Fecha, Descripcion, ReferenciaExterna, TipoDocumento,
                            Estado, UsuarioID, FechaCreacion, NumeroComprobante
                        ) VALUES (
                            ?, ?, ?, ?, 'ComprobanteDiario',
                            'Contabilizado', 1, ?, ?
                        );
                        SELECT SCOPE_IDENTITY();
                    """, cont_per_id, fecha_asiento, f"Costo de producción y materia prima {curr_month:02d}/{curr_year}",
                        ref_costo, fecha_asiento, f"CD-{curr_year}{curr_month:02d}-02")
                    asiento_costo_id = int(cur.fetchone()[0])

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

        conn.commit()
        log(f"Asientos de diario contables creados y mayorizados: {asientos_creados}")
        log("¡PROCESO COMPLETADO AL 100% EXITOSAMENTE!")

    except Exception:
        conn.rollback()
        log("ERROR al completar DGI y contabilidad")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
