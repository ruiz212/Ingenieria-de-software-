# Revisión de rendimiento — 05-11-2026

Alcance autorizado: diagnóstico y optimizaciones locales conservando las reglas de negocio.
No se modificó Azure, no se desplegó ni se accedió a SQL operativo.

## Evidencia y cambios

- El arranque cargaba OpenCV y modelos faciales (43,8 MiB en disco) para todos los módulos.
  Medición local inicial de `create_app`: 5,748 s, en un proceso nuevo, sin cargar `.env`.
  Ahora el servicio se importa al primer uso biométrico; Python serializa la importación.
  El primer reconocimiento paga ese coste; las siguientes llamadas reutilizan el singleton.
  Con el cambio, la misma medición local dio 2,211 s sin importar el servicio facial.
  Son muestras individuales, no un benchmark estadístico ni una medición de Azure.
- Cada resolución de CSS ejecutaba `stat()` sobre el manifiesto, incluso en producción.
  Ahora producción reutiliza el manifiesto; desarrollo conserva la recarga.
  Reiniciar workers al desplegar activos nuevos.
- El comando Docker sobrescribía el puerto dinámico del archivo Gunicorn con 8000.
  Ahora ambas rutas usan explícitamente el archivo de configuración del repositorio.
  Se mantienen los valores de concurrencia existentes sin aumentarlos a ciegas.

## Comprobaciones pendientes en Azure

Validación local: suite general con 437 pruebas aprobadas y 168 omitidas;
tras añadir la comprobación de delegación biométrica, 10 pruebas focalizadas aprobadas.
Los 46 paquetes CSS están vigentes y `git diff --check` no reporta errores.
Las pruebas omitidas incluyen integraciones que necesitan QA; no certifican SQL productivo.
Revisión del diff: se conservan autenticación, roles SQL y reglas de negocio.
No se construyó la imagen Docker ni se ejecutó Gunicorn en este Windows.

No hay CLI Azure ni conector Azure disponible en esta sesión. Confirmar el recurso y SKU
exactos: App Service B1 y una VM de serie B son servicios diferentes. No se puede afirmar
que el cambio de plan sea la causa sin métricas anteriores y actuales.

1. En App Service, comprobar **Always On**. Desactivado, Azure descarga la aplicación
   tras 20 minutos de inactividad. Basic permite activarlo.
2. Para despliegue ZIP, verificar el comando de inicio:
   `gunicorn --config gunicorn.conf.py run:app`.
3. Medir CPU, memoria, tiempo HTTP, cola HTTP y reinicios durante la lentitud.
4. Correlacionar con Azure SQL: CPU/DTU, bloqueos, consultas lentas y región respecto al servidor.
5. Comparar primera petición tras inactividad con peticiones repetidas y navegación autenticada.
   Medir login, tienda, dashboard, POS, DGI y reconocimiento; no usar cargas de escritura
   sobre producción para hacer pruebas.

Fuente: https://learn.microsoft.com/azure/app-service/configure-common
Las mediciones locales de arranque no representan el tiempo de carga real en Azure.

## Incidente de arranque — registros del 06-11-2026 UTC

Los intentos recibidos hasta las 05:22:07 fallan al importar `run`, antes de
ejecutar la aplicación: `ModuleNotFoundError: No module named 'run'` y salida 3.
El mensaje «Container is running» solo confirma el proceso del contenedor; no
confirma que Flask esté listo. Los avisos de certificados preceden al lanzamiento
de Gunicorn y no son la excepción que termina estos intentos.

Evidencia adicional del servidor:

- No encuentra `oryx-manifest.toml`, `antenv` ni `__oryx_packages__` en `wwwroot`.
  Es compatible con un despliegue incompleto o sin compilación, pero los logs
  de arranque no demuestran cuál fue la causa del despliegue.
- Usa Gunicorn 24.1.1 desde `/opt/python`, mientras el repositorio fija 26.2.0.
- Declara `Using worker: sync`; el archivo local define `gthread` y dos hilos.
  No se observa la configuración de concurrencia esperada en esos intentos.
- La primera descarga de imagen dura unos 125 s; los siguientes métodos de
  arranque del contenedor tardan entre 2,8 y 4,1 s. Son fases de plataforma,
  distintas de importar Flask o responder una petición.

Validación local de esta revisión: 10 pruebas aprobadas de empaquetado,
arranque diferido y activos CSS. Se generó un ZIP temporal con el empaquetador
actual: 421 entradas, 39,71 MiB, CRC correcto, archivos requeridos presentes y
`run.py` idéntico al del árbol de trabajo en la raíz. Se comprobaron exclusiones
de `.env`, cargas, cachés, `instance` y `node_modules`. No acredita el contenido
del artefacto que recibió Azure ni se publicó este ZIP.

### Diagnóstico pendiente y recuperación propuesta

En SSH/Kudu de Azure, obtener únicamente rutas, sin abrir secretos:

```sh
find /home/site/wwwroot -maxdepth 3 -type f \( -name run.py -o -name requirements.txt -o -name gunicorn.conf.py -o -name deployment.zip -o -name oryx-manifest.toml -o -name output.tar.gz \) -print
```

Revisar también el resultado del último job de despliegue y su commit, y confirmar
si se ejecutó Oryx con instalación de dependencias. El workflow local ya entrega
`deployment.zip` explícitamente; no se encontró evidencia para cambiar su ruta.

- Si falta `run.py`, comprobar el artefacto del despliegue. Debe contener los
  archivos de la aplicación en la raíz; publicar después de autorizar el despliegue.
- Si está dentro de una subcarpeta, corregir el empaquetado o ajustar `--chdir`
  a la ruta comprobada. No inventar una ruta ni sustituir `run:app` a ciegas.
- Si `run.py` está en la raíz, comprobar el directorio efectivo de Gunicorn y su
  ruta de importación antes de alterar el comando.
- Esta entrega contiene fuente sin entorno virtual: comprobar
  `SCM_DO_BUILD_DURING_DEPLOYMENT=true` y volver a desplegar con compilación
  si está desactivado. Habilitarlo y reiniciar, sin desplegar, no instala por sí
  solo las dependencias que faltan.
- Tras verificar archivos y dependencias, usar el comando previsto:
  `gunicorn --config gunicorn.conf.py run:app`. Confirmar `gthread` y respuesta
  HTTP de la aplicación antes de medir rendimiento.

La revisión inicial no modificó configuración de Azure ni el workflow.
Posteriormente, el usuario autorizó reparación, publicación y merge: la entrega
ahora usa ZipDeploy, exige compilación Oryx y comprueba el arranque desde el ZIP.
El artefacto del último run también contiene `run.py` en la raíz y tiene CRC
correcto. La cancelación de ese run fue manual por el usuario y no se considera
causa. Procedimiento y límites en `DESPLIEGUE_AZURE.md`.

Referencias de Microsoft:
https://learn.microsoft.com/en-us/azure/app-service/configure-language-python
y https://learn.microsoft.com/en-us/azure/app-service/quickstart-python
