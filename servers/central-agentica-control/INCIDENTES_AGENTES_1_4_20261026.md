# Central Agéntica — Registro de incidencias y mejora continua A1–A4
Fecha: 2026-10-26. Entorno: AF9328, Central Agéntica V5.7.5.
Alcance: observación de cuatro agentes, recuperación controlada y clasificación de detenciones.
Fuente: API local /api/status, /api/autosigue/status, /api/agent-health, CLI MCP, checkpoints de solo lectura y supervisor_events.jsonl.
**Confidencialidad:** sin conversaciones, credenciales, URL de chat ni documentos empresariales.

## Evidencias e intenciones

| Agente | Propósito autorizado | Estado observado | Motivo de pausa o riesgo | Corrección / próximo paso |
| --- | --- | --- | --- | --- |
| A1 | Preparación segura de México QAS: backup, autenticación, restauración y gates de release | Activo, progresó 7 → 9 → 10/100, con generación visible | Etiquetas LENTO intermitentes. No se acreditó un paro real; falta certificación del despliegue. | Mantener la ejecución y el run existente. Solo clasificar atasco si cesa generación y no hay progreso confirmado; validar backup/SSH/TLS antes de promover. |
| A2 | Volvo ExcelJobs: aislamiento por propietario/centro, ACL y trazabilidad Git | Activo, progresó 67 → 70/100, con generación visible | Transitorios LENTO y WAITING; no equivalen a fallo. La integración sigue bloqueada por aprobación de política A/B2, permisos reales y SUPPORT_HEAD no acreditado. | No reiniciar ni duplicar turnos. Conservar candidato y hashes, resolver política y release contract; continuar verificaciones seguras. |
| A3 | EQUIPAN Facturación: clientes de PRD y comprobación de documentos legales | WAITING_SAFE_WORK, 10/100, health ERROR y RESPONSE_TIMEOUT_UNCONFIRMED; borrador no vacío (5605 caracteres), respuesta posterior al último usuario no confirmada | **Entrega o finalización incierta**. No está demostrada la causa raíz del timeout; el borrador y la secuencia de mensajes impiden un reenvío seguro. | Conservar borrador, no usar Retry, no reenviar ni iniciar otro run. Conciliar journal de transporte, último turno y checkpoint del mismo run; retomar SOLO tras evidencia de estado seguro. |
| A4 | MRP QAS: 752 posiciones ALC/CDQ, matriz preventiva, ADMIN y BAPI TESTRUN sin COMMIT | Activo, 24/100, indicador LENTO pero DOM indica generating=true. HTTP 405 sigue en endpoint GET del servicio activo | **Falso positivo de estancamiento** en supervisor: clasificaba cualquier etiqueta LENTO como NO_PROGRESS incluso durante generación. Problema HTTP 405 relacionado con ruta existente en código pero no cargada por PID activo; recarga pendiente de certificación. | Ajustar clasificador para respetar generating=true, conservar PID/sesión, activar la ruta únicamente con procedimiento QAS controlado y certificar GET autenticado; no ejecutar SAP COMMIT. |

## Cambios implementados y verificados

1. **FIX-001 — evitar falsas alarmas por streaming:** en `supervisor.py`, NO_PROGRESS exige simultáneamente active, health=LENTO y generating=false. Con generating=true se considera ACTIVE, salvo error/timeout prioritario. No fuerza envíos y no desactiva gates.
2. **TEST-001:** regresión `test_slow_health_with_live_generation_is_not_stall` prueba que etiqueta LENTO durante generación se clasifica ACTIVE y no registra incidencia de atasco.
3. **Regresión local del MCP:** `python -m unittest discover -s tests -p test_*.py -v` -> **25/25 PASS**. Las pruebas son simuladas/aisladas y no certifican el despliegue de negocio.
4. **Observación:** el supervisor lateral opera en AF9328 por intervalos de 60 segundos y solo lee/registrа; los cuatro paneles estaban montados, A1/A2/A4 con actividad, A3 en espera protegida. Aplicar/reiniciar el sidecar es distinto de reiniciar agentes; verificar proceso y resultado luego de hacerlo.

## Mejora continua — backlog con criterios de cierre

- **FIX-002 (A3, prioritario):** implementar reconciliación *read-only* por correlación de run, URL de proyecto, último usuario/assistant, turn y checkpoint; diferenciar solicitud enviada de respuesta confirmada. Nunca borrar borrador ni realizar segundo POST mientras outcome sea incierto. **PASS**: prueba de timeout simulado con borrador y respuesta sin confirmar = cero envíos repetidos; prueba de recuperación con checkpoint final propiedad del mismo run = un solo avance permitido.
- **FIX-003 (A4):** incorporar verificación de rutas del servicio activo contra manifest de backend, HTTP GET protegido y estado del PID, con activación QAS transaccional/reversible. **PASS**: endpoint 200 autenticado, 401/403 anónimo, filtrado y CSV auditables; servicio y sesión preservados; sin reconsulta SAP ni COMMIT.
- **FIX-004 (A1/A2):** detectar falta real de progreso mediante combinación de `generating`, firma DOM, contador de turnos, marcas temporales y ventana de persistencia (no un rótulo aislado). **PASS**: generación lenta no dispara recuperación y estancamiento real sostenido genera una sola incidencia deduplicada.
- **FIX-005 (orquestador):** registrar causa, evidencia, fallback, resultado, fecha y estado de la regresión en Git y bitácora local, sin guardar información sensible. Solo declarar DONE con checkpoint final válido, pendientes vacíos y pruebas verificables.

## Restricciones y estado final de esta intervención

- Nunca reiniciar una conversación en vuelo, duplicar un envío incierto, sobrescribir borradores ni omitir autenticación o aprobaciones de despliegue.
- No modificar SAP PRD, no hacer SAP COMMIT, no publicar correos, no promover releases empresariales sin gates.
- **A1/A2/A4:** paneles en línea y ejecución activa observada; esto no significa que su objetivo de negocio esté finalizado.
- **A3:** panel conectado pero ejecución detenida en WAITING_SAFE_WORK. No se certifica reanudación hasta resolver la incertidumbre del transporte y la propiedad del borrador.
- La modificación del supervisor queda **codificada y testeada**; su activación en el proceso lateral requiere verificación independiente de recarga y lectura posterior.

## Cierre técnico del FIX-001 (comprobación posterior)

- Archivo `supervisor.py` corregido en local y en la rama del PR #11.
- Regresión local ejecutada después del cambio: **25/25 pruebas PASS**.
- Se identificó por cmdline el proceso anterior del monitor (`supervisor.py --daemon --interval 60`), y se reemplazó **solo ese sidecar**, sin detener los agentes ni la GUI.
- Nuevo proceso lateral **PID 44604**, comprobado `running` con el mismo intervalo de 60 segundos.
- Lectura posterior de `cli.py monitor`: A1 ACTIVE iteración 11; A2 ACTIVE iteración 71; A3 TIMEOUT_UNCONFIRMED iteración 10; A4 ACTIVE iteración 24. RAM disponible 10.86 GB, CPU 22.4 %, presión NORMAL.
- **Alcance del PASS:** clasificación y supervisión, no continuidad de A3 ni certificación de los releases empresariales. A3 conserva borrador y debe conciliarse.
