# Selección y respaldo de Gemini

Autorización: el usuario suministró una clave para configurar y probar Gemini y
solicitó seleccionar modelos y cambiar automáticamente al agotar límites.

1. Consultar catálogo real y documentación oficial; guardar clave únicamente en .env
   ignorado por Git, sin incluirla en código, documentos, comandos del sistema ni logs.
2. Extraer adaptador Gemini a un módulo propio. Orden explícito de modelos de texto
   con herramientas; enfriamiento por modelo, Retry-After/RetryInfo y límite de intentos.
   No cambiar ante claves inválidas ni peticiones incorrectas; no ejecutar herramientas
   dos veces por un cambio de modelo. Preservar firmas de pensamiento del mismo modelo;
   al cambiar, representar resultados anteriores como datos verificados sin reenviar firmas.
3. Pruebas previas para 429, errores transitorios, autenticación, cooldown, respuesta vacía,
   selección y conservación de herramientas; pruebas sintéticas reales acotadas.
4. Actualizar manual, ejecutar suite completa y revisar cambios. No activar WhatsApp ni SQL.

Elección de Codex: Gemini 3.8 Flash principal para atención con herramientas y baja
latencia. Gemini 4 Argon es el modelo insignia de razonamiento, con otro perfil de coste
y latencia. El catálogo incluye modelos especializados que no son intercambiables.
La lista de modelos no garantiza cuota ni autorización efectiva de generación.

Estado: terminado localmente por Codex. Catálogo real: HTTP 200, 60 modelos.
Se configuraron 14 candidatos de texto/herramientas, omitiendo aliases duplicados y
modelos especializados. Orden inicial: 3.8 Flash, 3.5 Flash-Lite, 3.6 Flash.
Prueba real del adaptador: 503 en 3.8 Flash y generación exitosa con 3.5 Flash-Lite.
Suite completa: 456 aprobadas y 104 omitidas. Pruebas específicas: cuotas, RetryInfo,
cooldown, red/servicio, credenciales, respuestas bloqueadas, firmas e IDs de herramientas.
No se activó WhatsApp ni se ejecutaron migraciones SQL. Se preservaron los cambios
de autenticación y demás trabajo previo. Clave fuera del repositorio en `.env`.
