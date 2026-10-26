# Camino feliz y recuperación SOLO / Sígueme — contrato V5.7.6

**Estado:** procedimiento documentado y probado en MCP; **integración automática Qt pendiente**.
Esta guía cubre hasta seis agentes. La aplicación operativa continúa en V5.7.5.
Ningún resultado de un POST incierto se repite a ciegas.

## 1. Camino feliz A: restaurar la misma ejecución

Aplicar únicamente cuando el agente debe continuar el **mismo** objetivo, conversación/proyecto y `run_id`.

1. Leer `GET /api/status`, `/api/autosigue/status`, `/api/agent-health`, `/api/recovery/status`; no interferir con otros agentes.
2. Consultar el último turno visible y el SQLite en **solo lectura**. Confirmar URL, proyecto, `run_id`, emisor y orden de mensajes.
3. Verificar `ready=true`, `finalized=true`, `isGenerating=false`, **respuesta posterior al último usuario** y checkpoint `task-state` `working` del mismo `run_id`, con evidencias y `safe_next_steps`.
4. Confirmar **sin borrador**, sin alertas, sin petición en vuelo ni error de entrega sin conciliar. Hacer snapshot con hash/backup SQLite; usar `prepare-restore` cuando cumpla sus condiciones.
5. En caso de migración de conversación, exigir nuevo editor autenticado **en el mismo proyecto** y mantener identidad del trabajo. El protocolo no debe enviar el turno ya respondido.
6. Ejecutar el único cambio preparado, con aprobación/control transaccional, y verificar `run_id` idéntico, contador no retrocedido, `phase=WAITING/RESPONSE`, `solo_enabled=true` y una sola continuación nueva.
7. Registrar `action/outcome/evidence` y monitorizar respuesta/avance. No afirmar reparación por un simple HTTP 202.

**Evidencia de implementación real:** un caso de MRP QAS recuperó exactamente el mismo `run_id` tras verificar último checkpoint; quedó `WAITING` en la iteración 23, sin reenvío del turno antiguo. La recuperación usó un cambio controlado de estado del controlador y del DB; **no generalizar el rearme del DB** sin la próxima implementación transaccional dentro de Qt y sus pruebas. Las operaciones SAP permanecieron de solo lectura.

## 2. Camino feliz B: cambiar la tarea de un panel libre

1. Detener solo el **controlador elegido**, conservar chat y estado de su tarea antigua, y esperar a que concluya cualquier respuesta activa.
2. Verificar que no quedan borradores externos ni mensajes inciertos; respaldar URL, `run_id`, checkpoint y hash de último turno.
3. Encontrar el proyecto nuevo desde su **ruta local y estado real**, no de una instrucción inventada; inspeccionar su checkpoint más reciente, respaldos, pruebas y gates pendientes.
4. Abrir **una sola vez** una conversación perteneciente al proyecto correcto (no crear una conversación en el proyecto equivocado). Verificar editor autenticado, sin borrador y sin respuesta generándose.
5. Iniciar nuevo `run_id` contextual con instrucción específica, `mode=count`, `solo_enabled=true`, límite controlado y prohibiciones de PRD/SAP/correos.
6. Verificar API, persistencia, URL de proyecto y primera iteración reconocida **antes de declararlo trabajando**.

**Evidencia de implementación real:** un panel liberado se asignó a MASTER_OPERACIONES / Informe de Venta; el antiguo proyecto MRP quedó preservado. Se verificó el nuevo `run_id`, `solo_enabled=true`, iteración 1 y generación activa. La certificación empresarial del PBIP sigue siendo tarea del agente, no se declaró DONE.

## 3. Camino no feliz C: Error de ChatGPT + timeout + borrador

Caso detectado en vivo: `Unknown error / Retry`, `RESPONSE_TIMEOUT_UNCONFIRMED` y un borrador largo en el editor. Tras **un único reload conservador** y un respaldo SQL comprobado, desapareció la alerta, pero el borrador seguía presente. Que haya una respuesta antigua finalizada **NO prueba** que se haya respondido al turno más reciente.

