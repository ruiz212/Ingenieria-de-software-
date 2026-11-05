"""Neonize adapter. Imported lazily; never connects on web startup."""
from pathlib import Path
import logging
from app.services.auth_challenges import normalize_phone
from app.utils.qr import generar_qr_base64
from app.whatsapp.media import save_image


def sender_phone(jid):
    number, _, server = jid.partition('@')
    if server != 's.whatsapp.net' or not number.isdigit():
        raise ValueError('Remitente no telefónico o no individual.')
    return normalize_phone('+' + number)


class Transport:
    def __init__(self, app, store, session_path):
        from neonize.client import NewClient
        from neonize.events import ConnectedEv, DisconnectedEv, LoggedOutEv, MessageEv
        self.client = NewClient(str(session_path))
        self.app, self.store = app, store
        self.status = 'Desconectado'
        self.qr = None

        @self.client.event.qr
        def qr(client, code):
            self.status, self.qr = 'Esperando QR', generar_qr_base64(code)
            with app.app_context():
                store.state(self.status, self.qr)

        @self.client.event(ConnectedEv)
        def connected(client, event):
            self.status, self.qr = 'Conectado', None
            with app.app_context():
                device = client.get_me()
                phone = sender_phone(f'{device.JID.User}@{device.JID.Server}')
                store.account(phone, True)
                store.state(self.status)

        @self.client.event(DisconnectedEv)
        def disconnected(client, event):
            self.status, self.qr = 'Desconectado', None

        @self.client.event(LoggedOutEv)
        def logged_out(client, event):
            self.status, self.qr = 'Requiere vinculación', None
            with app.app_context():
                store.account(None, False)
                store.state(self.status)

        @self.client.event(MessageEv)
        def incoming(client, event):
            try:
                source = event.Info.MessageSource
                if source.IsFromMe or source.IsGroup:
                    return
                sender = source.Sender
                # LID resolution comes from authenticated device storage, never model text.
                if sender.Server == 'lid':
                    sender = client.get_pn_from_lid(sender)
                jid = f'{sender.User}@{sender.Server}'
                phone = sender_phone(jid)
                message = event.Message
                text = message.conversation or message.extendedTextMessage.text
                image = None
                with app.app_context():
                    if message.HasField('imageMessage'):
                        if message.imageMessage.fileLength > 5 * 1024 * 1024:
                            text = 'La imagen enviada supera el máximo permitido de 5 MB.'
                        else:
                            folder = Path(app.static_folder) / 'uploads' / 'referencias'
                            image = 'uploads/referencias/' + save_image(client.download_any(message), folder)
                            text = message.imageMessage.caption or 'Adjunté una imagen de referencia para el pastelero.'
                    if text:
                        store.receive(jid, phone, event.Info.ID, text, image)
            except ValueError:
                logging.getLogger(__name__).warning('Mensaje WhatsApp no admitido; contenido omitido.')
            except Exception:
                logging.getLogger(__name__).exception('No se pudo registrar un mensaje WhatsApp')

    def connect(self):
        self.client.connect()

    def send(self, jid, text):
        from neonize.utils.jid import build_jid
        phone = sender_phone(jid)
        self.client.send_message(build_jid(phone[1:]), text)

    def stop(self):
        self.client.stop()

    def logout(self):
        self.client.logout()
