"""Only channel-owned quotes can be mutated. No phone/SQL/identity model arguments."""
from app.services.validation import required_text, positive_int
from app.whatsapp.policies import delivery_date

FIELDS = {
    'consultar_catalogo': {},
    'obtener_recomendaciones_cliente': {},
    'consultar_mis_cotizaciones': {},
    'agendar_cotizacion_pastel': {'nombre': 'string', 'especificaciones': 'string',
                                'fecha_entrega': 'string', 'confirmed': 'boolean'},
    'responder_cotizacion': {'cotizacion_id': 'integer', 'decision': 'string', 'confirmed': 'boolean'},
    'rastrear_pedido': {'codigo_seguimiento': 'string'},
    'transferir_a_humano': {'motivo': 'string'},
}


class Tools:
    schemas = [{'name': name, 'description': name.replace('_', ' '),
                'parameters': {'type': 'object', 'properties': {k: {'type': t} for k, t in fields.items()},
                               'required': list(fields)}} for name, fields in FIELDS.items()]

    def __init__(self, store, session):
        self.store, self.session = store, session

    def call(self, name, args, key):
        if name not in FIELDS or not isinstance(args, dict) or set(args) - set(FIELDS[name]):
            raise ValueError('Herramienta o argumentos no autorizados.')
        if name in ('agendar_cotizacion_pastel', 'responder_cotizacion') and args.get('confirmed') is not True:
            raise ValueError('Se requiere confirmación explícita de los detalles.')
        if name == 'agendar_cotizacion_pastel':
            args = dict(args, nombre=required_text(args.get('nombre'), 'Nombre', 100),
                        especificaciones=required_text(args.get('especificaciones'), 'Especificaciones', 2000),
                        fecha_entrega=delivery_date(args.get('fecha_entrega')).isoformat())
        elif name == 'responder_cotizacion':
            args = dict(args, cotizacion_id=positive_int(args.get('cotizacion_id'), maximum=2147483647))
            if args.get('decision') not in ('aceptar', 'rechazar'):
                raise ValueError('Decisión no válida.')
        elif name == 'rastrear_pedido':
            args = dict(args, codigo_seguimiento=required_text(args.get('codigo_seguimiento'), 'Código privado', 20))
        elif name == 'transferir_a_humano':
            args = dict(args, motivo=required_text(args.get('motivo'), 'Motivo', 200))
        return self.store.tool(self.session, name, args, key)