Secuencia obligatoria:

1. Snapshot local (URL, `run_id`, último user/assistant, hash y longitud del borrador; SQLite backup íntegro).
2. Una inspección controlada sin pulsar **Retry**. Si la recarga está permitida, hacerlo **una sola vez** por intento, con marcador persistente previo.
3. Comparar hash/identidad del último turno y ledger del envío; detectar nuevo borrador, otra autoría, otro mensaje o resultado incierto.
4. Si permanece borrador o incertidumbre: decisión `PRESERVE_DRAFT` o `RECONCILE_UNCERTAIN`; **NO** reactivar envíos ni borrar contenido, ni marcar `ACTIVE` como si trabajara.
5. Registrar bloqueo accionable, continuar supervisando los otros agentes y solo reanudar cuando exista evidencia verificable de entrega/ausencia de entrega y los gates de control.

**Resultado del caso real:** bloqueo preservado, **no** reparación final. Esta negativa es un PASS de seguridad, no una falla a ocultar.

## 4. Contrato técnico de la próxima versión

Módulo puro `recovery_protocol_v576.py`; entrada: estado controlador, DOM fresco, DB, checkpoint y snapshot. Salida: `action`, `reason`, `next_gate`, elegibilidad para preparar acciones. Nunca envía mensajes ni modifica la sesión.

Clasificaciones cubiertas: `MOUNT_PANEL`, `RESTORE_READABILITY`, `PROJECT_MISMATCH`, `OBSERVE_STREAM`, `RECONCILE_DELIVERY`, `PRESERVE_DRAFT`, `RECONCILE_ERROR`, `RECONCILE_UNCERTAIN`, `TRANSPORT_ERROR`, `VERIFY_DONE`, `VERIFY_ROLLOVER`, `RECONCILE_CONTROLLER`, `KEEP_RUNNING`, `NEEDS_USER`, `PREPARE_SAME_RUN_RESTORE`, `PREPARE_CONTEXTUAL_START`, `RECONCILE_PREVIOUS_RUN`.

Nueva herramienta consultiva: `central_recovery_diagnosis(agent_id)`.
CLI: `python cli.py recovery-diagnosis 3` (igual para 1..6).

## 5. Gates antes de incorporar en SOLO / Sígueme (V5.7.6)

- [x] Implementar diagnóstico sin side effects; prioritizar bloqueos por borrador/error/transporte.
- [x] Pruebas de la matriz de casos en aislamiento y humo MCP reales.
- [x] Demostrar que el caso con borrador no autoriza reenvío.
- [ ] Integrar el contrato al controlador Qt y su delivery journal en una **copia candidata aislada**. Ningún cambio en vivo por esta guía.
- [ ] Gate transaccional de restauración en Qt que elimine rearme manual de SQLite, compruebe identidad y proteja contra colisiones.
- [ ] Probar rollover mismo proyecto, múltiples agentes concurrentes, reinicio/crash entre ACK y persistencia, borrador, duplicidad e idempotencia.
- [ ] Ejecutar piloto QAS controlado, evidenciar hash/versiones, comparar resultados antes y después y disponer de rollback.
- [ ] Revisar PR y activar solo después de resultados completos. **No** declarar V5.7.6 desplegada mientras falten gates.

## 6. Comandos de verificación

En la carpeta MCP, desde APPANOL Trabajo:

~~~powershell
python cli.py status
python cli.py monitor
python cli.py recovery-diagnosis 3
python -m unittest discover -s tests -p "test_*.py" -q
python smoke_stdio.py
~~~

**Restricciones permanentes:** no SAP COMMIT, no PRD/escrituras externas sin gates, no Repeat/Retry automático ante incertidumbre; los archivos de conversaciones, credenciales, SQLite y capturas operativas permanecen únicamente en el host autorizado.
