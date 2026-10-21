import json
from app.db import execute_sp


def registrar_auditoria(cursor, usuario_id, accion, entidad, entidad_id=None,
                        datos_antes=None, datos_despues=None, ip=None):
    """Registra cambios de negocio en la bitácora general de auditoría vía SP."""
    antes_str = json.dumps(datos_antes, ensure_ascii=False, default=str) if datos_antes is not None else None
    despues_str = json.dumps(datos_despues, ensure_ascii=False, default=str) if datos_despues is not None else None
    execute_sp(
        cursor,
        'seguridad.sp_RegistrarAuditoria',
        (usuario_id, accion, entidad, entidad_id, antes_str, despues_str, ip),
        fallback_sql=(
            "INSERT INTO AuditLog (UsuarioID, Accion, Entidad, EntidadID, DatosAntes, DatosDespues, IP) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        ),
    )
