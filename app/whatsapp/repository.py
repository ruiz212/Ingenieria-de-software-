"""Short SQL transactions. All calls use a fresh connection and close its identity."""
import json
from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
from uuid import uuid4
from app.db import get_db_connection, as_db_role


def rows(cursor):
    keys = [c[0] for c in cursor.description] if cursor.description else []
    return [dict(zip(keys, row)) for row in cursor.fetchall()] if keys else []


@contextmanager
def connection(worker=False):
    conn = get_db_connection(inject_context=not worker, apply_role=not worker)
    try:
        cur = conn.cursor()
        if worker:
            cur.execute("EXECUTE AS USER='usr_bd_whatsapp'")
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if worker:
            try:
                conn.cursor().execute('REVERT')
                conn.commit()
            except Exception:
                pass
        conn.close()


class Store:
    def state(self, status=None, qr=None):
        with connection(True) as (_, cur):
            if status:
                cur.execute('EXEC crm.sp_WhatsAppHeartbeat ?,?,?,?', status, qr, qr, qr)
            cur.execute('EXEC crm.sp_WhatsAppLeerControl')
            return rows(cur)[0]

    def receive(self, jid, phone, message_id, text, image=None):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppBuscarSesion ?', jid)
            row = cur.fetchone()
            if not row:
                cur.execute('EXEC crm.sp_WhatsAppCrearSesion ?,?,?', jid, phone, uuid4().hex)
                sid = cur.fetchone()[0]
            else:
                sid = row[0]
            cur.execute('EXEC crm.sp_WhatsAppBuscarMensaje ?,?', sid, message_id)
            if cur.fetchone():
                return False
            cur.execute('EXEC crm.sp_WhatsAppContarRecientes ?', sid)
            if cur.fetchone()[0] >= 6:
                return False
            cur.execute('EXEC crm.sp_WhatsAppInsertarMensaje ?,?,?,?', sid, message_id, text[:4000], image)
            cur.execute('EXEC crm.sp_WhatsAppActualizarImagen ?,?', None, sid)
            return True

    def next_message(self):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppMarcarFallidos')
            cur.execute('EXEC crm.sp_WhatsAppSiguienteMensaje')
            result = rows(cur)
            if not result:
                return None
            item = result[0]
            cur.execute('EXEC crm.sp_WhatsAppIntentarMensaje ?', item['ID'])
            cur.execute('EXEC crm.sp_WhatsAppPrepararMensaje ?,?,?', item['id'], item['Imagen'], item['Texto'])
            return item

    def history(self, sid):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppHistorial ?,?', sid, sid)
            return [{'role': r['Tipo'], 'text': r['Texto']} for r in reversed(rows(cur))]

    def finish(self, item, text):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppRevision ?', item['id'])
            session = cur.fetchone()
            cur.execute('EXEC crm.sp_WhatsAppCompletarMensaje ?', item['ID'])
            if text and session[0] == item['Revision'] and session[1] == 'IA':
                self.enqueue(cur, item['id'], f"reply:{item['ID']}", text, 'IA', session[0])

    @staticmethod
    def enqueue(cur, sid, key, text, kind, revision):
        cur.execute('EXEC crm.sp_WhatsAppEncolar ?,?,?,?,?,?', key, sid, key, text[:4000], kind, revision)

    def command(self, item):
        text = item['Texto'].strip().upper()
        if text not in ('HUMANO', 'AVISOS SI', 'AVISOS SÍ', 'AVISOS NO', 'CONFIRMAR'):
            return False, None
        if text == 'CONFIRMAR':
            with connection(True) as (_, cur):
                cur.execute('EXEC crm.sp_WhatsAppLeerAccion ?', f"confirm:{item['ID']}")
                prior = cur.fetchone()
                if prior:
                    return True, str(json.loads(prior[0]))
            if not item['Pendiente']:
                return True, 'No hay una operación pendiente de confirmar.'
            pending = json.loads(item['Pendiente'])
            if datetime.fromisoformat(pending['expires']) < datetime.now(timezone.utc):
                return True, 'La confirmación venció. Solicita nuevamente la operación para revisar sus detalles.'
            result = self.tool(item, pending['name'], pending['args'], f"confirm:{item['ID']}", confirm=True)
            if 'cotizacion' in result:
                return True, f"Solicitud {result['cotizacion']} registrada. El pastelero revisará el precio."
            return True, f"Cotización COT-{result['cotizacion_id']:04d}: decisión registrada ({result['decision']}). El adelanto y la factura se gestionan en caja."
        with connection(True) as (_, cur):
            if text == 'HUMANO':
                cur.execute('EXEC crm.sp_WhatsAppHandoff ?', item['id'])
                # The acknowledgment is human-mode compatible.
                self.enqueue(cur, item['id'], f"handoff:{item['ID']}", 'Tu conversación está en atención humana.', 'Humano', item['Revision'] + 1)
                return True, None
            cur.execute('EXEC crm.sp_WhatsAppConsentimiento ?,?', text != 'AVISOS NO', item['id'])
            return True, 'Preferencia de avisos actualizada.'

    def tool(self, session, name, args, key, confirm=False):
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppLeerAccion ?', key)
            previous = cur.fetchone()
            if previous:
                return json.loads(previous[0])
            cur.execute('EXEC crm.sp_WhatsAppValidarSesion ?', session['id'])
            current = cur.fetchone()
            if not current or current[0] != 'IA' or current[1] != session['Revision']:
                raise PermissionError('Conversación pausada o modificada.')
            cur.execute('EXEC crm.sp_WhatsAppActivo')
            if not cur.fetchone()[0]:
                raise PermissionError('Bot apagado.')
            if name in ('agendar_cotizacion_pastel', 'responder_cotizacion') and not confirm:
                if name == 'responder_cotizacion':
                    cur.execute('EXEC crm.sp_WhatsAppPrecio ?,?', session['id'], args['cotizacion_id'])
                    quote = cur.fetchone()
                    if not quote or quote[0] is None:
                        raise ValueError('Cotización ajena o no disponible para responder.')
                    args = dict(args, precio_esperado=str(quote[0]))
                pending = json.dumps({'name': name, 'args': args,
                                      'expires': (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}, ensure_ascii=False)
                cur.execute('EXEC crm.sp_WhatsAppBorrador ?,?', pending, session['id'])
                details = (f"Nombre: {args['nombre']}. Pedido: {args['especificaciones']}. Entrega: {args['fecha_entrega']}. Precio pendiente de valoración."
                           if name == 'agendar_cotizacion_pastel' else
                           f"Cotización COT-{args['cotizacion_id']:04d}. Precio: C$ {args['precio_esperado']}. Decisión: {args['decision']}.")
                result = {'requiere_confirmacion': True, 'detalles': args,
                          'mensaje': details + ' Escribe CONFIRMAR para registrar esta operación. Vence en 15 minutos.'}
            elif name == 'agendar_cotizacion_pastel':
                cur.execute('EXEC crm.sp_WhatsAppCotizacion ?,?,?,?,?,?', session['id'], 'crear', None, args['nombre'], args['especificaciones'], args['fecha_entrega'])
                result = {'cotizacion': f'COT-{cur.fetchone()[0]:04d}', 'estado': 'Pendiente'}
            elif name == 'responder_cotizacion':
                cur.execute('EXEC crm.sp_WhatsAppCotizacion ?,?,?,?,?,?,?', session['id'], args['decision'], args['cotizacion_id'], None, None, None, args['precio_esperado'])
                result = {'cotizacion_id': cur.fetchone()[0], 'decision': args['decision']}
            elif name == 'consultar_mis_cotizaciones':
                cur.execute('EXEC crm.sp_WhatsAppCotizacion ?,?', session['id'], 'listar')
                result = rows(cur)
            elif name in ('consultar_catalogo', 'obtener_recomendaciones_cliente'):
                with as_db_role(cur, 'db_rol_portal_cliente'):
                    cur.execute('EXEC catalogo.sp_ObtenerProductosPOS')
                    result = [r for r in rows(cur) if not r['EsFicticio']][:100]
                if name == 'obtener_recomendaciones_cliente':
                    from types import SimpleNamespace
                    from app.services.marketing_repository import store_recommendations, load_marketing_catalog
                    with as_db_role(cur, 'db_rol_portal_cliente'):
                        catalog = load_marketing_catalog(cur)
                        recommended = store_recommendations(cur, catalog, SimpleNamespace(is_authenticated=False))
                    result = {'tipo': 'tendencias generales, sin historial personal', 'productos': recommended}
            elif name == 'rastrear_pedido':
                with as_db_role(cur, 'db_rol_portal_cliente'):
                    cur.execute('EXEC ventas.sp_SeguimientoEncargoPublico ?', args['codigo_seguimiento'])
                    result = rows(cur)
                    # Return only public status, not customer names or reference images.
                    result = [{k: r[k] for k in ('NumeroFactura', 'Estado', 'FechaEntrega', 'Total')} for r in result]
                    cur.execute('EXEC ventas.sp_SeguimientoAdelantoPublico ?', args['codigo_seguimiento'])
                    paid = cur.fetchone()[0]
                    for row in result:
                        row['SaldoPendiente'] = max(0, row['Total'] - paid)
            elif name == 'transferir_a_humano':
                cur.execute('EXEC crm.sp_WhatsAppHandoff ?', session['id'])
                result = {'atencion': 'HUMANO'}
                self.enqueue(cur, session['id'], key + ':handoff', 'Tu conversación está en atención humana.', 'Humano', current[1] + 1)
            else:
                raise ValueError('Herramienta no autorizada.')
            if confirm:
                cur.execute('EXEC crm.sp_WhatsAppLimpiarBorrador ?', session['id'])
            # JSON converts SQL Decimal/datetime without losing their display value.
            payload = json.dumps(result, ensure_ascii=False, default=str)
            cur.execute('EXEC crm.sp_WhatsAppGuardarAccion ?,?,?,?', key, session['id'], name, payload)
            return json.loads(payload)

    def outgoing(self):
        with connection(True) as (_, cur):
            # Singleton worker owns delivery; revision invalidates stale generated responses.
            cur.execute('EXEC crm.sp_WhatsAppCancelarObsoletos')
            cur.execute('EXEC crm.sp_WhatsAppSiguienteEnvio')
            result = rows(cur)
            return result[0] if result else None

    def deliver(self, outgoing, send):
        # Lock only channel state during dispatch. A successful human takeover cannot
        # race with an old AI send; no POS/invoice locks are acquired here.
        with connection(True) as (_, cur):
            cur.execute('EXEC crm.sp_WhatsAppBloquearEnvio ?', outgoing['SesionID'])
            session = cur.fetchone()
            cur.execute('EXEC crm.sp_WhatsAppBloquearControl')
            active = cur.fetchone()[0]
            if not active:
                return
            if ((outgoing['Tipo'] == 'IA' and (session[0] != 'IA' or session[1] != outgoing['Revision']))
                    or (outgoing['Tipo'] == 'Aviso' and not session[2])):
                cur.execute('EXEC crm.sp_WhatsAppCancelarEnvio ?', outgoing['ID'])
                return
            success = False
            try:
                send(outgoing['JID'], outgoing['Texto'])
                success = True
            except Exception:
                import logging
                logging.getLogger(__name__).warning('Envío WhatsApp falló ID=%s', outgoing['ID'])
            cur.execute('EXEC crm.sp_WhatsAppResultadoEnvio ?,?', success, outgoing['ID'])


def notify(cursor, kind, entity_id):
    """Opt-in integration flag prevents querying absent migration in existing installs."""
    import os
    if os.environ.get('WHATSAPP_ENABLED', '0') == '1':
        cursor.execute('EXEC crm.sp_WhatsAppNotificar ?,?', kind, entity_id)
