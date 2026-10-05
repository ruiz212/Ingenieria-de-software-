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
from app.db import get_db_connection


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
        'Transferencia':    BANCOS_MN,
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
        cursor.execute(
            "SELECT ID FROM CatalogoCuentas WHERE Codigo = ? AND Activa = 1",
            (codigo,)
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
        total_debe = sum(decimal.Decimal(str(d[1])) for d in detalles)
        total_haber = sum(decimal.Decimal(str(d[2])) for d in detalles)
        
        if total_debe != total_haber:
            raise ContabilidadError(
                f"Partida doble violada: Debe ({total_debe}) != Haber ({total_haber}). "
                f"Diferencia: {abs(total_debe - total_haber)}"
            )
        
        if total_debe == 0:
            raise ContabilidadError("El asiento no puede tener todos los montos en cero.")

    @staticmethod
    def _obtener_o_crear_periodo(cursor, mes=None, anio=None):
        """Obtiene o crea automáticamente un periodo contable para el mes/año dado."""
        if mes is None:
            mes = datetime.now().month
        if anio is None:
            anio = datetime.now().year
        
        cursor.execute(
            "SELECT ID, Estado FROM PeriodosContables WHERE Mes = ? AND Anio = ?",
            (mes, anio)
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
        cursor.execute(
            "SET NOCOUNT ON; INSERT INTO PeriodosContables (Mes, Anio, Estado) OUTPUT INSERTED.ID VALUES (?, ?, 'Abierto')",
            (mes, anio)
        )
        return cursor.fetchone()[0]

    @staticmethod
    def _generar_numero_comprobante(cursor, tipo_comprobante_codigo):
        """Genera un número correlativo para el tipo de comprobante dado."""
        cursor.execute(
            "SELECT ID, Prefijo, CorrelativoActual FROM TiposComprobante WHERE Codigo = ?",
            (tipo_comprobante_codigo,)
        )
        row = cursor.fetchone()
        if not row:
            # Si no existe el tipo, usar un formato genérico
            return None, None
        
        tipo_id = row[0]
        prefijo = row[1]
        correlativo = row[2] + 1
        
        cursor.execute(
            "UPDATE TiposComprobante SET CorrelativoActual = ? WHERE ID = ?",
            (correlativo, tipo_id)
        )
        
        numero = f"{prefijo}-{correlativo:06d}"
        return tipo_id, numero

    # ============================================================
    # FUNCIÓN CORE: Crear Asiento de Diario
    # ============================================================

    @classmethod
    def crear_asiento(cls, cursor, descripcion, detalles, usuario_id,
                      tipo_comprobante='DI', referencia_externa=None,
                      tipo_documento='Manual', ip=None, mes=None, anio=None):
        """
        Crea un asiento de diario completo con validación de partida doble.
        
        Args:
            cursor: cursor de pyodbc dentro de una transacción activa
            descripcion: descripción del asiento
            detalles: lista de tuplas (cuenta_codigo, debe, haber, descripcion_linea)
                      o (cuenta_codigo, debe, haber) sin descripción
            usuario_id: ID del usuario que crea el asiento
            tipo_comprobante: código del tipo ('DI','FV','FC','NM','EG','AJ','CI')
            referencia_externa: número de documento origen (ej: FAC-0001)
            tipo_documento: tipo del documento origen
            ip: dirección IP del usuario
            mes, anio: periodo contable (default: mes y año actual)
        
        Returns:
            dict con {asiento_id, numero_comprobante, periodo_id}
        
        Raises:
            ContabilidadError si partida doble falla o periodo cerrado
        """
        # 1. Normalizar detalles a 4 elementos
        detalles_normalizados = []
        for d in detalles:
            if len(d) == 3:
                detalles_normalizados.append((d[0], d[1], d[2], None))
            else:
                detalles_normalizados.append(d)
        
        # 2. Validar partida doble
        cls._validar_partida_doble([(d[0], d[1], d[2]) for d in detalles_normalizados])
        
        # 3. Obtener periodo contable
        periodo_id = cls._obtener_o_crear_periodo(cursor, mes, anio)
        
        # 4. Generar número de comprobante
        tipo_comprobante_id, numero_comprobante = cls._generar_numero_comprobante(
            cursor, tipo_comprobante
        )
        
        # 5. Insertar cabecera del asiento
        cursor.execute("""
            SET NOCOUNT ON;
            INSERT INTO AsientosDiario 
                (PeriodoID, Descripcion, ReferenciaExterna, TipoDocumento, 
                 Estado, UsuarioID, TipoComprobanteID, NumeroComprobante, IP)
            OUTPUT INSERTED.ID
            VALUES (?, ?, ?, ?, 'Contabilizado', ?, ?, ?, ?)
        """, (
            periodo_id, descripcion, referencia_externa, tipo_documento,
            usuario_id, tipo_comprobante_id, numero_comprobante, ip
        ))
        asiento_id = cursor.fetchone()[0]
        
        # 6. Insertar líneas de detalle
        for cuenta_codigo, debe, haber, desc_linea in detalles_normalizados:
            cuenta_id = cls._get_cuenta_id(cursor, cuenta_codigo)
            
            # Validar que la cuenta es transaccional
            cursor.execute(
                "SELECT EsTransaccional FROM CatalogoCuentas WHERE ID = ?",
                (cuenta_id,)
            )
            es_transaccional = cursor.fetchone()
            if es_transaccional and not es_transaccional[0]:
                raise ContabilidadError(
                    f"La cuenta '{cuenta_codigo}' es de agrupación, no es transaccional."
                )
            
            cursor.execute("""
                INSERT INTO DetalleAsientos 
                    (AsientoID, CuentaID, Debe, Haber, Descripcion, DocumentoRelacionado)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                asiento_id, cuenta_id,
                float(debe), float(haber),
                desc_linea, referencia_externa
            ))
        
        return {
            'asiento_id': asiento_id,
            'numero_comprobante': numero_comprobante,
            'periodo_id': periodo_id
        }

    # ============================================================
    # ASIENTO DE REVERSIÓN (Anulación NIIF)
    # ============================================================

    @classmethod
    def revertir_asiento(cls, cursor, asiento_id_original, usuario_id, motivo, ip=None):
        """
        Crea un asiento de reversión (contrapartida) que anula el efecto
        de un asiento anterior. El asiento original se marca como 'Anulado'.
        
        NIIF: Los asientos contabilizados NUNCA se eliminan ni editan.
        """
        # 1. Obtener el asiento original
        cursor.execute("""
            SELECT ID, PeriodoID, Descripcion, ReferenciaExterna, Estado
            FROM AsientosDiario WHERE ID = ?
        """, (asiento_id_original,))
        original = cursor.fetchone()
        
        if not original:
            raise ContabilidadError(f"Asiento #{asiento_id_original} no encontrado.")
        if original.Estado == 'Anulado':
            raise ContabilidadError(f"Asiento #{asiento_id_original} ya fue anulado.")
        if original.Estado == 'Borrador':
            raise ContabilidadError(f"Asiento #{asiento_id_original} está en borrador, no en contabilizado.")
        
        # 2. Obtener detalles del asiento original
        cursor.execute("""
            SELECT C.Codigo, D.Debe, D.Haber, D.Descripcion
            FROM DetalleAsientos D
            JOIN CatalogoCuentas C ON D.CuentaID = C.ID
            WHERE D.AsientoID = ?
        """, (asiento_id_original,))
        lineas_originales = cursor.fetchall()
        
        if not lineas_originales:
            raise ContabilidadError(f"Asiento #{asiento_id_original} no tiene detalle.")
        
        # 3. Crear detalles invertidos (debe↔haber)
        detalles_revertidos = []
        for linea in lineas_originales:
            detalles_revertidos.append((
                linea.Codigo,
                float(linea.Haber),   # Lo que era Haber ahora es Debe
                float(linea.Debe),    # Lo que era Debe ahora es Haber
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
            ip=ip
        )
        
        # 5. Marcar el asiento original como anulado
        cursor.execute("""
            UPDATE AsientosDiario SET 
                Estado = 'Anulado',
                AnuladoPor = ?,
                FechaAnulacion = GETDATE(),
                MotivoAnulacion = ?
            WHERE ID = ? AND Estado = 'Contabilizado'
        """, (usuario_id, motivo, asiento_id_original))
        
        return resultado

    # ============================================================
    # ASIENTOS AUTOMÁTICOS — Integración con módulos
    # ============================================================

    @classmethod
    def contabilizar_venta(cls, cursor, usuario_id, numero_factura, 
                           subtotal, iva, total, pagos, 
                           es_encargo=False, adelanto=0, ip=None):
        """
        Genera el asiento contable automático para una venta POS.
        
        Args:
            pagos: lista de dicts [{metodo, monto}] con los pagos realizados
            es_encargo: si es True, el restante va a CxC Encargos
            adelanto: monto del adelanto (solo para encargos)
        """
        detalles = []
        descripcion = f"Venta POS {numero_factura}"
        
        if es_encargo:
            descripcion += " (Encargo)"
            restante = float(total) - float(adelanto)
            
            # Débito: adelanto a la cuenta según método de pago
            if float(adelanto) > 0:
                for pago in pagos:
                    cuenta_debito = cls.METODO_PAGO_CUENTA.get(pago['metodo'], cls.CAJA_GENERAL_CS)
                    detalles.append((
                        cuenta_debito, float(pago['monto']), 0,
                        f"Adelanto encargo {numero_factura}"
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
                if float(pago['monto']) > 0:
                    cuenta_debito = cls.METODO_PAGO_CUENTA.get(pago['metodo'], cls.CAJA_GENERAL_CS)
                    detalles.append((
                        cuenta_debito, float(pago['monto']), 0,
                        f"Cobro {pago['metodo']} {numero_factura}"
                    ))
        
        # Crédito: Ingresos por Ventas (subtotal sin IVA)
        if float(subtotal) > 0:
            detalles.append((
                cls.VENTAS_PAN, 0, float(subtotal),
                f"Ingreso por venta {numero_factura}"
            ))
        
        # Crédito: IVA Débito Fiscal
        if float(iva) > 0:
            detalles.append((
                cls.IVA_DEBITO_FISCAL, 0, float(iva),
                f"IVA 15% venta {numero_factura}"
            ))
        
        return cls.crear_asiento(
            cursor=cursor,
            descripcion=descripcion,
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='FV',
            referencia_externa=numero_factura,
            tipo_documento='FacturaVenta',
            ip=ip
        )

    @classmethod
    def contabilizar_compra(cls, cursor, usuario_id, compra_id,
                            monto_sin_iva, iva, monto_total,
                            metodo_pago='Contado', referencia=None, ip=None):
        """
        Genera el asiento contable automático para una compra de materia prima.
        
        Si metodo_pago == 'Credito', se registra en CxP Proveedores.
        Si metodo_pago == 'Contado', se debita de Caja o Bancos.
        """
        detalles = []
        ref = referencia or f"COMP-{compra_id}"
        
        # Débito: Inventario de Materia Prima
        detalles.append((
            cls.INV_MATERIA_PRIMA, float(monto_sin_iva), 0,
            f"Compra MP {ref}"
        ))
        
        # Débito: IVA Crédito Fiscal (si aplica)
        if float(iva) > 0:
            detalles.append((
                cls.IVA_CREDITO_FISCAL, float(iva), 0,
                f"IVA crédito fiscal {ref}"
            ))
        
        # Crédito: según forma de pago
        if metodo_pago == 'Credito':
            detalles.append((
                cls.CXP_PROVEEDORES, 0, float(monto_total),
                f"CxP proveedor {ref}"
            ))
        else:
            cuenta_pago = cls.METODO_PAGO_CUENTA.get(metodo_pago, cls.CAJA_GENERAL_CS)
            detalles.append((
                cuenta_pago, 0, float(monto_total),
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
                            cargo='Admin', ip=None):
        """
        Genera el asiento contable automático para una nómina individual.
        Clasifica los gastos según el cargo del empleado (Admin vs Ventas vs Producción).
        """
        detalles = []
        ref = f"NOM-{nomina_id}"
        cargo_lower = cargo.lower()
        
        # Determinar cuentas de gasto según área del empleado
        if 'panadero' in cargo_lower or 'produccion' in cargo_lower or 'hornero' in cargo_lower:
            cuenta_sueldo = cls.MOD_PANADEROS
            cuenta_inss_pat = cls.CIF  # CIF incluye INSS patronal de producción
            cuenta_inatec = cls.CIF
        elif 'vendedora' in cargo_lower or 'dependienta' in cargo_lower or 'cajera' in cargo_lower:
            cuenta_sueldo = cls.SUELDOS_VENTAS
            cuenta_inss_pat = cls.INSS_PATRONAL_VENTAS
            cuenta_inatec = cls.INATEC_VENTAS
        else:
            cuenta_sueldo = cls.SUELDOS_ADMIN
            cuenta_inss_pat = cls.INSS_PATRONAL_ADMIN
            cuenta_inatec = cls.INATEC_ADMIN
        
        # DÉBITOS (Gastos)
        detalles.append((cuenta_sueldo, float(salario_bruto), 0, f"Sueldo {empleado_nombre}"))
        
        if float(inss_patronal) > 0:
            detalles.append((cuenta_inss_pat, float(inss_patronal), 0, f"INSS Patronal {empleado_nombre}"))
        
        if float(inatec) > 0:
            detalles.append((cuenta_inatec, float(inatec), 0, f"INATEC {empleado_nombre}"))
        
        # CRÉDITOS (Obligaciones)
        detalles.append((cls.SUELDOS_POR_PAGAR, 0, float(salario_neto), f"Neto a pagar {empleado_nombre}"))
        
        if float(inss_laboral) > 0:
            detalles.append((cls.INSS_LABORAL_POR_PAGAR, 0, float(inss_laboral), f"INSS Lab. {empleado_nombre}"))
        
        if float(ir_retenido) > 0:
            detalles.append((cls.IR_LABORAL_POR_PAGAR, 0, float(ir_retenido), f"IR Ret. {empleado_nombre}"))
        
        if float(inss_patronal) > 0:
            detalles.append((cls.INSS_PATRONAL_POR_PAGAR, 0, float(inss_patronal), f"INSS Pat. x pagar {empleado_nombre}"))
        
        if float(inatec) > 0:
            detalles.append((cls.INATEC_POR_PAGAR, 0, float(inatec), f"INATEC x pagar {empleado_nombre}"))
        
        if float(pension_alimenticia) > 0:
            detalles.append((cls.PENSIONES_POR_PAGAR, 0, float(pension_alimenticia), f"Pensión alim. {empleado_nombre}"))
        
        if float(vales_descontados) > 0:
            detalles.append((cls.ANTICIPOS_EMPLEADOS, 0, float(vales_descontados), f"Descuento vales {empleado_nombre}"))
        
        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Nómina {empleado_nombre} — {ref}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='NM',
            referencia_externa=ref,
            tipo_documento='Nomina',
            ip=ip
        )

    @classmethod
    def contabilizar_egreso(cls, cursor, usuario_id, concepto, monto,
                            cuenta_gasto=None, metodo_pago='Efectivo',
                            referencia=None, ip=None):
        """
        Genera el asiento contable automático para un egreso privado.
        
        Args:
            cuenta_gasto: código de la cuenta de gasto (default: Gastos Varios Admin)
            metodo_pago: 'Efectivo', 'Transferencia', etc.
        """
        if cuenta_gasto is None:
            cuenta_gasto = cls.GASTOS_VARIOS_ADMIN
        
        cuenta_pago = cls.METODO_PAGO_CUENTA.get(metodo_pago, cls.CAJA_GENERAL_CS)
        ref = referencia or f"EGR-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        detalles = [
            (cuenta_gasto, float(monto), 0, concepto),
            (cuenta_pago, 0, float(monto), f"Pago {metodo_pago} — {concepto}"),
        ]
        
        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Egreso: {concepto}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='EG',
            referencia_externa=ref,
            tipo_documento='EgresoPrivado',
            ip=ip
        )

    @classmethod
    def contabilizar_vale(cls, cursor, usuario_id, empleado_nombre,
                          monto, metodo_pago='Efectivo', referencia=None, ip=None):
        """
        Genera el asiento contable automático para un vale a empleado.
        El vale se registra como un anticipo (activo) que se descontará en nómina.
        """
        cuenta_pago = cls.METODO_PAGO_CUENTA.get(metodo_pago, cls.CAJA_GENERAL_CS)
        ref = referencia or f"VALE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        detalles = [
            (cls.ANTICIPOS_EMPLEADOS, float(monto), 0, f"Vale a {empleado_nombre}"),
            (cuenta_pago, 0, float(monto), f"Desembolso vale {empleado_nombre}"),
        ]
        
        return cls.crear_asiento(
            cursor=cursor,
            descripcion=f"Vale a empleado: {empleado_nombre}",
            detalles=detalles,
            usuario_id=usuario_id,
            tipo_comprobante='EG',
            referencia_externa=ref,
            tipo_documento='ValeEmpleado',
            ip=ip
        )

    @classmethod
    def contabilizar_merma(cls, cursor, usuario_id, producto_nombre,
                           cantidad, costo_unitario_estimado,
                           motivo='Pan Frio', referencia=None, ip=None):
        """
        Genera el asiento contable automático para una merma.
        Traslada el costo del inventario de productos terminados al gasto por merma.
        """
        monto = float(cantidad) * float(costo_unitario_estimado)
        ref = referencia or f"MERMA-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
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

    @staticmethod
    def obtener_saldo_cuenta(cursor, cuenta_codigo, fecha_corte=None):
        """
        Calcula el saldo actual de una cuenta contable.
        El saldo se calcula según la naturaleza de la cuenta:
        - Deudora: Debe - Haber
        - Acreedora: Haber - Debe
        """
        params = [cuenta_codigo]
        filtro_fecha = ""
        if fecha_corte:
            filtro_fecha = "AND A.Fecha <= ?"
            params.append(fecha_corte)
        
        cursor.execute(f"""
            SELECT 
                C.Naturaleza,
                ISNULL(SUM(D.Debe), 0) AS TotalDebe,
                ISNULL(SUM(D.Haber), 0) AS TotalHaber
            FROM CatalogoCuentas C
            LEFT JOIN DetalleAsientos D ON D.CuentaID = C.ID
            LEFT JOIN AsientosDiario A ON D.AsientoID = A.ID 
                AND A.Estado = 'Contabilizado' {filtro_fecha}
            WHERE C.Codigo = ?
            GROUP BY C.Naturaleza
        """, (*params[1:], params[0]))
        
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
        elif fecha_corte:
            filtro = "AND A.Fecha <= ?"
            params.append(fecha_corte)
        
        cursor.execute(f"""
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
            WHERE A.Estado = 'Contabilizado'
              AND C.EsTransaccional = 1
              {filtro}
            GROUP BY C.Codigo, C.Nombre, C.Clase, C.Naturaleza, C.Nivel
            HAVING ISNULL(SUM(D.Debe), 0) != 0 OR ISNULL(SUM(D.Haber), 0) != 0
            ORDER BY C.Codigo
        """, params)
        
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
        filtros = ["A.Estado = 'Contabilizado'"]
        params = [cuenta_codigo]
        
        if periodo_id:
            filtros.append("A.PeriodoID = ?")
            params.append(periodo_id)
        if fecha_inicio:
            filtros.append("A.Fecha >= ?")
            params.append(fecha_inicio)
        if fecha_fin:
            filtros.append("A.Fecha <= ?")
            params.append(fecha_fin)
        
        where_clause = " AND ".join(filtros)
        
        cursor.execute(f"""
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
        """, params)
        
        # Obtener naturaleza para calcular saldo acumulado
        cursor.execute(
            "SELECT Naturaleza FROM CatalogoCuentas WHERE Codigo = ?",
            (cuenta_codigo,)
        )
        nat_row = cursor.fetchone()
        es_deudora = nat_row and nat_row[0] == 'Deudora'
        
        movimientos = []
        saldo_acumulado = decimal.Decimal('0')
        
        # Re-ejecutar la query (el cursor fue consumido por la query de naturaleza)
        cursor.execute(f"""
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
        """, params)
        
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
        
        cursor.execute(f"""
            SELECT ID, Codigo, Nombre, Clase, Grupo, Naturaleza, 
                   Nivel, EsTransaccional, Descripcion, CuentaPadreID, Activa
            FROM CatalogoCuentas
            WHERE Activa = 1 {filtro}
            ORDER BY OrdenVisualizacion, Codigo
        """)
        
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
