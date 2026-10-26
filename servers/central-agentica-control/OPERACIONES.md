# Runbook — Control de seis agentes

## A. Diagnóstico antes de cambiar nada
1. Verificar la versión y el puerto con `python cli.py status`.
2. Revisar `python cli.py monitor` y `python cli.py agent <n>`.
3. Consultar `python cli.py context <n>`, contrastando `run_id` y proyecto.
4. Si existe generación o transporte incierto, NO reenviar.

## B. Montar los seis paneles
1. `python cli.py prepare-layout 6`.
2. Revisar el plan y la carga RAM.
3. `python cli.py approve <token> APROBAR_CAMBIO_CONTROLADO`.
4. Confirmar exactamente 6 IDs en `/api/status` y la continuidad de 1..4.
5. Montar no significa iniciar: los agentes 5 y 6 requieren chat/proyecto propios.

## C. Arrancar tarea contextual segura
`python cli.py prepare-start 5 solo 100` se acepta únicamente si hay un chat auténtico con contexto persistente, último turno final y sin ejecución incierta. La instrucción se deriva del objetivo y de las tareas pendientes del propio agente.

## D. Restaurar
`python cli.py prepare-restore 2 solo` requiere snapshot persistente del MISMO `run_id` y respuesta final acreditada. La restauración no repite el último envío.

## E. Monitoreo continuo
Ejecutar `python supervisor.py --daemon --interval 60` (una única instancia supervisora). Publica cambios de estado en `%LOCALAPPDATA%\central_agentica_control\supervisor_events.jsonl`. Si Qt deja de responder, el supervisor registra la interrupción; no reinicia ni elimina nada.

## F. Confirmar cierre
Nunca cerrar por porcentaje o señal visual; exigir `done` con evidencia y pendientes vacíos, además del estado DB coherente. Un `needs_user` indica bloqueo verificable, no completitud.

## G. Recuperación de incidentes
`central_record_incident` registra el fallo localmente, y `central_continuous_improvement` propone pruebas específicas. Registrar `action/outcome/evidence` antes de afirmar reparación. No reintentar un `POST` con resultado incierto.

## H. Control Git
Solo versionar código/test/doc sin tokens, cookies, sesiones, dumps o historiales de conversación.
No hacer push del perfil activo. Validar `git status` antes de cualquier commit. Mantener respaldo independiente del SQLite.
