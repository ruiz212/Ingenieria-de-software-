# app/services/contabilidad_service.py
# ============================================================
# SERVICIO CONTABLE CENTRALIZADO — Motor de Partida Doble NIIF
# ============================================================
# Este servicio encapsula TODA la lógica contable del sistema.
# Todos los módulos (POS, Inventario, RRHH, Egresos) deben
# llamar a estas funciones para generar asientos contables.
# ============================================================

import decimal
from datetime import datetime
from app.db import get_db_connection, execute_sp, is_sqlserver_cursor
from app.services.validation import amount
from app.services.business_time import business_now
from app.services.accounting_validation import validate_double_entry


class ContabilidadError(Exception):
    """Excepción personalizada para errores contables."""
    pass


class ContabilidadService:
    """
    Motor contable centralizado basado en NIIF para PYMES.

    Responsabilidades:
    - Validar partida doble (Debe == Haber)
    - Gestionar periodos contables (apertura/cierre)
    - Crear asientos de diario con validaciones
    - Generar asientos automáticos desde otros módulos
    - Implementar asientos de reversión (inmutabilidad)
    - Calcular saldos de cuentas y reportes

    IMPORTANTE: Todas las funciones que reciben 'cursor' esperan
    estar dentro de una transacción activa. El commit/rollback
    es responsabilidad del llamador.
    """

    # ============================================================
    # CONSTANTES — Códigos de cuenta del catálogo NIIF
    # ============================================================
    # Activos
    CAJA_GENERAL_CS         = '1.1.01.001'
    CAJA_GENERAL_USD        = '1.1.01.002'
    CAJA_CHICA              = '1.1.01.003'
    BANCOS_MN               = '1.1.01.004'
    BANCOS_ME               = '1.1.01.005'
    CXC_CLIENTES            = '1.1.02.001'
    ENCARGOS_POR_COBRAR     = '1.1.02.002'
    ANTICIPOS_EMPLEADOS     = '1.1.02.003'
    ANTICIPOS_PROVEEDORES   = '1.1.02.004'
    INV_MATERIA_PRIMA       = '1.1.03.001'
    INV_PRODUCTOS_PROCESO   = '1.1.03.002'
    INV_PRODUCTOS_TERMINADOS= '1.1.03.003'
    IVA_CREDITO_FISCAL      = '1.1.04.001'

    # Pasivos
    CXP_PROVEEDORES         = '2.1.01.001'
    ANTICIPOS_CLIENTES      = '2.1.01.003'
    SUELDOS_POR_PAGAR       = '2.1.02.001'
    INSS_LABORAL_POR_PAGAR  = '2.1.02.002'
    INSS_PATRONAL_POR_PAGAR = '2.1.02.003'
    INATEC_POR_PAGAR        = '2.1.02.004'
    IR_LABORAL_POR_PAGAR    = '2.1.02.005'
    VACACIONES_POR_PAGAR    = '2.1.02.006'
    AGUINALDO_POR_PAGAR     = '2.1.02.007'
    INDEMNIZACION_POR_PAGAR = '2.1.02.008'
    PENSIONES_POR_PAGAR     = '2.1.02.009'
    IVA_DEBITO_FISCAL       = '2.1.03.001'
    RETENCIONES_POR_PAGAR   = '2.1.03.005'

    # Capital
    CAPITAL_SOCIAL          = '3.1.01.001'
    UTILIDADES_RETENIDAS    = '3.2.01.001'
    UTILIDAD_EJERCICIO      = '3.2.01.002'

    # Ingresos
    VENTAS_PAN              = '4.1.01.001'
    VENTAS_PASTELES         = '4.1.01.002'
    VENTAS_BEBIDAS          = '4.1.01.003'
    DEVOLUCIONES_VENTAS     = '4.1.01.004'

    # Costos
    COSTO_MP_CONSUMIDA      = '5.1.01.001'
    MOD_PANADEROS           = '5.1.01.002'
    CIF                     = '5.1.01.003'
    MERMAS_DESPERDICIOS     = '5.1.02.001'

    # Gastos Admin
    SUELDOS_ADMIN           = '6.1.01.001'
    INSS_PATRONAL_ADMIN     = '6.1.01.002'
    INATEC_ADMIN            = '6.1.01.003'
    AGUINALDO_ADMIN         = '6.1.01.004'
    VACACIONES_ADMIN        = '6.1.01.005'
    INDEMNIZACION_ADMIN     = '6.1.01.006'
    ALQUILER_LOCAL          = '6.1.02.001'
    SERVICIOS_PUBLICOS      = '6.1.02.002'
    GASTOS_VARIOS_ADMIN     = '6.1.02.008'

    # Gastos Venta
    SUELDOS_VENTAS          = '6.2.01.001'
    INSS_PATRONAL_VENTAS    = '6.2.01.002'
    INATEC_VENTAS           = '6.2.01.003'

    # Mapeo de método de pago → cuenta contable
    METODO_PAGO_CUENTA = {
        'Efectivo':         CAJA_GENERAL_CS,
        'Efectivo USD':     CAJA_GENERAL_USD,
        'Caja Chica':       CAJA_CHICA,
        'Transferencia':    BANCOS_MN,
        'Transferencia ME': BANCOS_ME,
    }

    CUENTAS_EFECTIVO_BANCOS = {
        CAJA_GENERAL_CS,
        CAJA_GENERAL_USD,
        CAJA_CHICA,
        BANCOS_MN,
        BANCOS_ME,
    }

    # Tipo de comprobante por defecto para cada módulo
    TIPO_COMPROBANTE = {
        'venta':    'FV',
        'compra':   'FC',
        'nomina':   'NM',
        'egreso':   'EG',
        'ajuste':   'AJ',
        'diario':   'DI',
        'cierre':   'CI',
    }

    # ============================================================
    # FUNCIONES AUXILIARES INTERNAS
    # ============================================================

    @staticmethod
    def _get_cuenta_id(cursor, codigo):
        """Obtiene el ID de una cuenta por su código. Lanza error si no existe."""
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerCuentaActivaPorCodigo',
            (codigo,),
            fallback_sql="SELECT ID FROM CatalogoCuentas WHERE Codigo = ? AND Activa = 1",
        )
        row = cursor.fetchone()
        if not row:
            raise ContabilidadError(f"Cuenta contable '{codigo}' no encontrada o inactiva.")
        return row[0]

    @staticmethod
    def _validar_partida_doble(detalles):
        """
        Valida que la suma de débitos == suma de créditos.
        detalles: lista de tuplas (cuenta_codigo, debe, haber)
        """
        try:
            validate_double_entry([(amount(debe), amount(haber)) for _, debe, haber in detalles])
        except ValueError as error:
            raise ContabilidadError(str(error)) from error

    @staticmethod
    def _obtener_o_crear_periodo(cursor, mes=None, anio=None):
        """Obtiene o crea automáticamente un periodo contable para el mes/año dado."""
        if mes is None:
            mes = business_now().month
        if anio is None:
            anio = business_now().year

        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerPeriodoContablePorMesAnio',
            (mes, anio),
            fallback_sql="SELECT ID, Estado FROM PeriodosContables WITH (UPDLOCK, HOLDLOCK) WHERE Mes = ? AND Anio = ?",
        )
        row = cursor.fetchone()

        if row:
            if row[1] == 'Cerrado':
                raise ContabilidadError(
                    f"El periodo {mes}/{anio} está cerrado. "
                    "No se pueden registrar asientos en periodos cerrados."
                )
            return row[0]

        # Crear periodo automáticamente
        execute_sp(
            cursor,
            'contabilidad.sp_InsertarPeriodoContableAbierto',
            (mes, anio),
            fallback_sql="SET NOCOUNT ON; INSERT INTO PeriodosContables (Mes, Anio, Estado) OUTPUT INSERTED.ID VALUES (?, ?, 'Abierto')",
        )
        return cursor.fetchone()[0]

    @staticmethod
    def _generar_numero_comprobante(cursor, tipo_comprobante_codigo):
        """Genera un número correlativo para el tipo de comprobante dado."""
        execute_sp(
            cursor,
            'contabilidad.sp_SiguienteNumeroComprobante',
            (tipo_comprobante_codigo,),
            fallback_sql="""
            UPDATE TiposComprobante WITH (UPDLOCK, HOLDLOCK)
            SET CorrelativoActual = CorrelativoActual + 1
            OUTPUT INSERTED.ID, INSERTED.Prefijo, INSERTED.CorrelativoActual
            WHERE Codigo = ?
        """,
        )
        row = cursor.fetchone()
        if not row:
            raise ContabilidadError('Tipo de comprobante no configurado.')

        tipo_id = row[0]
        prefijo = row[1]
        correlativo = row[2]

        numero = f"{prefijo}-{correlativo:06d}"
        return tipo_id, numero

    # ============================================================
    # FUNCIÓN CORE: Crear Asiento de Diario
    # ============================================================

    @classmethod
    def crear_asiento(cls, cursor, descripcion, detalles, usuario_id,
                      tipo_comprobante='DI', referencia_externa=None,
                      tipo_documento='Manual', ip=None, mes=None, anio=None, fecha=None):
        """
        Crea un asiento de diario completo con validación de partida doble.
        """
        if not descripcion or not descripcion.strip():
            raise ContabilidadError('La descripción del asiento es obligatoria.')
        fecha = fecha or business_now()
        if (mes is not None and int(mes) != fecha.month) or (anio is not None and int(anio) != fecha.year):
            raise ContabilidadError('La fecha del asiento debe pertenecer al período seleccionado.')
        mes, anio = fecha.month, fecha.year
        # 1. Normalizar detalles a 4 elementos
        detalles_normalizados = []
        for d in detalles:
            if len(d) == 3:
                detalles_normalizados.append((d[0], amount(d[1]), amount(d[2]), None))
            else:
                detalles_normalizados.append((d[0], amount(d[1]), amount(d[2]), d[3]))

        # 2. Validar partida doble
        cls._validar_partida_doble([(d[0], d[1], d[2]) for d in detalles_normalizados])

        # 3. Obtener periodo contable
        periodo_id = cls._obtener_o_crear_periodo(cursor, mes, anio)

        # 4. Generar número de comprobante
        tipo_comprobante_id, numero_comprobante = cls._generar_numero_comprobante(
            cursor, tipo_comprobante
        )

        # 5. Insertar cabecera del asiento
        execute_sp(
            cursor,
            'contabilidad.sp_InsertarCabeceraAsiento',
            (
                fecha, periodo_id, descripcion, referencia_externa, tipo_documento,
                usuario_id, tipo_comprobante_id, numero_comprobante, ip
            ),
            fallback_sql="""
            SET NOCOUNT ON;
            INSERT INTO AsientosDiario
                (Fecha, PeriodoID, Descripcion, ReferenciaExterna, TipoDocumento,
                 Estado, UsuarioID, TipoComprobanteID, NumeroComprobante, IP)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, ?, 'Contabilizado', ?, ?, ?, ?)
        """,
        )
        asiento_id = cursor.fetchone()[0]
        if is_sqlserver_cursor(cursor):
            execute_sp(cursor, 'contabilidad.sp_InicializarEmisorYAuditarAsiento',
                       (asiento_id, usuario_id, numero_comprobante, referencia_externa, ip))
        else:
            from app.services.fiscal_service import configuration, audit
            import json
            emisor = {k:v for k,v in configuration(cursor).items() if k.startswith('fiscal_')}
            execute_sp(
                cursor, 'contabilidad.sp_ActualizarEmisorJSONAsiento',
                (json.dumps(emisor, ensure_ascii=False), asiento_id),
                fallback_sql='UPDATE AsientosDiario SET EmisorJSON=? WHERE ID=?',
            )
            audit(cursor,usuario_id,'ASIENTO','AsientosDiario',asiento_id,{'numero':numero_comprobante,'referencia':referencia_externa},ip)

        # 6. Insertar líneas de detalle
        for cuenta_codigo, debe, haber, desc_linea in detalles_normalizados:
            cuenta_id = cls._get_cuenta_id(cursor, cuenta_codigo)

            # Validar que la cuenta es transaccional
            execute_sp(
                cursor,
                'contabilidad.sp_ObtenerEsTransaccionalCuenta',
                (cuenta_id,),
                fallback_sql="SELECT EsTransaccional FROM CatalogoCuentas WHERE ID = ?",
            )
            es_transaccional = cursor.fetchone()
            if es_transaccional and not es_transaccional[0]:
                raise ContabilidadError(
                    f"La cuenta '{cuenta_codigo}' es de agrupación, no es transaccional."
                )

            execute_sp(
                cursor,
                'contabilidad.sp_InsertarLineaDetalleAsiento',
                (
                    asiento_id, cuenta_id,
                    debe, haber,
                    desc_linea, referencia_externa
                ),
                fallback_sql="""
                INSERT INTO DetalleAsientos
                    (AsientoID, CuentaID, Debe, Haber, Descripcion, DocumentoRelacionado)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            )

        return {
            'asiento_id': asiento_id,
            'numero_comprobante': numero_comprobante,
            'periodo_id': periodo_id
        }

    # ============================================================
    # ASIENTO DE REVERSIÓN (Anulación NIIF)
    # ============================================================

    @classmethod
    def revertir_asiento(cls, cursor, asiento_id_original, usuario_id, motivo, ip=None, fecha=None):
        """
        Crea un asiento de reversión (contrapartida) que anula el efecto
        de un asiento anterior. El asiento original se marca como 'Anulado'.

        NIIF: Los asientos contabilizados NUNCA se eliminan ni editan.
        """
        if not motivo or len(motivo.strip()) < 5:
            raise ContabilidadError('Indique un motivo de al menos cinco caracteres.')
        # 1. Obtener el asiento original
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerAsientoParaReversion',
            (asiento_id_original,),
            fallback_sql="""
            SELECT ID, PeriodoID, Descripcion, ReferenciaExterna, Estado
            FROM AsientosDiario WITH (UPDLOCK, HOLDLOCK) WHERE ID = ?
        """,
        )
        original = cursor.fetchone()

        if not original:
            raise ContabilidadError(f"Asiento #{asiento_id_original} no encontrado.")
        if original.Estado == 'Anulado':
            raise ContabilidadError(f"Asiento #{asiento_id_original} ya fue anulado.")
        if original.Estado == 'Borrador':
            raise ContabilidadError(f"Asiento #{asiento_id_original} está en borrador, no en contabilizado.")

        # 2. Obtener detalles del asiento original
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerDetallesAsientoParaReversion',
            (asiento_id_original,),
            fallback_sql="""
            SELECT C.Codigo, D.Debe, D.Haber, D.Descripcion
            FROM DetalleAsientos D
            JOIN CatalogoCuentas C ON D.CuentaID = C.ID
            WHERE D.AsientoID = ?
        """,
        )
        lineas_originales = cursor.fetchall()

        if not lineas_originales:
            raise ContabilidadError(f"Asiento #{asiento_id_original} no tiene detalle.")

        # 3. Crear detalles invertidos (debe↔haber)
        detalles_revertidos = []
        for linea in lineas_originales:
            detalles_revertidos.append((
                linea.Codigo,
                linea.Haber,
                linea.Debe,
                f"REVERSIÓN: {linea.Descripcion or ''}"
            ))

        # 4. Crear el asiento de reversión
        resultado = cls.crear_asiento(
            cursor=cursor,
            descripcion=f"REVERSIÓN del asiento #{asiento_id_original}: {motivo}",
            detalles=detalles_revertidos,
            usuario_id=usuario_id,
            tipo_comprobante='AJ',
            referencia_externa=f"REV-{asiento_id_original}",
            tipo_documento='Reversión',
            fecha=fecha,
            ip=ip
        )

        # 5. Marcar el asiento original como anulado
        execute_sp(
            cursor,
            'contabilidad.sp_MarcarAsientoAnulado',
            (usuario_id, motivo, asiento_id_original),
            fallback_sql="""
            UPDATE AsientosDiario SET
                Estado = 'Anulado',
                AnuladoPor = ?,
                FechaAnulacion = GETDATE(),
                MotivoAnulacion = ?
            WHERE ID = ? AND Estado = 'Contabilizado'
        """,
        )

        return resultado

    # ============================================================
    # ASIENTOS AUTOMÁTICOS — Integración con módulos
    # ============================================================

    @classmethod
    def contabilizar_venta(cls, cursor, usuario_id, numero_factura,
                           subtotal, iva, total, pagos,
                           es_encargo=False, adelanto=0, ip=None, fecha=None):
        """
        Genera el asiento contable automático para una venta POS.
        """
        detalles = []
        descripcion = f"Venta POS {numero_factura}"

        if es_encargo:
            descripcion += " (Encargo)"
            restante = amount(total) - amount(adelanto)
            porcentaje = (amount(adelanto) * 100 / amount(total)) if amount(total) else 0
            porcentaje_texto = f'{porcentaje:g}%'

            # Débito: adelanto a la cuenta según método de pago
            if float(adelanto) > 0:
                for pago in pagos:
                    cuenta_debito = cls.METODO_PAGO_CUENTA.get(pago['metodo'], cls.CAJA_GENERAL_CS)
                    destino = 'Caja' if cuenta_debito in (cls.CAJA_GENERAL_CS, cls.CAJA_GENERAL_USD) else 'Banco'
                    detalles.append((
                        cuenta_debito, amount(pago['monto']), 0,
                        f"Adelanto Encargo {numero_factura} ({porcentaje_texto}) - Recibido en {destino}"
                    ))

            # Débito: restante a Encargos por Cobrar
            if restante > 0:
                detalles.append((
                    cls.ENCARGOS_POR_COBRAR, restante, 0,
                    f"Saldo pendiente encargo {numero_factura}"
                ))
        else:
            # Ventas de mostrador: débito según método de pago
            for pago in pagos:
                if amount(pago['monto']) > 0:
                    cuenta_debito = cls.METODO_PAGO_CUENTA.get(pago['metodo'], cls.CAJA_GENERAL_CS)
                    detalles.append((
                        cuenta_debito, amount(pago['monto']), 0,
                        f"Cobro {pago['metodo']} {numero_factura}"
                    ))

        # Crédito: Ingresos por Ventas (subtotal sin IVA)
        if float(subtotal) > 0:
            cuenta_ingreso = cls.VENTAS_PAN
            if es_encargo:
                execute_sp(
                    cursor,
                    'contabilidad.sp_VerificarCuentaTransaccionalActiva',
                    (cls.VENTAS_PASTELES,),
                    fallback_sql="SELECT 1 FROM CatalogoCuentas WHERE Codigo = ? AND Activa = 1 AND EsTransaccional = 1",
                )
                if cursor.fetchone():
                    cuenta_ingreso = cls.VENTAS_PASTELES
            detalles.append((
                cuenta_ingreso, 0, amount(subtotal),
                f"Ingreso por venta {numero_factura}"
            ))

        # Crédito: IVA Débito Fiscal
        if float(iva) > 0:
            detalles.append((
                cls.IVA_DEBITO_FISCAL, 0, amount(iva),
                f"IVA venta {numero_factura}"
            ))

        return cls.crear_asiento(
            cursor=cursor,
            descripcion=descripcion,
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='FV',
            referencia_externa=numero_factura,
            tipo_documento='FacturaVenta',
            fecha=fecha,
            ip=ip
        )

    @classmethod
    def contabilizar_cobro_encargo(cls, cursor, usuario_id, numero_factura,
                                   monto_saldo, metodo_pago='Efectivo', ip=None, fecha=None):
        """
        Registra el asiento contable por el cobro del saldo pendiente de un encargo al entregarse.
        Debita Caja/Bancos según método de pago y acredita Encargos por Cobrar (1.1.02.002).
        """
        saldo = amount(monto_saldo)
        if saldo <= 0:
            return None
        cuenta_debito = cls.METODO_PAGO_CUENTA.get(metodo_pago, cls.CAJA_GENERAL_CS)
        detalles = [
            (cuenta_debito, saldo, 0, f"Liquidación Saldo Encargo {numero_factura} - Entrega de Producto ({metodo_pago})"),
            (cls.ENCARGOS_POR_COBRAR, 0, saldo, f"Liquidación CxC encargo {numero_factura}"),
        ]
        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Cobro saldo encargo {numero_factura}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='IN',
            referencia_externa=f"SALDO-{numero_factura}",
            tipo_documento='CobroEncargo',
            fecha=fecha,
            ip=ip
        )

    @classmethod
    def contabilizar_compra(cls, cursor, usuario_id, compra_id,
                            monto_sin_iva, iva, monto_total,
                            metodo_pago='Contado', referencia=None, ip=None, fecha=None):
        """
        Genera el asiento contable automático para una compra de materia prima.
        """
        detalles = []
        ref = referencia or f"COMP-{compra_id}"

        # Débito: Inventario de Materia Prima
        detalles.append((
            cls.INV_MATERIA_PRIMA, amount(monto_sin_iva), 0,
            f"Compra MP {ref}"
        ))

        # Débito: IVA Crédito Fiscal (si aplica)
        if float(iva) > 0:
            detalles.append((
                cls.IVA_CREDITO_FISCAL, amount(iva), 0,
                f"IVA crédito fiscal {ref}"
            ))

        # Crédito: según forma de pago
        if metodo_pago == 'Credito':
            detalles.append((
                cls.CXP_PROVEEDORES, 0, amount(monto_total),
                f"CxP proveedor {ref}"
            ))
        else:
            cuenta_pago = cls.METODO_PAGO_CUENTA.get(metodo_pago, cls.CAJA_GENERAL_CS)
            detalles.append((
                cuenta_pago, 0, amount(monto_total),
                f"Pago contado {ref}"
            ))

        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Compra de Materia Prima {ref}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='FC',
            referencia_externa=ref,
            tipo_documento='CompraMP',
            fecha=fecha,
            ip=ip
        )

    @classmethod
    def contabilizar_nomina(cls, cursor, usuario_id, nomina_id,
                            empleado_nombre, salario_bruto,
                            inss_laboral, ir_retenido,
                            inss_patronal, inatec,
                            pension_alimenticia=0,
                            vales_descontados=0,
                            salario_neto=0,
                            cargo='Admin', ip=None, fecha=None,
                            provision_vacaciones=0,
                            provision_aguinaldo=0,
                            provision_indemnizacion=0,
                            deduccion_prestamos=0,
                            cobro_perdidas=0,
                            viaticos=0,
                            depreciacion_vehiculo=0):
        """
        Genera el asiento contable automático para una nómina individual,
        incorporando ingresos salariales y no salariales, deducciones
        y cargos/provisiones patronales (Parte 1, 2 y 3).
        """
        detalles = []
        ref = f"NOM-{nomina_id}"
        cargo_lower = cargo.lower()

        # Determinar cuentas de gasto según área del empleado
        if 'panadero' in cargo_lower or 'produccion' in cargo_lower or 'hornero' in cargo_lower:
            cuenta_sueldo = cls.MOD_PANADEROS
            cuenta_inss_pat = cls.CIF
            cuenta_inatec = cls.CIF
            cuenta_vacaciones = cls.CIF
            cuenta_aguinaldo = cls.CIF
            cuenta_indemnizacion = cls.CIF
        elif 'vendedora' in cargo_lower or 'dependienta' in cargo_lower or 'cajera' in cargo_lower:
            cuenta_sueldo = cls.SUELDOS_VENTAS
            cuenta_inss_pat = cls.INSS_PATRONAL_VENTAS
            cuenta_inatec = cls.INATEC_VENTAS
            cuenta_vacaciones = cls.VACACIONES_ADMIN
            cuenta_aguinaldo = cls.AGUINALDO_ADMIN
            cuenta_indemnizacion = cls.INDEMNIZACION_ADMIN
        else:
            cuenta_sueldo = cls.SUELDOS_ADMIN
            cuenta_inss_pat = cls.INSS_PATRONAL_ADMIN
            cuenta_inatec = cls.INATEC_ADMIN
            cuenta_vacaciones = cls.VACACIONES_ADMIN
            cuenta_aguinaldo = cls.AGUINALDO_ADMIN
            cuenta_indemnizacion = cls.INDEMNIZACION_ADMIN

        # DÉBITOS (Gastos y Costos)
        detalles.append((cuenta_sueldo, float(amount(salario_bruto)), 0, f"Sueldo {empleado_nombre}"))

        if float(viaticos) > 0:
            detalles.append((cls.GASTOS_VARIOS_ADMIN, float(amount(viaticos)), 0, f"Viáticos {empleado_nombre}"))

        if float(depreciacion_vehiculo) > 0:
            detalles.append((cls.GASTOS_VARIOS_ADMIN, float(amount(depreciacion_vehiculo)), 0, f"Depreciación Vehículo {empleado_nombre}"))

        if float(inss_patronal) > 0:
            detalles.append((cuenta_inss_pat, float(amount(inss_patronal)), 0, f"INSS Patronal {empleado_nombre}"))

        if float(inatec) > 0:
            detalles.append((cuenta_inatec, float(amount(inatec)), 0, f"INATEC {empleado_nombre}"))

        if float(provision_vacaciones) > 0:
            detalles.append((cuenta_vacaciones, float(amount(provision_vacaciones)), 0, f"Provisión Vacaciones {empleado_nombre}"))

        if float(provision_aguinaldo) > 0:
            detalles.append((cuenta_aguinaldo, float(amount(provision_aguinaldo)), 0, f"Provisión Aguinaldo {empleado_nombre}"))

        if float(provision_indemnizacion) > 0:
            detalles.append((cuenta_indemnizacion, float(amount(provision_indemnizacion)), 0, f"Provisión Indemnización {empleado_nombre}"))

        # CRÉDITOS (Obligaciones, Pasivos y Recuperaciones)
        if float(salario_neto) > 0:
            detalles.append((cls.SUELDOS_POR_PAGAR, 0, float(amount(salario_neto)), f"Neto a pagar {empleado_nombre}"))

        if float(inss_laboral) > 0:
            detalles.append((cls.INSS_LABORAL_POR_PAGAR, 0, float(amount(inss_laboral)), f"INSS Lab. {empleado_nombre}"))

        if float(ir_retenido) > 0:
            detalles.append((cls.IR_LABORAL_POR_PAGAR, 0, float(amount(ir_retenido)), f"IR Ret. {empleado_nombre}"))

        if float(inss_patronal) > 0:
            detalles.append((cls.INSS_PATRONAL_POR_PAGAR, 0, float(amount(inss_patronal)), f"INSS Pat. x pagar {empleado_nombre}"))

        if float(inatec) > 0:
            detalles.append((cls.INATEC_POR_PAGAR, 0, float(amount(inatec)), f"INATEC x pagar {empleado_nombre}"))

        if float(pension_alimenticia) > 0:
            detalles.append((cls.PENSIONES_POR_PAGAR, 0, float(amount(pension_alimenticia)), f"Pensión alim. {empleado_nombre}"))

        if float(vales_descontados) > 0:
            detalles.append((cls.ANTICIPOS_EMPLEADOS, 0, float(amount(vales_descontados)), f"Descuento vales {empleado_nombre}"))

        if float(deduccion_prestamos) > 0:
            detalles.append((cls.ANTICIPOS_EMPLEADOS, 0, float(amount(deduccion_prestamos)), f"Abono préstamo {empleado_nombre}"))

        if float(cobro_perdidas) > 0:
            detalles.append((cls.GASTOS_VARIOS_ADMIN, 0, float(amount(cobro_perdidas)), f"Recuperación pérdida {empleado_nombre}"))

        if float(provision_vacaciones) > 0:
            detalles.append((cls.VACACIONES_POR_PAGAR, 0, float(amount(provision_vacaciones)), f"Provisión Vacaciones {empleado_nombre}"))

        if float(provision_aguinaldo) > 0:
            detalles.append((cls.AGUINALDO_POR_PAGAR, 0, float(amount(provision_aguinaldo)), f"Provisión Aguinaldo {empleado_nombre}"))

        if float(provision_indemnizacion) > 0:
            detalles.append((cls.INDEMNIZACION_POR_PAGAR, 0, float(amount(provision_indemnizacion)), f"Provisión Indemnización {empleado_nombre}"))

        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Nómina {empleado_nombre} — {ref}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='NM',
            referencia_externa=ref,
            tipo_documento='Nomina',
            ip=ip,
            fecha=fecha
        )

    @classmethod
    def contabilizar_aguinaldo(cls, cursor, usuario_id, nomina_id,
                               empleado_nombre, monto_aguinaldo,
                               cargo='Admin', ip=None, fecha=None):
        """
        Genera el asiento contable automático para el treceavo mes (aguinaldo).
        """
        monto = float(amount(monto_aguinaldo))
        if monto <= 0:
            raise ContabilidadError('El monto de aguinaldo debe ser mayor a cero.')
        ref = f"NOM-{nomina_id}"
        detalles = [
            (cls.AGUINALDO_ADMIN, monto, 0, f"Aguinaldo {empleado_nombre}"),
            (cls.AGUINALDO_POR_PAGAR, 0, monto, f"Aguinaldo por pagar {empleado_nombre}"),
        ]
        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Aguinaldo {empleado_nombre} — {ref}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='NM',
            referencia_externa=ref,
            tipo_documento='Nomina',
            ip=ip,
            fecha=fecha
        )

    @classmethod
    def obtener_saldo_disponible_cuenta(cls, cursor, cuenta_codigo):
        """
        Obtiene el saldo disponible actual de una cuenta contable (con bloqueo UPDLOCK, HOLDLOCK
        en SQL Server) sobre asientos Contabilizados (y anulados con reversión compensada).
        """
        if not cuenta_codigo or not str(cuenta_codigo).strip():
            raise ContabilidadError('Debe especificar el código de la cuenta de origen.')
        codigo = str(cuenta_codigo).strip()
        sql_fallback = """
            SELECT
                C.Naturaleza,
                COALESCE(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Debe ELSE 0 END), 0) AS TotalDebe,
                COALESCE(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Haber ELSE 0 END), 0) AS TotalHaber,
                COALESCE(SUM(D.Debe-D.Haber), 0) AS SaldoBruto
            FROM CatalogoCuentas C
            LEFT JOIN DetalleAsientos D ON D.CuentaID = C.ID
            LEFT JOIN AsientosDiario A ON D.AsientoID = A.ID
                AND (
                    A.Estado = 'Contabilizado'
                    OR (A.Estado = 'Anulado' AND EXISTS (
                        SELECT 1 FROM AsientosDiario R
                        WHERE R.ReferenciaExterna = ('REV-' || CAST(A.ID AS TEXT))
                          AND R.Estado = 'Contabilizado'
                    ))
                )
            WHERE C.Codigo = ? AND C.Activa = 1
            GROUP BY C.Naturaleza
        """
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerSaldoDisponibleCuenta',
            (codigo,),
            fallback_sql=sql_fallback,
        )
        row = cursor.fetchone()
        if not row:
            raise ContabilidadError(f"Cuenta contable '{codigo}' no encontrada o inactiva.")
        if len(row) == 1:
            return decimal.Decimal(str(row[0] or 0))
        naturaleza = getattr(row, 'Naturaleza', row[0])
        total_debe = decimal.Decimal(str(getattr(row, 'TotalDebe', row[1]) or 0))
        total_haber = decimal.Decimal(str(getattr(row, 'TotalHaber', row[2]) or 0))
        if naturaleza == 'Deudora':
            return total_debe - total_haber
        return total_haber - total_debe

    @classmethod
    def verificar_fondos_disponibles(cls, cursor, cuenta_codigo, monto_requerido, permitir_sobregiro=False):
        """
        Verifica que una cuenta de efectivo o bancos tenga fondos suficientes antes de un desembolso.
        """
        try:
            monto_dec = amount(monto_requerido, 'Monto')
        except ValueError as err:
            raise ContabilidadError(str(err)) from err
        if monto_dec <= 0:
            raise ContabilidadError('El monto del desembolso debe ser mayor a cero.')
        if not cuenta_codigo or str(cuenta_codigo).strip() not in cls.CUENTAS_EFECTIVO_BANCOS:
            raise ContabilidadError(
                f"La cuenta '{cuenta_codigo}' no es una cuenta válida de efectivo o bancos."
            )
        saldo_actual = cls.obtener_saldo_disponible_cuenta(cursor, str(cuenta_codigo).strip())
        if not permitir_sobregiro and saldo_actual < monto_dec:
            raise ContabilidadError(
                f"Fondos insuficientes en la cuenta seleccionada ({cuenta_codigo}): "
                f"disponible C${saldo_actual:.2f}, requerido C${monto_dec:.2f}."
            )
        return saldo_actual

    @classmethod
    def resolver_cuenta_desembolso(cls, metodo_pago='Efectivo', cuenta_pago=None):
        """Resuelve y valida la cuenta de efectivo/bancos para un desembolso."""
        if cuenta_pago is not None and str(cuenta_pago).strip():
            codigo = str(cuenta_pago).strip()
            if codigo not in cls.CUENTAS_EFECTIVO_BANCOS:
                raise ContabilidadError(
                    f"La cuenta '{codigo}' no es una cuenta válida de efectivo o bancos."
                )
            return codigo
        if not metodo_pago or metodo_pago not in cls.METODO_PAGO_CUENTA:
            raise ContabilidadError(f"Método de pago '{metodo_pago}' no válido para desembolso.")
        return cls.METODO_PAGO_CUENTA[metodo_pago]

    @classmethod
    def contabilizar_egreso(cls, cursor, usuario_id, concepto, monto,
                            cuenta_gasto=None, metodo_pago='Efectivo',
                            cuenta_pago=None, permitir_sobregiro=False,
                            referencia=None, ip=None, fecha=None):
        """
        Genera el asiento contable automático para un egreso privado,
        verificando previamente fondos disponibles en la cuenta de origen.
        """
        if cuenta_gasto is None:
            cuenta_gasto = cls.GASTOS_VARIOS_ADMIN

        cuenta_origen = cls.resolver_cuenta_desembolso(metodo_pago=metodo_pago, cuenta_pago=cuenta_pago)
        cls.verificar_fondos_disponibles(
            cursor, cuenta_origen, monto, permitir_sobregiro=permitir_sobregiro
        )

        fecha = fecha or business_now()
        ref = referencia or f"EGR-{fecha.strftime('%Y%m%d%H%M%S')}"

        detalles = [
            (cuenta_gasto, float(monto), 0, concepto),
            (cuenta_origen, 0, float(monto), f"Pago {metodo_pago} — {concepto}"),
        ]

        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Egreso: {concepto}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='EG',
            referencia_externa=ref,
            tipo_documento='EgresoPrivado',
            ip=ip,
            fecha=fecha
        )

    @classmethod
    def contabilizar_vale(cls, cursor, usuario_id, empleado_nombre,
                          monto, metodo_pago='Efectivo', cuenta_pago=None,
                          permitir_sobregiro=False, referencia=None, ip=None, fecha=None):
        """
        Genera el asiento contable automático para un vale a empleado,
        verificando previamente fondos disponibles en la cuenta de origen.
        """
        cuenta_origen = cls.resolver_cuenta_desembolso(metodo_pago=metodo_pago, cuenta_pago=cuenta_pago)
        cls.verificar_fondos_disponibles(
            cursor, cuenta_origen, monto, permitir_sobregiro=permitir_sobregiro
        )

        fecha = fecha or business_now()
        ref = referencia or f"VALE-{fecha.strftime('%Y%m%d%H%M%S')}"

        detalles = [
            (cls.ANTICIPOS_EMPLEADOS, float(monto), 0, f"Vale a {empleado_nombre}"),
            (cuenta_origen, 0, float(monto), f"Desembolso vale {empleado_nombre}"),
        ]

        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Vale a empleado: {empleado_nombre}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='EG',
            referencia_externa=ref,
            tipo_documento='ValeEmpleado',
            ip=ip,
            fecha=fecha
        )

    @classmethod
    def contabilizar_merma(cls, cursor, usuario_id, producto_nombre,
                           cantidad, costo_unitario_estimado,
                           motivo='Pan Frio', referencia=None, ip=None):
        """
        Genera el asiento contable automático para una merma.
        """
        monto = float(cantidad) * float(costo_unitario_estimado)
        ref = referencia or f"MERMA-{business_now().strftime('%Y%m%d%H%M%S')}"

        detalles = [
            (cls.MERMAS_DESPERDICIOS, monto, 0, f"Merma: {cantidad} x {producto_nombre} ({motivo})"),
            (cls.INV_PRODUCTOS_TERMINADOS, 0, monto, f"Baja inventario PT por merma"),
        ]

        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Merma: {cantidad} {producto_nombre} — {motivo}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='AJ',
            referencia_externa=ref,
            tipo_documento='Merma',
            ip=ip
        )

    # ============================================================
    # CONSULTAS Y REPORTES
    # ============================================================

    @classmethod
    def _verificar_conciliacion_cierre(cls, cursor, periodo_id, mes, anio):
        """
        Verifica que todas las facturas activas y compras del período tengan su asiento
        contable contabilizado antes de permitir el cierre mensual.
        Maneja con gracia entornos SQLite o dobles de prueba donde Facturas/Compras no existan.
        """
        mes_int, anio_int = int(mes), int(anio)
        if is_sqlserver_cursor(cursor):
            execute_sp(
                cursor,
                'contabilidad.sp_VerificarConciliacionCierrePeriodo',
                (periodo_id, mes_int, anio_int),
            )
            row = cursor.fetchone()
            if row and (int(row[0] or 0) > 0 or int(row[1] or 0) > 0):
                raise ContabilidadError(
                    'No se puede cerrar el período: existen facturas o compras sin asiento contable conciliado.'
                )
            return

        is_sqlite = type(cursor).__module__.startswith('sqlite3')
        if is_sqlite:
            ym_prefix = f"{anio_int:04d}-{mes_int:02d}"
            execute_sp(
                cursor,
                'contabilidad.sp_ListarTablasOperativasSQLite',
                (),
                fallback_sql="SELECT name FROM sqlite_master WHERE type='table' AND name IN ('Facturas', 'Compras', 'ComprasMateriaPrima')",
            )
            existing_tables = {r[0] for r in cursor.fetchall()}
            if not existing_tables:
                return

            execute_sp(
                cursor,
                'contabilidad.sp_ListarAsientosPeriodoSQLite',
                (periodo_id, ym_prefix),
                fallback_sql=(
                    "SELECT ID, COALESCE(ReferenciaExterna, ''), COALESCE(TipoDocumento, '') "
                    "FROM AsientosDiario WHERE Estado = 'Contabilizado' AND "
                    "(PeriodoID = ? OR substr(CAST(Fecha AS TEXT), 1, 7) = ?)"
                ),
            )
            asientos_rows = cursor.fetchall()
            refs_contabilizadas = {str(r[1]).strip() for r in asientos_rows if str(r[1]).strip()}
            ids_contabilizados = {int(r[0]) for r in asientos_rows if r[0] is not None}
            tipos_contabilizados = {str(r[2]).strip() for r in asientos_rows if str(r[2]).strip()}

            if 'Facturas' in existing_tables:
                execute_sp(
                    cursor,
                    'contabilidad.sp_InfoTablaFacturasSQLite',
                    (),
                    fallback_sql="PRAGMA table_info(Facturas)",
                )
                f_cols = {r[1] for r in cursor.fetchall()}
                date_col = 'FechaHora' if 'FechaHora' in f_cols else ('Fecha' if 'Fecha' in f_cols else None)
                state_col = 'EstadoFiscal' if 'EstadoFiscal' in f_cols else ('Estado' if 'Estado' in f_cols else None)
                num_col = 'NumeroFactura' if 'NumeroFactura' in f_cols else ('Numero' if 'Numero' in f_cols else None)
                if date_col:
                    select_num = f"COALESCE(CAST({num_col} AS TEXT), '')" if num_col else "''"
                    where_state = f"AND COALESCE({state_col}, 'Emitida') != 'Anulada'" if state_col else ""
                    execute_sp(
                        cursor,
                        'contabilidad.sp_ListarFacturasActivasPeriodoSQLite',
                        (ym_prefix,),
                        fallback_sql=(
                            f"SELECT ID, {select_num} FROM Facturas "
                            f"WHERE substr(CAST({date_col} AS TEXT), 1, 7) = ? {where_state}"
                        ),
                    )
                    facturas_activas = cursor.fetchall()
                    for fid, fnum in facturas_activas:
                        fnum_s = str(fnum or '').strip()
                        matched = (
                            (fnum_s and fnum_s in refs_contabilizadas)
                            or f"FAC-{fid}" in refs_contabilizadas
                            or str(fid) in refs_contabilizadas
                            or (not fnum_s and bool(tipos_contabilizados & {'FacturaVenta', 'Venta', 'VentaPOS'}))
                        )
                        if not matched:
                            raise ContabilidadError(
                                'No se puede cerrar el período: existen facturas o compras sin asiento contable conciliado.'
                            )

            for compra_table in ('ComprasMateriaPrima', 'Compras'):
                if compra_table in existing_tables:
                    execute_sp(
                        cursor,
                        'contabilidad.sp_InfoTablaComprasSQLite',
                        (),
                        fallback_sql=f"PRAGMA table_info({compra_table})",
                    )
                    c_cols = {r[1] for r in cursor.fetchall()}
                    date_col = 'Fecha' if 'Fecha' in c_cols else ('FechaHora' if 'FechaHora' in c_cols else None)
                    state_col = 'Estado' if 'Estado' in c_cols else None
                    ref_col = (
                        'FacturaProveedor' if 'FacturaProveedor' in c_cols
                        else ('Referencia' if 'Referencia' in c_cols else ('Numero' if 'Numero' in c_cols else None))
                    )
                    if date_col:
                        select_ref = f"COALESCE(CAST({ref_col} AS TEXT), '')" if ref_col else "''"
                        where_state = f"AND COALESCE({state_col}, 'Registrada') != 'Anulada'" if state_col else ""
                        execute_sp(
                            cursor,
                            'contabilidad.sp_ListarComprasActivasPeriodoSQLite',
                            (ym_prefix,),
                            fallback_sql=(
                                f"SELECT ID, {select_ref} FROM {compra_table} "
                                f"WHERE substr(CAST({date_col} AS TEXT), 1, 7) = ? {where_state}"
                            ),
                        )
                        compras_activas = cursor.fetchall()
                        for cid, cref in compras_activas:
                            cref_s = str(cref or '').strip()
                            matched = (
                                (cref_s and cref_s in refs_contabilizadas)
                                or f"COMP-{cid}" in refs_contabilizadas
                                or str(cid) in refs_contabilizadas
                                or (not cref_s and bool(tipos_contabilizados & {'CompraMP', 'Compra'}))
                            )
                            if not matched:
                                raise ContabilidadError(
                                    'No se puede cerrar el período: existen facturas o compras sin asiento contable conciliado.'
                                )
            return

        # Dobles de prueba genéricos que implementan fallback_sql
        try:
            execute_sp(
                cursor,
                'contabilidad.sp_VerificarConciliacionCierrePeriodo',
                (periodo_id, mes_int, anio_int),
                fallback_sql="SELECT 0 AS FacturasSinAsiento, 0 AS ComprasSinAsiento",
                fallback_params=(),
            )
            row = cursor.fetchone()
            if row and len(row) >= 2 and (int(row[0] or 0) > 0 or int(row[1] or 0) > 0):
                raise ContabilidadError(
                    'No se puede cerrar el período: existen facturas o compras sin asiento contable conciliado.'
                )
        except ContabilidadError:
            raise
        except Exception:
            pass

    @classmethod
    def cerrar_periodo(cls, cursor, periodo_id, usuario_id, permitir_excepcion=False):
        is_sqlite = type(cursor).__module__.startswith('sqlite3')
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerPeriodoParaCierre',
            (periodo_id,),
            fallback_sql=(
                'SELECT Mes, Anio, Estado FROM PeriodosContables WHERE ID=?'
                if is_sqlite else
                'SELECT Mes,Anio,Estado FROM PeriodosContables WITH(UPDLOCK,HOLDLOCK) WHERE ID=?'
            ),
        )
        period = cursor.fetchone()
        if not period:
            raise ContabilidadError('El período no existe o ya está cerrado.')
        p_mes = getattr(period, 'Mes', period[0])
        p_anio = getattr(period, 'Anio', period[1])
        p_estado = getattr(period, 'Estado', period[2])
        if p_estado != 'Abierto':
            raise ContabilidadError('El período no existe o ya está cerrado.')
        now = business_now()
        if (int(p_anio), int(p_mes)) >= (now.year, now.month):
            raise ContabilidadError('Solo se pueden cerrar meses concluidos.')
        execute_sp(
            cursor,
            'contabilidad.sp_ContarAsientosBorradorPeriodo',
            (periodo_id,),
            fallback_sql="SELECT COUNT(*) FROM AsientosDiario WHERE PeriodoID=? AND Estado='Borrador'",
        )
        if cursor.fetchone()[0]:
            raise ContabilidadError('Revise los asientos en borrador antes del cierre.')
        sql_descuadrados = """SELECT A.ID FROM AsientosDiario A LEFT JOIN DetalleAsientos D ON D.AsientoID=A.ID
            WHERE A.PeriodoID=? AND A.Estado IN ('Contabilizado','Anulado') GROUP BY A.ID
            HAVING COUNT(D.ID)<2 OR SUM(D.Debe)<>SUM(D.Haber) OR SUM(D.Debe)<=0"""
        execute_sp(
            cursor,
            'contabilidad.sp_VerificarAsientosDescuadradosPeriodo',
            (periodo_id,),
            fallback_sql=sql_descuadrados,
        )
        if cursor.fetchone():
            raise ContabilidadError('Hay asientos vacíos o descuadrados. No se cerró el período.')
        if not permitir_excepcion:
            cls._verificar_conciliacion_cierre(cursor, periodo_id, p_mes, p_anio)
        sql_cerrar = "UPDATE PeriodosContables SET Estado='Cerrado',CerradoPor=?,CerradoEn=? WHERE ID=?"
        execute_sp(
            cursor,
            'contabilidad.sp_CerrarPeriodoContable',
            (usuario_id, now, periodo_id),
            fallback_sql=sql_cerrar,
        )

    @classmethod
    def obtener_resumen_financiero_rango(cls, cursor, fecha_inicio, fecha_fin):
        """
        Calcula a partir del Mayor General (asientos Contabilizados y anulados con reversión):
        - Ingresos netos contables (Clase 4 / 'Ingreso': Haber - Debe, excluyendo IVA Débito Fiscal)
        - Costos contables (Clase 5 / 'Costo': Debe - Haber, excluyendo compras de activo inventario)
        - Gastos contables (Clase 6 / 'Gasto': Debe - Haber)
        - Utilidad neta contable (Ingresos - Costos - Gastos)
        - Flujo de caja operativo (Entradas y Salidas reales en cuentas de Efectivo y Bancos 1.1.01.%)
        """
        is_sqlite = type(cursor).__module__.startswith('sqlite3')
        sql_fallback = """
            SELECT
                COALESCE(SUM(CASE WHEN C.Clase = 'Ingreso' OR C.Codigo LIKE '4.%' THEN D.Haber - D.Debe ELSE 0 END), 0) AS IngresosContables,
                COALESCE(SUM(CASE WHEN C.Clase = 'Costo' OR C.Codigo LIKE '5.%' THEN D.Debe - D.Haber ELSE 0 END), 0) AS CostosContables,
                COALESCE(SUM(CASE WHEN C.Clase = 'Gasto' OR C.Codigo LIKE '6.%' THEN D.Debe - D.Haber ELSE 0 END), 0) AS GastosContables,
                COALESCE(SUM(CASE WHEN C.Codigo IN ('1.1.01.001','1.1.01.002','1.1.01.003','1.1.01.004','1.1.01.005')
                                   AND A.Estado = 'Contabilizado' AND COALESCE(A.TipoDocumento, '') != 'Reversión'
                             THEN D.Debe ELSE 0 END), 0) AS EntradasEfectivo,
                COALESCE(SUM(CASE WHEN C.Codigo IN ('1.1.01.001','1.1.01.002','1.1.01.003','1.1.01.004','1.1.01.005')
                                   AND A.Estado = 'Contabilizado' AND COALESCE(A.TipoDocumento, '') != 'Reversión'
                             THEN D.Haber ELSE 0 END), 0) AS SalidasEfectivo,
                COALESCE(SUM(CASE WHEN C.Codigo IN ('1.1.01.001','1.1.01.002','1.1.01.003','1.1.01.004','1.1.01.005')
                             THEN D.Debe - D.Haber ELSE 0 END), 0) AS FlujoCajaOperativo
            FROM DetalleAsientos D
            JOIN AsientosDiario A ON D.AsientoID = A.ID
            JOIN CatalogoCuentas C ON D.CuentaID = C.ID
            WHERE (
                A.Estado = 'Contabilizado'
                OR (A.Estado = 'Anulado' AND EXISTS (
                    SELECT 1 FROM AsientosDiario R
                    WHERE R.ReferenciaExterna = ('REV-' || CAST(A.ID AS TEXT))
                      AND R.Estado = 'Contabilizado'
                ))
            )
              AND A.Fecha >= ? AND A.Fecha < ?
        """
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerResumenFinancieroRango',
            (fecha_inicio, fecha_fin),
            fallback_sql=sql_fallback,
        )
        row = cursor.fetchone()
        if not row:
            return {
                'ingresos_contables': 0.0,
                'costos_contables': 0.0,
                'gastos_contables': 0.0,
                'utilidad_neta': 0.0,
                'entradas_efectivo': 0.0,
                'salidas_efectivo': 0.0,
                'flujo_caja_operativo': 0.0,
            }
        ingresos_c = float(row[0] or 0)
        costos_c = float(row[1] or 0)
        gastos_c = float(row[2] or 0)
        entradas_ef = float(row[3] or 0)
        salidas_ef = float(row[4] or 0)
        flujo_caja = float(row[5] or 0)
        utilidad_neta = round(ingresos_c - costos_c - gastos_c, 2)
        return {
            'ingresos_contables': round(ingresos_c, 2),
            'costos_contables': round(costos_c, 2),
            'gastos_contables': round(gastos_c, 2),
            'utilidad_neta': utilidad_neta,
            'entradas_efectivo': round(entradas_ef, 2),
            'salidas_efectivo': round(salidas_ef, 2),
            'flujo_caja_operativo': round(flujo_caja, 2),
        }

    @staticmethod
    def balanza_mensual(cursor, mes, anio):
        start = datetime(int(anio), int(mes), 1)
        end = datetime(start.year + 1, 1, 1) if start.month == 12 else datetime(start.year, start.month + 1, 1)
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerBalanzaMensualRango',
            (start, start, start, end),
            fallback_sql="""
            SELECT C.Codigo,C.Nombre,C.Naturaleza,
              SUM(CASE WHEN A.Fecha<? THEN D.Debe-D.Haber ELSE 0 END) AS SaldoAnterior,
              SUM(CASE WHEN A.Fecha>=? THEN D.Debe ELSE 0 END) AS TotalDebe,
              SUM(CASE WHEN A.Fecha>=? THEN D.Haber ELSE 0 END) AS TotalHaber,
              SUM(D.Debe-D.Haber) AS SaldoFinal
            FROM CatalogoCuentas C JOIN DetalleAsientos D ON C.ID=D.CuentaID
            JOIN AsientosDiario A ON A.ID=D.AsientoID
            WHERE A.Estado IN ('Contabilizado','Anulado') AND A.Fecha<? AND C.EsTransaccional=1
            GROUP BY C.Codigo,C.Nombre,C.Naturaleza ORDER BY C.Codigo
        """,
        )
        return [dict(zip([c[0] for c in cursor.description], r)) for r in cursor.fetchall()]

    @staticmethod
    def obtener_saldo_cuenta(cursor, cuenta_codigo, fecha_corte=None):
        """
        Calcula el saldo actual de una cuenta contable.
        """
        params = [cuenta_codigo]
        filtro_fecha = ""
        if fecha_corte:
            filtro_fecha = "AND A.Fecha < DATEADD(day,1,CAST(? AS date))"
            params.append(fecha_corte)

        sp_name = 'contabilidad.sp_ObtenerSaldoCuentaCorte' if fecha_corte else 'contabilidad.sp_ObtenerSaldoCuentaTotal'
        execute_sp(
            cursor,
            sp_name,
            (*params[1:], params[0]),
            fallback_sql=f"""
            SELECT
                C.Naturaleza,
                ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Debe ELSE 0 END), 0) AS TotalDebe,
                ISNULL(SUM(CASE WHEN A.ID IS NOT NULL THEN D.Haber ELSE 0 END), 0) AS TotalHaber
            FROM CatalogoCuentas C
            LEFT JOIN DetalleAsientos D ON D.CuentaID = C.ID
            LEFT JOIN AsientosDiario A ON D.AsientoID = A.ID
                AND A.Estado IN ('Contabilizado', 'Anulado') {filtro_fecha}
            WHERE C.Codigo = ?
            GROUP BY C.Naturaleza
        """,
        )

        row = cursor.fetchone()
        if not row:
            return decimal.Decimal('0')

        if row.Naturaleza == 'Deudora':
            return decimal.Decimal(str(row.TotalDebe)) - decimal.Decimal(str(row.TotalHaber))
        else:
            return decimal.Decimal(str(row.TotalHaber)) - decimal.Decimal(str(row.TotalDebe))

    @staticmethod
    def obtener_balance_comprobacion(cursor, periodo_id=None, fecha_corte=None):
        """
        Genera el Balance de Comprobación completo.
        Retorna lista de dicts con: Codigo, Nombre, Clase, TotalDebe, TotalHaber, SaldoFinal
        """
        filtro = ""
        params = []

        if periodo_id:
            filtro = "AND A.PeriodoID = ?"
            params.append(periodo_id)
            sp_name = 'contabilidad.sp_ObtenerBalanceComprobacionPeriodo'
        elif fecha_corte:
            filtro = "AND A.Fecha < DATEADD(day,1,CAST(? AS date))"
            params.append(fecha_corte)
            sp_name = 'contabilidad.sp_ObtenerBalanceComprobacionCorte'
        else:
            sp_name = 'contabilidad.sp_ObtenerBalanceComprobacionGeneral'

        execute_sp(
            cursor,
            sp_name,
            params,
            fallback_sql=f"""
            SELECT
                C.Codigo,
                C.Nombre,
                C.Clase,
                C.Naturaleza,
                C.Nivel,
                ISNULL(SUM(D.Debe), 0) AS TotalDebe,
                ISNULL(SUM(D.Haber), 0) AS TotalHaber,
                CASE
                    WHEN C.Naturaleza = 'Deudora' THEN ISNULL(SUM(D.Debe), 0) - ISNULL(SUM(D.Haber), 0)
                    ELSE ISNULL(SUM(D.Haber), 0) - ISNULL(SUM(D.Debe), 0)
                END AS SaldoFinal
            FROM CatalogoCuentas C
            INNER JOIN DetalleAsientos D ON D.CuentaID = C.ID
            INNER JOIN AsientosDiario A ON D.AsientoID = A.ID
            WHERE A.Estado IN ('Contabilizado', 'Anulado')
              AND C.EsTransaccional = 1
              {filtro}
            GROUP BY C.Codigo, C.Nombre, C.Clase, C.Naturaleza, C.Nivel
            HAVING ISNULL(SUM(D.Debe), 0) != 0 OR ISNULL(SUM(D.Haber), 0) != 0
            ORDER BY C.Codigo
        """,
        )

        resultados = []
        for row in cursor.fetchall():
            resultados.append({
                'Codigo': row.Codigo,
                'Nombre': row.Nombre,
                'Clase': row.Clase,
                'Naturaleza': row.Naturaleza,
                'TotalDebe': float(row.TotalDebe),
                'TotalHaber': float(row.TotalHaber),
                'SaldoFinal': float(row.SaldoFinal)
            })

        return resultados

    @staticmethod
    def obtener_libro_mayor(cursor, cuenta_codigo, periodo_id=None,
                            fecha_inicio=None, fecha_fin=None):
        """
        Genera el Libro Mayor para una cuenta específica.
        Retorna lista de movimientos con saldo acumulado.
        """
        filtros = ["A.Estado IN ('Contabilizado', 'Anulado')"]
        params = [cuenta_codigo]

        if periodo_id:
            filtros.append("A.PeriodoID = ?")
            params.append(periodo_id)
        if fecha_inicio:
            filtros.append("A.Fecha >= ?")
            params.append(fecha_inicio)
        if fecha_fin:
            filtros.append("A.Fecha < DATEADD(day,1,CAST(? AS date))")
            params.append(fecha_fin)

        where_clause = " AND ".join(filtros)
        mov_params = (cuenta_codigo, periodo_id, fecha_inicio, fecha_fin) if is_sqlserver_cursor(cursor) else params

        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerMovimientosLibroMayor',
            mov_params,
            fallback_sql=f"""
            SELECT
                A.Fecha,
                A.NumeroComprobante,
                A.Descripcion AS DescripcionAsiento,
                D.Descripcion AS DescripcionLinea,
                D.Debe,
                D.Haber,
                A.ReferenciaExterna
            FROM DetalleAsientos D
            INNER JOIN AsientosDiario A ON D.AsientoID = A.ID
            INNER JOIN CatalogoCuentas C ON D.CuentaID = C.ID
            WHERE C.Codigo = ? AND {where_clause}
            ORDER BY A.Fecha, A.ID
        """,
        )

        # Obtener naturaleza para calcular saldo acumulado
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerNaturalezaCuenta',
            (cuenta_codigo,),
            fallback_sql="SELECT Naturaleza FROM CatalogoCuentas WHERE Codigo = ?",
        )
        nat_row = cursor.fetchone()
        es_deudora = nat_row and nat_row[0] == 'Deudora'

        movimientos = []
        saldo_acumulado = decimal.Decimal('0')
        opening_date = fecha_inicio
        if periodo_id:
            execute_sp(
                cursor,
                'contabilidad.sp_ObtenerAnioMesPeriodo',
                (periodo_id,),
                fallback_sql='SELECT Anio,Mes FROM PeriodosContables WHERE ID=?',
            )
            period = cursor.fetchone()
            if period:
                opening_date = datetime(period[0], period[1], 1)
        if opening_date:
            execute_sp(
                cursor,
                'contabilidad.sp_ObtenerSaldoAnteriorLibroMayor',
                (cuenta_codigo, opening_date),
                fallback_sql="""SELECT ISNULL(SUM(D.Debe-D.Haber),0) FROM DetalleAsientos D
              JOIN AsientosDiario A ON D.AsientoID=A.ID JOIN CatalogoCuentas C ON D.CuentaID=C.ID
              WHERE C.Codigo=? AND A.Fecha<? AND A.Estado IN ('Contabilizado','Anulado')""",
            )
            saldo_acumulado = cursor.fetchone()[0] * (1 if es_deudora else -1)
            movimientos.append({'Fecha': '', 'Comprobante': '', 'Descripcion': 'Saldo anterior', 'Referencia': '', 'Debe': 0, 'Haber': 0, 'Saldo': float(saldo_acumulado)})

        # Re-ejecutar la query (el cursor fue consumido por la query de naturaleza)
        execute_sp(
            cursor,
            'contabilidad.sp_ObtenerMovimientosLibroMayor',
            mov_params,
            fallback_sql=f"""
            SELECT
                A.Fecha,
                A.NumeroComprobante,
                A.Descripcion AS DescripcionAsiento,
                D.Descripcion AS DescripcionLinea,
                D.Debe,
                D.Haber,
                A.ReferenciaExterna
            FROM DetalleAsientos D
            INNER JOIN AsientosDiario A ON D.AsientoID = A.ID
            INNER JOIN CatalogoCuentas C ON D.CuentaID = C.ID
            WHERE C.Codigo = ? AND {where_clause}
            ORDER BY A.Fecha, A.ID
        """,
        )

        for row in cursor.fetchall():
            debe = decimal.Decimal(str(row.Debe))
            haber = decimal.Decimal(str(row.Haber))

            if es_deudora:
                saldo_acumulado += debe - haber
            else:
                saldo_acumulado += haber - debe

            movimientos.append({
                'Fecha': row.Fecha.strftime('%d/%m/%Y') if row.Fecha else '',
                'Comprobante': row.NumeroComprobante or '',
                'Descripcion': row.DescripcionLinea or row.DescripcionAsiento,
                'Referencia': row.ReferenciaExterna or '',
                'Debe': float(debe),
                'Haber': float(haber),
                'Saldo': float(saldo_acumulado)
            })

        return movimientos

    @staticmethod
    def obtener_catalogo_cuentas(cursor, solo_transaccionales=False):
        """Retorna el catálogo de cuentas completo en estructura jerárquica."""
        filtro = "AND EsTransaccional = 1" if solo_transaccionales else ""
        sp_name = 'contabilidad.sp_ObtenerCatalogoCuentasTransaccionales' if solo_transaccionales else 'contabilidad.sp_ObtenerCatalogoCuentasActivas'

        execute_sp(
            cursor,
            sp_name,
            fallback_sql=f"""
            SELECT ID, Codigo, Nombre, Clase, Grupo, Naturaleza,
                   Nivel, EsTransaccional, Descripcion, CuentaPadreID, Activa
            FROM CatalogoCuentas
            WHERE Activa = 1 {filtro}
            ORDER BY OrdenVisualizacion, Codigo
        """,
        )

        cuentas = []
        for row in cursor.fetchall():
            cuentas.append({
                'id': row.ID,
                'codigo': row.Codigo,
                'nombre': row.Nombre,
                'clase': row.Clase,
                'grupo': row.Grupo,
                'naturaleza': row.Naturaleza,
                'nivel': row.Nivel,
                'es_transaccional': bool(row.EsTransaccional),
                'descripcion': row.Descripcion,
                'padre_id': row.CuentaPadreID,
                'activa': bool(row.Activa)
            })

        return cuentas
