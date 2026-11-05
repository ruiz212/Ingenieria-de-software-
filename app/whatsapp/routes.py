"""Management-only WhatsApp inbox. Forms use the application's CSRF extension."""
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pyodbc
from flask import flash, redirect, render_template, request, url_for, session, jsonify, make_response
from flask_login import login_required, current_user
from app.admin import admin_bp
from app.auth.decorators import roles_required
from app.services.validation import required_text
from app.whatsapp.repository import connection, rows, Store
from app.whatsapp.security import verify_admin, SECURITY_PROTOCOLS
from app.whatsapp.linking import public_state, start_local_worker


def _apply_security_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def snapshot(sid=None, *, only_state=False):
    with connection() as (_, cur):
        cur.execute('EXEC crm.sp_WhatsAppLeerControl')
        state = rows(cur)[0]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        state['worker_alive'] = bool(state['Heartbeat'] and state['Heartbeat'] >= now - timedelta(seconds=30))
        if not state['worker_alive']:
            state['Estado'], state['QR'] = 'Worker desconectado', None
            if os.environ.get('PYTHON_DOTENV_DISABLED') != '1':
                try:
                    start_local_worker()
                except Exception:
                    pass
        if not state['QRExpira'] or state['QRExpira'] < now:
            state['QR'] = None
        if only_state:
            return state, [], []
        cur.execute('EXEC crm.sp_WhatsAppListarSesiones')
        sessions = rows(cur)
        messages = []
        if sid:
            cur.execute('EXEC crm.sp_WhatsAppHistorialAdmin ?,?', sid, sid)
            messages = list(reversed(rows(cur)))
        return state, sessions, messages


@admin_bp.get('/whatsapp/estado')
@login_required
@roles_required('Admin', 'SuperAdmin')
def whatsapp_status():
    if os.environ.get('WHATSAPP_ENABLED', '0') != '1':
        response = jsonify(error='La integración está desactivada.')
        response.status_code = 503
    else:
        try:
            chat_id = request.args.get('chat', type=int) or request.headers.get('X-WA-Chat', type=int)
            if chat_id:
                state, sessions, messages = snapshot(chat_id, only_state=False)
                payload = public_state(state)
                payload['sessions'] = [
                    {
                        'ID': s.get('ID'),
                        'Telefono': s.get('Telefono'),
                        'Modo': s.get('Modo'),
                        'Avisos': bool(s.get('Avisos')),
                        'Revision': s.get('Revision'),
                        'UltimaInteraccion': str(s.get('UltimaInteraccion') or '')[:19],
                    }
                    for s in sessions
                ]
                payload['messages'] = [
                    {
                        'Tipo': m.get('Tipo'),
                        'Estado': m.get('Estado'),
                        'Creado': str(m.get('Creado') or '')[:19],
                        'Texto': m.get('Texto') or '',
                        'Imagen': m.get('Imagen') or '',
                    }
                    for m in messages
                ]
            else:
                state, _, _ = snapshot(only_state=True)
                payload = public_state(state)
            response = jsonify(payload)
        except pyodbc.Error:
            response = jsonify(error='No se pudo actualizar la conexión. Vuelva a intentarlo.')
            response.status_code = 503
    return _apply_security_headers(response)


@admin_bp.route('/whatsapp', methods=['GET', 'POST'])
@login_required
@roles_required('Admin', 'SuperAdmin')
def whatsapp():
    sid = request.args.get('chat', type=int)
    installed = os.environ.get('WHATSAPP_ENABLED', '0') == '1'
    state, sessions, messages = {'Activo': False, 'Estado': 'Pendiente de instalación'}, [], []
    if not installed:
        response = make_response(render_template('admin/whatsapp.html', state=public_state(state),
                                                sessions=sessions, messages=messages, sid=sid,
                                                installed=False, protocols=SECURITY_PROTOCOLS))
        return _apply_security_headers(response)
    try:
        if request.method == 'POST':
            action = request.form.get('action')
            if action in ('link', 'unlink'):
                if action == 'unlink' and request.form.get('confirmation', '').strip() != 'DESVINCULAR':
                    raise ValueError('Escriba DESVINCULAR para confirmar que desea retirar la cuenta.')
                verify_admin(current_user, request.form.get('password', ''), request.form.get('otp', '').strip())
                revision = request.form.get('revision', type=int)
                state = Store().request_link('VINCULAR' if action == 'link' else 'DESVINCULAR', revision)
                session.pop('wa_pairing', None)
                if action == 'link':
                    session['wa_pairing'] = {
                        'until': time.time() + 900,
                        'revision': state['ConnectionRevision'],
                        'solicitud_id': state.get('SolicitudID'),
                    }
                # No network connection or native client runs in a Flask request.
                if not state.get('Heartbeat') or state['Heartbeat'] < datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=30):
                    try:
                        started = start_local_worker()
                    except OSError:
                        started = False
                    if not started:
                        flash('Solicitud guardada. El responsable del sistema debe iniciar el servicio de WhatsApp; consulte la guía de instalación.', 'warning')
                flash('Identidad verificada. Espere el QR para escanearlo.' if action == 'link'
                      else 'Desvinculación solicitada. Espere la confirmación antes de agregar otra cuenta.', 'success')
                return redirect(url_for('admin.whatsapp', chat=sid, _anchor='wa-connection-title' if action == 'link' else None))
            with connection() as (_, cur):
                if action == 'global':
                    cur.execute('EXEC crm.sp_WhatsAppActivar ?', request.form.get('enabled') == '1')
                elif action in ('mode', 'reply'):
                    sid = request.form.get('sid', type=int)
                    revision = request.form.get('revision', type=int)
                    cur.execute('EXEC crm.sp_WhatsAppRevision ?', sid)
                    row = cur.fetchone()
                    if not row or row[0] != revision:
                        raise ValueError('La conversación cambió. Actualice la página antes de continuar.')
                    if action == 'mode':
                        mode = request.form.get('mode')
                        if mode not in ('IA', 'HUMANO'):
                            raise ValueError('Modo de atención no válido.')
                        cur.execute('EXEC crm.sp_WhatsAppModo ?,?', mode, sid)
                        if mode == 'IA':
                            # Human-period messages remain visible but are never replayed to AI.
                            cur.execute('EXEC crm.sp_WhatsAppCerrarMensajes ?', sid)
                    else:
                        if row[1] != 'HUMANO':
                            raise ValueError('Tome control de la conversación antes de responder.')
                        text = required_text(request.form.get('text'), 'Respuesta', 3500)
                        Store.enqueue(cur, sid, f'human:{current_user.id}:{uuid4().hex}', text, 'Humano', row[0])
                else:
                    raise ValueError('Acción no válida.')
            flash('Cambios guardados.', 'success')
            return redirect(url_for('admin.whatsapp', chat=sid))
        state, sessions, messages = snapshot(sid)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('admin.whatsapp', chat=sid))
    except pyodbc.Error as exc:
        flash('La conexión cambió o hay una operación pendiente. Actualice el panel antes de continuar.'
              if '52027' in str(exc) else 'No se pudo cargar WhatsApp. Verifique la migración y la conexión SQL.', 'error')
    response = render_template('admin/whatsapp.html', state=public_state(state), sessions=sessions,
                               messages=messages, sid=sid, installed=installed, protocols=SECURITY_PROTOCOLS)
    response = make_response(response)
    return _apply_security_headers(response)
