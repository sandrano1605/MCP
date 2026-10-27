# Contrato del orquestador central

## Estado por agente

Identidad obligatoria: `agent_id=1..6`, `chat_url`, `run_id`, fase, contador, estado del transporte y `task-state`.
No se mezclan proyectos. El último mensaje y un estado de salud GREEN no certifican ejecución terminada.

## Ciclo de trabajo

`MONITOR` → `IDENTIFICAR_OBJETIVO` → `EVALUAR_SEGURIDAD` → `PLANIFICAR` → `APROBAR` → `EJECUTAR` → `VERIFICAR` → `REGISTRAR`.

Un `POST` con respuesta perdida no se reintenta. El token se consume ANTES del envío. Para reanudar:
- Confirmar mismo chat y `run_id`.
- No generación activa, alertas ni borrador distinto.
- Confirmar bloque final `task-state` `working` con evidencia y `safe_next_steps`.
- Confirmar SQLite RUNNING/WAITING_SAFE_WORK y snapshot persistente.
- Reanudar tras aprobación; nunca repetir el turno anterior.

## Supervisión

El supervisor trabaja independiente del Qt GUI y muestrea 1..6 cada 60 s.
Distingue NOT_MOUNTED, ACTIVE, IDLE, DOM_STALE, NO_PROGRESS, FAILED_TRANSPORT, TIMEOUT_UNCONFIRMED, LIMIT_REACHED y DONE_CONFIRMED.
Escribe snapshots y solo cambios materiales (evita spam por variaciones de segundos/CPU).
`DONE_CONFIRMED` requiere estado DB `DECLARED_DONE_WITH_EVIDENCE`, último checkpoint `done`, `pending=[]` y evidencia no vacía.

## Mejora continua

Cada incidencia → diagnóstico y evidencia → hipótesis → prueba de regresión → corrección aislada → batería completa → canary → despliegue → verificación.
El MCP NO edita por sí mismo aplicaciones ni mezcla cuentas/proyectos. Los patrones y pruebas se conservan en Git; las evidencias sensibles permanecen en el host.

## Separación de repositorios

- **MCP genérico**: código/documentación sin rutas privadas, credenciales ni conversaciones; apto para `sandrano1605/MCP`.
- **Central Agéntica operativa**: código, perfiles, snapshots y bases en AF9328; fuente versionada localmente hasta contar con remoto **privado** explícito.
- **Estado operacional**: `%LOCALAPPDATA%` fuera de Git y respaldado con SQLite en modo online.
