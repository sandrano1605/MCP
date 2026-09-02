---
name: artel-powerplatform
description: Automatiza y audita proyectos Power BI PBIP y flujos Power Automate de ARTEL S.A. Úsala al crear, modificar, probar, reconciliar o diagnosticar modelos semánticos, consultas DAX, informes PBIP, flujos cloud, conexiones, ejecuciones y correos de piloto.
---

# Skill ARTEL Power Platform

## Objetivo

Operar el ciclo local y cloud con evidencia verificable: inspeccionar PBIP/TMDL, consultar el semantic model, construir o modificar flujos, probar una ejecución y reconciliar los resultados. Mantener Power BI/DAX como fuente de verdad numérica.

## Secuencia obligatoria

1. Leer `s510/automate/CURRENT_HANDOFF.md`, `coordination/PROTOCOL.md`, `coordination/AUTONOMOUS_POWER_AUTOMATE_PLAYBOOK.md`, `MCP_TOOLS.md`, `POWER_AUTOMATE_BUILD_GUIDE_V2.md` y `FLOW_BLUEPRINT.json` cuando existan.
2. Ejecutar `git status --short`, identificar branch y preservar cambios no relacionados.
3. Inspeccionar el proyecto con `artel_inspect_bi_project` y validar el blueprint con `artel_validate_s510_blueprint`.
4. Para Power BI, usar `artel_powerbi_execute_dax` con consultas pequeñas, filtros explícitos y límites; no recalcular KPI en el LLM.
5. Para Power Automate, obtener definición completa antes de modificar. Preferir cambio quirúrgico y previsualización; si la API aprobada no está configurada, dejar la operación en `dry_run`.
6. Después de cada cambio, verificar definición AFTER, ejecutar una prueba controlada y revisar inputs/outputs del mismo run.
7. Para correos, certificar subject, body HTML, destinatario piloto y ausencia de expresiones literales crudas.
8. Emitir un Evidence Pack con `GATE`, `RUN_ID`, `FLOW_STATUS`, `ACTION_STATUS`, `CODE_VIEW_CERTIFIED`, `RUNTIME_DATA_RECONCILED`, `OUTLOOK_DELIVERED`, `PRODUCTION_EMAIL` y `RESULT`.

## Guardas de seguridad

- Mantener `PILOT_MODE=true`, `PRODUCCION_HABILITADA=false` y redirección a correo piloto durante certificación.
- No guardar tokens, cookies, contraseñas, destinatarios privados ni cadenas de conexión.
- No declarar `VALIDATED` sin evidencia runtime del mismo run.
- No activar producción, borrar flujos ni enviar correo real sin autorización explícita.
- Las operaciones mutantes requieren `dry_run=false`, `confirm=true` y `ARTEL_ALLOW_WRITES=true`; DELETE permanece bloqueado en la primera versión.
- Si falta autenticación, permiso, licencia, endpoint o política del tenant, devolver `BLOCKED_<CAUSE>` con el dato exacto faltante.

## Reglas S510

- La fecha contractual proviene de `[Fecha Corte S510]`, no de `TODAY()` ni del reloj del flujo.
- En un `Apply to each`, comparar el vendedor actual mediante `item()?['[Vendedor]']`.
- Subject y body deben ser expresiones reales (`@concat(...)`, `@{outputs(...)}`), nunca texto pegado como literal.
- Reconciliar EntradaHoy, FacturadoHoy, EntradaMes y FacturadoMes contra las medidas certificadas del modelo.
- Validar aislamiento: cada fila de resumen, crédito, comercial, proceso y prioridades debe pertenecer al vendedor actual.

## Herramientas propias

- `artel_inspect_bi_project`: inventario local PBIP, SemanticModel, Report, DAX y documentación.
- `artel_validate_s510_blueprint`: verifica guardas críticas del blueprint.
- `artel_scan_embedded_secrets`: busca patrones de secretos sin revelar valores.
- `artel_powerbi_execute_dax`: consulta el semantic model mediante ExecuteQueries.
- `artel_powerplatform_request`: solicitud REST configurable, protegida por dry-run/confirmación.
