# Historial — MCP Orquestador

## V0.1.0 — 2026-10-26
- Inspección Git previa: `sandrano1605/MCP` contiene MCP `windows-capture`; no había control MCP de Central Agéntica. Repositorio local V5.6.5 sin remoto.
- Servidor `stdio` con herramientas de salud, contexto por agente, monitoreo y operaciones de dos fases.
- Guardas anti duplicado: `run_id`, chat, DOM, transporte, borrador, checkpoints y TTL/consumo de aprobación.
- Supervisor de seis agentes con certificación de cierre basada en DB y eventos.
- Matriz de incidentes orientada a regresiones.
- Sin cambios de código en la instancia activa V5.7.5 durante desarrollo del MCP.

- Regresión final: 21/21 PASS; stdio 12 herramientas y 3 lecturas PASS.
- Layout seis agentes PASS; A5 contextual SOLO activo y A6 detenido por ejecución incierta.
- Supervisor separado 60 s y vigilancia horaria consolidada.
- PR de código genérico `sandrano1605/MCP#11` en borrador. App completa pendiente de remoto privado.

## Corrección de monitorización — 2026-10-26
- Detectado en la instancia real: el agente 3 reportaba salud `ERROR` mientras el supervisor lo clasificaba erróneamente `ACTIVE`.
- Se añadió clasificación prioritaria `CHATGPT_ERROR` y `NO_TELEMETRY`, con registro local de incidencias y preservación de borradores/turnos inciertos.
- Regresión: `23/23` pruebas unitarias PASS; MCP stdio `12/12` herramientas registradas, 3 lecturas reales PASS.
- Supervisor independiente relanzado y verificado. La corrección afecta al monitor, **no** reenvía mensajes a agentes ni altera Qt.

## V0.1.2 — 2026-10-26 — Especificación camino feliz V5.7.6
- Documentado procedimiento real de restaurar mismo run y reasignar panel a otro proyecto.
- Caso de error ChatGPT + timeout + borrador tras reload convertido en NO-GO obligatorio: no es ejecución recuperada.
- Añadido `recovery_protocol_v576.py` y herramienta `central_recovery_diagnosis` en el MCP.
- Añadidos 21 tests de regresión para identidad, streaming, borrador, timeout, cierre y no reenvío.
- Batería total 47/47 PASS y humo MCP `stdio`: 13 herramientas, cuatro llamadas de lectura PASS.
- Plano de integración Qt/rollover transaccional y gates QAS en `UPGRADE_SOLO_SIGUE_V576.json`.
- Sin cambios del código del proceso Qt V5.7.5 en uso; release V5.7.6 sigue **NO DESPLEGADO**.

- Reincidencia tras una restauración inicialmente correcta: un agente avanzó a la iteración siguiente y volvió a timeout incierto. Se añadió gate de estabilidad multi-turno y prueba contra reintentos automáticos; V5.7.6 continúa pendiente de integración Qt.
