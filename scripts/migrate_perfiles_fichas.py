# scripts/migrate_perfiles_fichas.py
"""
Migración y población de datos de Perfiles de Puesto (Fichas Ocupacionales).
Agrega la columna Activo a rrhh.PerfilesPuesto, actualiza SPs y puebla los perfiles
según el documento 'Fichas Ocupacionales Panadería Brajher's Cake'.
"""

import sys
import os

# Asegurar importación de módulos del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.db import get_db_connection

FICHAS = [
    {
        'cargo': 'Limpieza',
        'perfil': (
            'Mantener la higiene, limpieza y desinfección de todas las áreas de la panadería '
            '(producción, mostrador, mesas y oficinas), garantizando el cumplimiento de las normas '
            'de inocuidad alimentaria y creando un ambiente agradable y seguro para clientes y colaboradores.'
        ),
        'obligaciones': (
            '1. Barrer, trapear y desinfectar continuamente el área de ventas, exhibidores y mesas de atención al cliente.\n'
            '2. Realizar la limpieza profunda del área de producción (pisos, paredes, lavaderos y hornos externos) eliminando residuos de harina, grasas y azúcares.\n'
            '3. Recolectar y clasificar los desechos sólidos del local, depositándolos en los basureros correspondientes.\n'
            '4. Controlar y reportar el inventario de insumos de limpieza (cloro, desinfectantes, escobas, bolsas) para su oportuna reposición.'
        ),
        'competencias': (
            '• Habilidad: Primaria completa o secundaria básica. Conocimiento en manejo y mezcla segura de químicos de limpieza básicos. Experiencia de 0 a 1 año en conserjería o limpieza. Sentido común para organizar tiempos y reportar averías.\n'
            '• Esfuerzo: Físico intenso (de pie toda la jornada, agacharse, fregar superficies y cargar baldes/bolsas de basura). Esfuerzo mental mínimo y rutinario.\n'
            '• Responsabilidad: Cuidado de utensilios de limpieza, uso racional de químicos sin desperdicio y colocación obligatoria de señalización de piso mojado.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Panadero Aprendiz',
        'perfil': (
            'Apoyar activamente en los procesos básicos de preparación, pesaje de ingredientes, amasado '
            'y horneado de productos, bajo la estricta dirección de los panaderos de mayor rango, '
            'asegurando el aprendizaje de las recetas y el cumplimiento de los estándares de calidad de Brajher\'s Cake.'
        ),
        'obligaciones': (
            '1. Pesar y medir con exactitud los ingredientes (harina, levadura, azúcar, sal) según las fichas técnicas y órdenes de producción del día.\n'
            '2. Asistir en la carga y descarga de bandejas en los hornos y cuartos de fermentación.\n'
            '3. Realizar el boleo manual, engrase de moldes y preparación de las bandejas para el proceso de horneado.\n'
            '4. Limpiar y desinfectar sus mesas de trabajo, amasadoras y batidoras inmediatamente después de cada uso.'
        ),
        'competencias': (
            '• Habilidad: Bachiller. Deseable cursos técnicos básicos en panadería o pastelería (INATEC) y nociones matemáticas de pesaje. Experiencia formativa de 0 a 1 año. Disposición y destreza manual básica.\n'
            '• Esfuerzo: Físico intenso (de pie toda la jornada, amasado repetitivo y carga de sacos hasta 50 lbs). Esfuerzo mental regular en gramajes y tiempos de fermentación.\n'
            '• Responsabilidad: Cuidado básico de básculas y amasadoras, cero desperdicio de materia prima y cumplimiento estricto de normas de higiene (redecillas y delantales).'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Cajero',
        'perfil': (
            'Atender al cliente con amabilidad y eficiencia en el mostrador, despachar los productos '
            'de panadería y repostería, y procesar los cobros a través del sistema POS, garantizando '
            'un cuadre de caja exacto y una excelente experiencia de compra.'
        ),
        'obligaciones': (
            '1. Recibir y saludar a los clientes, ofrecer sugerencias de productos y empaquetar adecuadamente los panes, postres y bebidas solicitados.\n'
            '2. Registrar con precisión todas las ventas en el sistema informático (POS) y procesar pagos en efectivo, transferencias o tarjetas de crédito/débito.\n'
            '3. Realizar el arqueo de caja (apertura y cierre de turno) entregando el reporte y los valores correspondientes a la Gerencia.\n'
            '4. Mantener surtidas, ordenadas y limpias las vitrinas de exhibición, verificando precios visibles y retirando producto mermado.'
        ),
        'competencias': (
            '• Habilidad: Bachiller o estudiante universitario (Administración, Contabilidad). Manejo fluido de computadoras, sistemas POS y datáfonos. Experiencia de 0 a 1 año en atención y caja. Excelente comunicación y agilidad en cobros.\n'
            '• Esfuerzo: Físico moderado (de pie detrás del mostrador). Esfuerzo mental regular a alto en cobros, cálculo de cambio y cuadre de caja.\n'
            '• Responsabilidad: Custodia y cuidado de terminales POS y valores en efectivo; emisión correcta de facturas y rotación PEPS en vitrinas con pinzas y guantes.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Panadero Junior',
        'perfil': (
            'Ejecutar la preparación, amasado y horneado de productos de panadería y repostería '
            'tradicional, siguiendo las recetas estándar de la empresa, operando maquinaria industrial '
            'de manera independiente y brindando supervisión operativa al Panadero Aprendiz.'
        ),
        'obligaciones': (
            '1. Elaborar masas para panes dulces, salados y repostería básica siguiendo con exactitud las fórmulas de producción diaria.\n'
            '2. Operar independientemente hornos, amasadoras y cilindros, controlando tiempos de fermentación y temperaturas de cocción.\n'
            '3. Decorar y presentar productos de repostería de complejidad media.\n'
            '4. Orientar y corregir al Panadero Aprendiz en sus labores de pesaje, limpieza y preparación de bandejas.'
        ),
        'competencias': (
            '• Habilidad: Bachiller. Técnico Medio en Panadería, Pastelería o Artes Culinarias (INATEC) con carnet de salud vigente. De 2 a 3 años de experiencia comprobable en producción y hornos comerciales. Detección de textura y consistencia de masas.\n'
            '• Esfuerzo: Físico intenso (fuerza de amasado continuo y manipulación de bandejas calientes). Mental regular a alto en cálculo de cocción y memorización de recetas.\n'
            '• Responsabilidad: Uso y programación adecuada de maquinaria industrial, control del rendimiento de masas para evitar mermas y supervisión del Aprendiz.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Panadero Senior',
        'perfil': (
            'Coordinar y ejecutar la producción diaria de las líneas de panadería y repostería fina, '
            'garantizando el estricto cumplimiento de la calidad, reduciendo mermas y dirigiendo al '
            'equipo operativo (Junior y Aprendiz) para cumplir con las metas de abastecimiento de las vitrinas.'
        ),
        'obligaciones': (
            '1. Liderar la elaboración de productos complejos, repostería especializada, pasteles de vitrina y pedidos especiales de clientes.\n'
            '2. Administrar el inventario de materias primas en piso de producción, calculando y solicitando los insumos necesarios para el turno.\n'
            '3. Distribuir las tareas diarias entre el Junior y el Aprendiz, supervisando la calidad del amasado, fermentación y horneado en todo momento.\n'
            '4. Realizar controles de calidad visual y gustativa antes de enviar el producto terminado al área de exhibición o despacho.'
        ),
        'competencias': (
            '• Habilidad: Técnico Especialista en Panadería y Pastelería con formación en costeo de recetas y control de mermas. De 5 a 8 años de trayectoria liderando turnos. Creatividad, resolución de problemas y liderazgo bajo presión.\n'
            '• Esfuerzo: Físico intenso (mesa, horno y supervisión en desplazamiento). Mental alto en coordinación simultánea de horneado y multiplicación de fórmulas.\n'
            '• Responsabilidad: Custodia y reporte de mantenimiento de equipo mayor, alta responsabilidad económica en materia prima, seguridad del personal y calidad de producto.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Cocina',
        'perfil': (
            'Preparar, sazonar y cocinar los alimentos complementarios a la panadería (rellenos para repostería, '
            'bocadillos salados, o menús si el local ofrece servicio de comedor), garantizando un excelente sabor, '
            'textura y estricta inocuidad alimentaria.'
        ),
        'obligaciones': (
            '1. Preparar y cocinar rellenos dulces y salados (crema pastelera, jaleas, carnes, pollos, quesos) necesarios para los productos horneados.\n'
            '2. Picar, porcionar y almacenar correctamente verduras, carnes y embutidos, aplicando la técnica PEPS (Primeras Entradas, Primeras Salidas).\n'
            '3. Elaborar platillos o bocadillos del menú diario según la demanda de la vitrina, manteniendo siempre el mismo estándar de sabor.\n'
            '4. Lavar, desinfectar y organizar todos los utensilios de cocina (ollas, sartenes, cuchillos) y mantener la estufa y campana extractora limpias.'
        ),
        'competencias': (
            '• Habilidad: Bachiller. Técnico en Cocina Profesional o Gastronomía Básica con carnet de manipulación de alimentos MINSA. Experiencia de 1 a 2 años en cocina o comedores. Excelente paladar, rapidez e improvisación culinaria.\n'
            '• Esfuerzo: Físico moderado a intenso (picado y mezcla continua en ollas grandes, de pie). Mental alto en horas pico vigilando fuegos y recetas.\n'
            '• Responsabilidad: Cuidado estricto de cuchillos y estufas industriales; prevención de contaminación cruzada en perecederos; seguridad contra fugas de gas y derrames de aceite hirviendo.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Maestro Panadero',
        'perfil': (
            'Dirigir técnica y operativamente toda el área de producción, diseñando el menú de productos, '
            'estandarizando recetas y garantizando que todas las líneas de panadería y repostería cumplan '
            'con la más alta calidad, mientras entrena y supervisa a todo el equipo operativo.'
        ),
        'obligaciones': (
            '1. Planificar la producción diaria y semanal según los pronósticos de ventas, asignando cargas de trabajo a cada nivel de panaderos.\n'
            '2. Diseñar, costear y estandarizar nuevas recetas para ampliar el catálogo de productos de Brajher\'s Cake.\n'
            '3. Realizar auditorías de calidad continuas sobre las masas, tiempos de fermentación y producto terminado.\n'
            '4. Capacitar técnicamente al personal de menor experiencia y resolver cualquier crisis operativa o fallo en equipos de producción de manera inmediata.'
        ),
        'competencias': (
            '• Habilidad: Técnico Especialista o Maestro en Artes Culinarias, Panadería y Pastelería Internacional con sólidos conocimientos en química de alimentos y administración de cocinas. Más de 12 años dominando todas las áreas y liderando equipos. Visión innovadora y liderazgo.\n'
            '• Esfuerzo: Físico moderado a intenso (supervisión y ejecuciones finas complejas). Mental muy intenso en balanceo de fórmulas, costeo de mermas y gestión operativa.\n'
            '• Responsabilidad: Responsable técnico del taller industrial, rendimiento de materias primas, costos de producción, seguridad industrial y resultados de toda la cuadrilla.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Jefe de Inventario',
        'perfil': (
            'Garantizar el control exacto, resguardo y abastecimiento de las materias primas, insumos y '
            'productos de empaque, asegurando que el área de producción y ventas siempre cuente con los '
            'materiales necesarios sin incurrir en sobrestock o caducidad.'
        ),
        'obligaciones': (
            '1. Recibir a los proveedores, verificar la calidad y cantidad de la materia prima recibida contra las órdenes de compra y facturas.\n'
            '2. Ingresar y descargar diariamente los insumos en el sistema informático de la empresa, manteniendo el inventario teórico cuadrado con el físico.\n'
            '3. Despachar la materia prima al área de producción utilizando el método PEPS (Primeras Entradas, Primeras Salidas).\n'
            '4. Realizar inventarios físicos periódicos (semanales/mensuales) y emitir reportes de faltantes, mermas o productos próximos a vencer para la Gerencia.'
        ),
        'competencias': (
            '• Habilidad: Bachiller técnico, estudiante o Licenciado en Administración, Contabilidad o Logística. Manejo avanzado de Excel y sistemas ERP/Inventario. Experiencia de 2 a 3 años en bodegas de alimentos. Organización espacial y capacidad analítica.\n'
            '• Esfuerzo: Físico moderado a intenso (carga de sacos hasta 50 lbs, estibar cajas pesadas). Mental alto en cuadre numérico continuo y revisión de caducidades.\n'
            '• Responsabilidad: Custodio absoluto de inventarios valorados en miles de córdobas; control de cuartos fríos y carretillas; estiba segura para evitar accidentes laborales.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Contador',
        'perfil': (
            'Registrar, analizar y controlar las operaciones contables, fiscales y financieras de Brajher\'s Cake, '
            'asegurando la presentación oportuna de estados financieros y el cumplimiento estricto de las '
            'obligaciones tributarias y laborales ante las autoridades correspondientes.'
        ),
        'obligaciones': (
            '1. Registrar diariamente los ingresos, egresos, facturas de compras y ventas en el sistema contable de la panadería.\n'
            '2. Elaborar y presentar las declaraciones de impuestos mensuales y anuales ante la DGI y la Alcaldía (Anticipo IR, IVA, IMI, etc.).\n'
            '3. Realizar las conciliaciones bancarias, liquidación de la nómina (pago a empleados) y declaración de planillas ante el INSS y MITRAB.\n'
            '4. Emitir estados financieros (Balance General y Estado de Resultados) y brindar asesoría financiera a la Gerencia para la toma de decisiones.'
        ),
        'competencias': (
            '• Habilidad: Licenciado en Contaduría Pública y Finanzas (deseable CPA). Dominio de leyes tributarias nicaragüenses, laborales y software contable. Experiencia de 3 a 5 años como contador general en pymes. Rigor analítico y control interno.\n'
            '• Esfuerzo: Físico sedentario/mínimo de oficina. Mental muy intenso en concentración analítica de grandes volúmenes de datos numéricos y cuadres al centavo.\n'
            '• Responsabilidad: Integridad y confidencialidad absoluta de libros contables, firmas electrónicas y tokens bancarios; prevención de multas fiscales; auditoría de soportes.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Gerente',
        'perfil': (
            'Planificar, organizar, dirigir y controlar todos los recursos humanos, materiales y financieros '
            'de Brajher\'s Cake, definiendo el rumbo estratégico del negocio para garantizar su rentabilidad, '
            'crecimiento sostenible y posicionamiento en el mercado local.'
        ),
        'obligaciones': (
            '1. Tomar las decisiones estratégicas de negocio: fijación de precios, alianzas con grandes proveedores, planes de expansión y estrategias de marketing.\n'
            '2. Administrar el flujo de efectivo, autorizar los pagos de nómina, gastos operativos e inversiones en maquinaria nueva.\n'
            '3. Contratar, evaluar y gestionar el desarrollo del personal, estableciendo las políticas internas y asegurando un buen clima laboral.\n'
            '4. Supervisar indirectamente todas las áreas (producción, inventario, ventas y finanzas) mediante la revisión de reportes e indicadores de desempeño (KPIs).'
        ),
        'competencias': (
            '• Habilidad: Licenciatura en Administración de Empresas, Ingeniería Industrial, Economía o afines (deseable especialización en Pymes o Finanzas). Más de 5 años de experiencia liderando negocios de alimentos. Visión de negocio, negociación y liderazgo inspirador.\n'
            '• Esfuerzo: Físico ligero (oficina, planta y gestiones externas). Mental máximo como responsable última del éxito comercial, rentabilidad y solución de crisis mayores.\n'
            '• Responsabilidad: Protección patrimonial de infraestructura y activos, cumplimiento legal patronal ante el MITRAB/INSS y autoridad sobre el 100% de colaboradores.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Panadero',
        'perfil': (
            'Responsable de la preparación, amasado, fermentación y horneado de productos de panadería '
            'y repostería conforme a los estándares de calidad e inocuidad de Brajher\'s Cake.'
        ),
        'obligaciones': (
            '1. Elaborar masas para panes dulces, salados y repostería siguiendo recetas de la empresa.\n'
            '2. Controlar tiempos de fermentación y temperaturas óptimas en hornos comerciales.\n'
            '3. Coordinar con el equipo de producción para mantener el surtido continuo de producto fresco en vitrinas.\n'
            '4. Mantener la limpieza y desinfección rigurosa de las áreas de trabajo y utensilios de amasado.'
        ),
        'competencias': (
            '• Habilidad: Experiencia comprobable en panadería comercial, manejo de recetas tradicionales y destreza en manipulación de masas.\n'
            '• Esfuerzo: Físico intenso en amasado continuo, manipulación de bandejas calientes y permanencia de pie.\n'
            '• Responsabilidad: Cuidado de hornos y amasadoras industriales, optimización de ingredientes y cumplimiento de estándares de inocuidad.'
        ),
        'activo': 1,
    },
    {
        'cargo': 'Ingeniero electronico',
        'perfil': (
            'Perfil histórico de soporte técnico, mantenimiento de infraestructura de cómputo, redes '
            'y equipos electrónicos de la panadería. (Puesto desactivado para nuevas contrataciones).'
        ),
        'obligaciones': (
            '1. Diagnóstico y mantenimiento preventivo de equipos de cómputo y terminales del sistema.\n'
            '2. Revisión de cableado de red y soporte en conectividad.'
        ),
        'competencias': (
            '• Habilidad: Formación técnica en electrónica, redes o sistemas computacionales.\n'
            '• Esfuerzo: Moderado de oficina y taller técnico.\n'
            '• Responsabilidad: Soporte técnico sobre equipos asignados.'
        ),
        'activo': 0,  # <-- DESACTIVADO (Soft Delete)
    },
]


def run_migration():
    app = create_app()
    with app.app_context():
        conn = get_db_connection(inject_context=False)
        cursor = conn.cursor()

        print("1. Verificando columna 'Activo' en [rrhh].[PerfilesPuesto]...")
        cursor.execute("""
            IF COL_LENGTH('rrhh.PerfilesPuesto', 'Activo') IS NULL
            BEGIN
                ALTER TABLE [rrhh].[PerfilesPuesto]
                ADD Activo BIT NOT NULL CONSTRAINT DF_PerfilesPuesto_Activo DEFAULT 1;
                PRINT 'Columna Activo agregada con éxito.';
            END
            ELSE
            BEGIN
                PRINT 'Columna Activo ya existía.';
            END
        """)
        conn.commit()

        print("2. Actualizando stored procedure [rrhh].[sp_ListarPerfilesPuesto]...")
        cursor.execute("""
            CREATE OR ALTER PROCEDURE [rrhh].[sp_ListarPerfilesPuesto]
            AS
            BEGIN
                SET NOCOUNT ON;
                SELECT Cargo, PerfilPuesto, Obligaciones, RequisitosCompetencias, ActualizadoEn, Activo
                FROM [rrhh].[PerfilesPuesto]
                ORDER BY Cargo;
            END
        """)
        conn.commit()

        print("3. Creando stored procedure [rrhh].[sp_CambiarEstadoPerfilPuesto]...")
        cursor.execute("""
            CREATE OR ALTER PROCEDURE [rrhh].[sp_CambiarEstadoPerfilPuesto]
                @Cargo NVARCHAR(100),
                @Activo BIT,
                @ActorID INT = NULL,
                @IP VARCHAR(50) = NULL
            AS
            BEGIN
                SET NOCOUNT ON;
                UPDATE [rrhh].[PerfilesPuesto]
                SET Activo = @Activo,
                    ActualizadoEn = SYSUTCDATETIME(),
                    ActualizadoPor = @ActorID
                WHERE Cargo = @Cargo;

                IF @@ROWCOUNT = 0
                BEGIN
                    THROW 51053, 'El cargo especificado no existe.', 1;
                END

                IF @ActorID IS NOT NULL
                BEGIN
                    EXEC [seguridad].[sp_RegistrarAuditoria] @ActorID, 'PERFIL_ESTADO', 'PerfilPuesto', NULL,
                         NULL, @Cargo, @IP;
                END
            END
        """)
        conn.commit()

        print("4. Otorgando permisos de ejecución a roles de la base de datos...")
        try:
            cursor.execute("GRANT EXECUTE ON [rrhh].[sp_ListarPerfilesPuesto] TO [db_rol_gerencia];")
            cursor.execute("GRANT EXECUTE ON [rrhh].[sp_ListarPerfilesPuesto] TO [db_rol_superadmin];")
            cursor.execute("GRANT EXECUTE ON [rrhh].[sp_CambiarEstadoPerfilPuesto] TO [db_rol_gerencia];")
            cursor.execute("GRANT EXECUTE ON [rrhh].[sp_CambiarEstadoPerfilPuesto] TO [db_rol_superadmin];")
            conn.commit()
        except Exception as e:
            print(f"Aviso sobre permisos de roles (no fatal): {e}")

        print("5. Poblando y actualizando perfiles según Fichas Ocupacionales...")
        for f in FICHAS:
            cursor.execute("""
                IF EXISTS (SELECT 1 FROM [rrhh].[PerfilesPuesto] WHERE Cargo = ?)
                BEGIN
                    UPDATE [rrhh].[PerfilesPuesto]
                    SET PerfilPuesto = ?,
                        Obligaciones = ?,
                        RequisitosCompetencias = ?,
                        Activo = ?,
                        ActualizadoEn = SYSUTCDATETIME()
                    WHERE Cargo = ?;
                END
                ELSE
                BEGIN
                    INSERT INTO [rrhh].[PerfilesPuesto] (Cargo, PerfilPuesto, Obligaciones, RequisitosCompetencias, Activo)
                    VALUES (?, ?, ?, ?, ?);
                END
            """, (
                f['cargo'],
                f['perfil'], f['obligaciones'], f['competencias'], f['activo'], f['cargo'],
                f['cargo'], f['perfil'], f['obligaciones'], f['competencias'], f['activo'],
            ))
            print(f" -> Perfil '{f['cargo']}': {'ACTIVO' if f['activo'] else 'INACTIVO'}")
        conn.commit()

        print("6. Asegurando que 'Ingeniero electronico' quede INACTIVO...")
        cursor.execute("UPDATE [rrhh].[PerfilesPuesto] SET Activo = 0 WHERE Cargo LIKE 'Ingeniero%'")
        conn.commit()

        print("7. Verificación final de perfiles:")
        cursor.execute("SELECT Cargo, Activo, LEN(PerfilPuesto), LEN(Obligaciones), LEN(RequisitosCompetencias) FROM [rrhh].[PerfilesPuesto] ORDER BY Cargo")
        for r in cursor.fetchall():
            estado = "ACTIVO" if r[1] else "INACTIVO"
            print(f"  [{estado}] {r[0]} (Perfil: {r[2]} car., Oblig: {r[3]} car., Compet: {r[4]} car.)")

        conn.close()
        print("\n¡Migración y población de perfiles completada con éxito!")


if __name__ == '__main__':
    run_migration()
