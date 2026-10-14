import json


def registrar_auditoria(cursor, usuario_id, accion, entidad, entidad_id=None,
                        datos_antes=None, datos_despues=None, ip=None):
    """Registra cambios de negocio en la bitácora general de auditoría."""
    cursor.execute(
        "INSERT INTO AuditLog (UsuarioID, Accion, Entidad, EntidadID, DatosAntes, DatosDespues, IP) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        usuario_id,
        accion,
        entidad,
        entidad_id,
        json.dumps(datos_antes, ensure_ascii=False, default=str) if datos_antes is not None else None,
        json.dumps(datos_despues, ensure_ascii=False, default=str) if datos_despues is not None else None,
        ip
    )
