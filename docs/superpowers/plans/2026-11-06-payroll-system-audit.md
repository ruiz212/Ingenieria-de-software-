# Reparación de planilla y revisión funcional

Autorización: continuar reparaciones, publicar e integrar en main según instrucciones del usuario. No ejecutar nóminas, cobros, mensajes ni migraciones en producción.

1. Reproducir generación de planilla con empleados sintéticos y consultas de diagnóstico de solo lectura. Comparar firmas SQL y preservar cálculo, restricciones y transacción completa.
2. Añadir regresiones que fallen por la causa encontrada; corregir el contrato o manejo de errores mínimo. Comprobar éxito y rollback ante fallos.
3. Revisar compatibilidad de procedimientos de los demás módulos, distinguiendo parámetros opcionales y alternativas SQLite de incompatibilidades reales. Documentar pendientes que necesiten migración o datos QA.
4. Ejecutar suite completa, validación CSS y pruebas pertinentes de navegador. Revisar diff y secretos antes de commit.
5. Publicar rama, esperar CI, integrar main y verificar despliegue. Registrar matriz por módulo con evidencia y límites; no certificar recorridos operativos que no se ejecutaron.

Archivos previstos: `app/admin/routes_hr.py`, pruebas de regresión de planilla, informe y backlog. Otros archivos solo tras reproducción de un defecto.
