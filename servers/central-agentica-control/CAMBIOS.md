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
