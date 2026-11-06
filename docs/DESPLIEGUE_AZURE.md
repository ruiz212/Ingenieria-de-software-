# Despliegue Python en Azure App Service

El ZIP contiene fuentes y dependencias declaradas, sin entorno virtual. La entrega
usa Kudu ZipDeploy y `.deployment` para solicitar compilación Oryx. No ejecuta
migraciones ni incluye credenciales, datos de usuarios o sesiones de WhatsApp.

## Configuración del servidor

- Runtime Python 3.14, igual al workflow.
- `SCM_DO_BUILD_DURING_DEPLOYMENT=true` antes de desplegar.
- Comando de inicio: `gunicorn --config gunicorn.conf.py run:app`.
- Credenciales y ajustes operativos permanecen en App Service.
- El secreto del publish profile ya existente en GitHub debe corresponder a
  `BrajhersCake` y permitir acceso SCM. No es una credencial para iniciar sesión
  en Azure CLI ni se escribe en el repositorio.

Oryx instala `requirements.txt` y genera `oryx-manifest.toml` y el entorno `antenv`.
Puede servir la aplicación desde `/tmp/<uid>`; no fijar `--chdir` a `wwwroot`.
Guardar datos persistentes de ejecución en almacenamiento apropiado bajo `/home`.

## Validación y entrega

1. Los PR contra `main` ejecutan la suite sin cadena SQL de pruebas y verifican CSS.
2. Se rechaza un paquete al que le falten archivos de arranque o dependencias.
3. Se extrae el ZIP fuera del checkout: se importa `run:app`, se comprueban login
   y kiosco sin biometría y se inicia Gunicorn realmente en Linux.
4. El merge o un workflow manual sobre `main` publica el ZIP mediante
   `/api/zipdeploy?isAsync=true`. Los despliegues de producción se serializan.
   Si Kudu rechaza el envío con HTTP 409, espera hasta diez minutos y vuelve
   a enviar el ZIP completo; no reintenta fallos de red con resultado ambiguo.
5. El job espera el identificador concreto de ese despliegue, comprueba el
   manifiesto Oryx y espera un HTTP 200 del login con formulario CSRF. Una página
   genérica de Azure no cuenta como aplicación lista.

La verificación HTTP es pública y no envía las credenciales SCM al sitio web.
Si falla compilación, revisar Deployment Center. Si falla el login, revisar los
logs del contenedor y confirmar el comando de inicio. El job no imprime el
publish profile ni cuerpos de respuestas SCM que puedan contener secretos.

Un resultado verde verifica arranque público; no certifica SQL, flujos autenticados,
entrega de correo, vinculación WhatsApp ni disponibilidad de todas las APIs externas.

Referencias:
- https://learn.microsoft.com/en-us/azure/app-service/configure-language-python
- https://github.com/projectkudu/kudu/wiki/Deploying-from-a-zip-file-or-url
