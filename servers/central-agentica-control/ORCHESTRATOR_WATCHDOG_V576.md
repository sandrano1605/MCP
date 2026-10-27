# Supervisor del Orquestador — V5.7.6 (7 paneles)

## Diseño aprobado

La interfaz contiene 6 trabajadores independientes y un séptimo panel ChatGPT dedicado al Orquestador. El panel 7 tiene un proyecto propio configurable. Los controles **▶ Encender Orquestador** y **⏹ Apagar Orquestador** cambian un estado persistido en SQLite; ocultar el panel no detiene a los trabajadores.

Encendido, el Orquestador mantiene su chat conectado y permanece en escucha; solo recibe eventos importantes de los seis agentes y un resumen compacto cada 600 segundos. Python controla el registro de eventos, los estados y la recuperación. ChatGPT utiliza herramientas efectivamente conectadas para diagnosticar incidentes; no se presume que posea permisos que no han sido verificados.

## Autorrecuperación del Orquestador

`orchestrator_self_heal_v576.py` es una política pura. `orchestrator_self_heal_runtime_v576.py` la ejecuta desde el panel dedicado cada 12 segundos y registra en SQLite `coordinator_heartbeat_v576`.

Estados de decisión:

- `DISABLED`: orquestador apagado; ninguna navegación ni envío.
- `LISTENING`: salud correcta; queda escuchando.
- `OBSERVE_INFLIGHT` / `RECONCILE_INFLIGHT`: respuesta o transporte pendiente; nunca interrumpir.
- `WAIT_EDITOR`: editor aún no autenticado/listo.
- `RECONCILE_DELIVERY`: bootstrap o entrega incierta; no reenviar.
- `PRESERVE_DRAFT`: borrador retenido; no borrar ni recargar.
- `WAIT_RATE_LIMIT`: respetar límite ChatGPT.
- `PREPARE_PROJECT_ROLLOVER`: nueva conversación del mismo proyecto, con reglas propias del rollover.
- `RECOVER_COORDINATOR_CHAT`: error reproducible con editor vacío, sin operaciones pendientes y proyecto confirmado.
- `COOLDOWN`: evitar loops automáticos.
- `NEEDS_USER`: permiso, autenticación, proyecto incorrecto o intentos agotados.

El primer intento elegible recarga SOLO la conversación del Orquestador. Si continúa el fallo después de 90 segundos, el segundo abre un chat nuevo SOLO en su proyecto, preservando cola de incidentes y sin repetir paquetes ya entregados. Se registra un intento durable antes de navegar. Tras dos intentos fallidos, `NEEDS_USER`; no ciclos infinitos. Dos minutos de escucha estable cierran el episodio de recuperación.

**No reiniciar los paneles 1–6 por un fallo del Orquestador.** Las operaciones empresariales irreversibles requieren las mismas autorizaciones de siempre.

## Supervisión independiente

El mecanismo anterior supervisa al **ChatGPT Orquestador** de forma independiente del modelo ChatGPT, pero el temporizador corre en el mismo proceso Qt. Si se congela o cierra todo Qt, el temporizador deja de ejecutarse. Queda como siguiente gate vincular el monitor externo MCP a su heartbeat y definir recuperación de proceso completo con exclusión mutua del perfil y preservación de todos los trabajadores. **No declarar resolución de caída total ni funcionamiento desatendido con el equipo apagado sin pruebas adicionales.**

## API, validaciones y evidencias

El endpoint de consulta `GET /api/coordinator/status` expone `self_heal` y `recovery_episode`, sin mostrar el contenido de las conversaciones. El proyecto del Orquestador sigue sin quedar configurado automáticamente; el usuario debe configurar su proyecto válido y autenticarse.

Pruebas aisladas: **73/73 PASS** mediante:

```powershell
python -m unittest discover -s tests_v576 -p 'test_*.py' -q
python -m compileall -q orchestrator_self_heal_v576.py orchestrator_self_heal_runtime_v576.py orchestrator_agent_v576.py app_v4.py
```

Se verifican: apagado, escucha, proyecto, autenticación, editor lento, streaming, envío incierto, borrador, rate limit, rollover, recarga segura, cooldown, segundo intento, presupuesto agotado, persistencia tras reinicio y no interferencia de trabajadores.

## Gates antes de despliegue

- [x] Política y watchdog Python implementados en candidata aislada.
- [x] Botones textuales de encendido y apagado incorporados.
- [x] 73 pruebas aisladas PASS.
- [ ] Probar UI y envío real con proyecto ChatGPT propio y sesión autenticada.
- [ ] Verificar que el ChatGPT Orquestador realmente dispone de APPANOL Trabajo/MCP en su conversación.
- [ ] Integrar heartbeat al supervisor externo y comprobar reinicio ante caída completa de Qt sin interrumpir trabajadores.
- [ ] Validar en canary, respaldar perfiles, pasar E2E y recién entonces promover a versión estable.
