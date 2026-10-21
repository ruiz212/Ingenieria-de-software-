# Receptores de movimientos de caja históricos

La migración agrega `ventas.Pagos.TurnoReceptorID` y `UsuarioReceptorID` sin completar registros históricos. La factura identifica el turno de emisión, pero no demuestra quién recibió un saldo posterior. Los pagos nuevos guardan su receptor y conservan `FechaPago`. Los arqueos nuevos suman esos movimientos; los arqueos ya registrados no se reescriben.

Si un turno contiene pagos antiguos sin receptor, el conteo responde 409 y solicita conciliación. También bloquea un turno cuyo intervalo de apertura/cierre se superponga a un pago histórico no identificado: podría tratarse de su saldo recibido, aunque la factura se emitiera en otro turno. Esta comprobación sólo solicita revisión, nunca asigna un receptor. Los movimientos de monto cero no bloquean; los turnos abiertos después del pago antiguo pueden operar. Los cobros de saldo requieren la caja abierta del cajero receptor y ninguna solicitud de arqueo pendiente. Operativo puede entregar pedidos totalmente pagados; un cajero debe confirmar primero los saldos pendientes.

Admin o SuperAdmin, con apoyo del responsable contable, debe revisar recibos, comprobantes de transferencia y el arqueo firmado antes de asignar cada movimiento. No completar en bloque desde `Facturas.TurnoID`. Si falta evidencia, mantener el movimiento pendiente y resolver la diferencia contable antes de aprobar el arqueo.

Consulta de pendientes para el operador de base de datos autorizado:

```sql
SELECT p.ID AS PagoID,p.FacturaID,p.FechaPago,p.MetodoPago,p.Monto,
       f.NumeroFactura,f.TurnoID AS TurnoDeEmision
FROM ventas.Pagos p JOIN ventas.Facturas f ON f.ID=p.FacturaID
WHERE p.TurnoReceptorID IS NULL OR p.UsuarioReceptorID IS NULL
ORDER BY p.ID;
```

Tras comprobar la evidencia, ejecutar individualmente con la identidad SQL Admin/SuperAdmin. Sustituir las variables por los IDs revisados, incluso si el receptor resulta distinto del emisor:

```sql
BEGIN TRANSACTION;
EXEC ventas.sp_ConciliarReceptorPagoHistorico
    @PagoID=@PagoRevisado,
    @TurnoID=@TurnoReceptorComprobado,
    @UsuarioReceptorID=@CajeroDeEseTurno,
    @UsuarioConciliadorID=@AdministradorResponsable,
    @Evidencia=N'Recibo firmado R-123; transferencia T-456; revisión contable del 20/10/2026';
-- Revisar el movimiento y el evento CONCILIAR_RECEPTOR_PAGO antes de confirmar.
COMMIT;
```

El procedimiento comprueba que el turno pertenece al receptor indicado, exige evidencia y registra una auditoría fiscal. Rechaza movimientos ya conciliados; no permite sustituir después una atribución confirmada. No cambia montos, facturas, documentos fiscales ni arqueos firmados. Cajero, Operativo y portal no reciben permiso para ejecutarlo. Ante una atribución errónea confirmada, el responsable contable debe definir una corrección auditada específica; no modificar los documentos originales.
