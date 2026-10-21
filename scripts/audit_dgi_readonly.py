"""Comprueba fuentes por período sin configurar, corregir ni generar revisiones.

python scripts/audit_dgi_readonly.py --connection-env DB_CONNECTION_STRING --mes 2026-10
Sin --mes revisa todos los meses presentes en ventas, compras o asientos.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pyodbc
from dotenv import load_dotenv
from app.services.dgi_engine import ENGINE_VERSION, analyze, monthly_period
from app.services.dgi_repository import snapshot


def inspect(connection, month=None):
    cursor = connection.cursor()
    if month:
        months = [month]
    else:
        cursor.execute('''SELECT DISTINCT CONVERT(char(7),Fecha,126) FROM (
            SELECT FechaHora AS Fecha FROM Facturas UNION ALL SELECT Fecha FROM ComprasMateriaPrima
            UNION ALL SELECT Fecha FROM AsientosDiario) d ORDER BY 1''')
        months = [r[0] for r in cursor.fetchall()]
    connection.rollback()
    report = []
    for value in months:
        start, end = monthly_period(value)
        try:
            cursor.execute('SET TRANSACTION ISOLATION LEVEL SERIALIZABLE; SET LOCK_TIMEOUT 15000;')
            data = snapshot(cursor, {'Desde':start,'Hasta':end}, 'Diagnóstico interno')
            result = analyze(data)
            report.append(dict(mes=value, totales=result['totales'], errores=result['bloqueantes'],
                advertencias=result['advertencias'], pendientes_configuracion=result['pendientes_configuracion'],
                fechas_normalizadas=result['fechas_normalizadas'],
                documentos=dict(ventas=len(data['ventas']),compras=len(data['compras']),asientos=len(data['asientos'])),
                incidencias_datos=[dict(regla=f['codigo'],severidad=f['severidad'],tipo=f['tipo'],id=f['origen_id'])
                    for f in result['hallazgos'] if f['categoria']=='DATOS']))
        finally:
            connection.rollback()
    return dict(motor=ENGINE_VERSION, modo='SOLO LECTURA: no se modifican fuentes, perfil ni revisiones', periodos=report)


if __name__ == '__main__':
    load_dotenv(Path(__file__).resolve().parents[1]/'.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-env', required=True)
    parser.add_argument('--mes')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    connection = pyodbc.connect(os.environ[args.connection_env],timeout=10)
    try:
        result = inspect(connection,args.mes)
    finally:
        connection.rollback()
        connection.cursor().execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED; SET LOCK_TIMEOUT -1;')
        connection.close()
    output = json.dumps(result,ensure_ascii=False,indent=2)
    if args.output:
        args.output.write_text(output+'\n',encoding='utf-8')
    else:
        print(output)
