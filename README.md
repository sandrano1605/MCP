# MCP

Repositorio de servidores MCP reutilizables para automatización, auditoría y evidencia técnica.

## Principios

- `read-first`: inspeccionar antes de modificar.
- seguridad por defecto: escrituras bloqueadas salvo habilitación y confirmación explícitas.
- herramientas pequeñas y descubribles para que distintos clientes MCP/LLM puedan utilizarlas.
- resultados estructurados y testeables.
- API/formatos oficiales antes que automatización visual cuando sea posible.
- evidencia runtime antes de declarar una operación validada.
- minimizar contexto: manifiestos y diagnóstico primero, detalle completo solo bajo demanda.

## Servidores

### `windows-capture`

Servidor Windows orientado a captura determinística de ventanas y revisión visual de Power BI Desktop.

Ruta relativa:

- `servers/windows-capture/`

Capacidades principales:

- listar ventanas;
- activar una ventana como best-effort;
- capturar una ventana o región;
- wrappers para Power BI Desktop.

### `artel-powerplatform-mcp`

Servidor Python orientado a Power BI, PBIP, PBIR, Microsoft Fabric y Power Platform.

Código:

- `src/artel_powerplatform_mcp/`

Estado V1.4:

- autodiscovery de capacidades;
- health check sin revelar secretos;
- Auth Broker para Fabric, Power BI y Power Platform;
- Microsoft Entra Device Code Flow con tokens solo en memoria;
- inventario local PBIP/TMDL/PBIR/DAX;
- Power BI ExecuteQueries;
- Fabric discovery: workspaces e items;
- Fabric Definition Engine read-only para Reports y Semantic Models;
- soporte Fabric LRO `202 Accepted` + polling;
- decodificación segura `InlineBase64` con o sin padding;
- PBIR Canvas Inspector compartido para fuente local y Fabric;
- análisis de límites del lienzo, solapes, deriva de alineación, `tabOrder` duplicado y patrones de spacing;
- reconocimiento de grupos PBIR para evitar marcar la relación padre/hijo como solape incorrecto;
- lista completa de visuales solo mediante `include_visuals=true`;
- validación de blueprint S510;
- scanner de secretos con salida redactada;
- cliente Power Platform configurable;
- guardas `dry_run`, `confirm` y `ARTEL_ALLOW_WRITES`;
- respuestas MCP estructuradas;
- pruebas unitarias y CI.

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Configura variables a partir de `.env.example`. No guardes `.env` reales en Git.

## Ejecución

```powershell
artel-powerplatform-mcp
```

Primeras tools recomendadas para cualquier cliente MCP:

1. `artel_list_capabilities`
2. `artel_health`
3. `artel_auth_status` para tareas cloud
4. la tool de dominio más pequeña necesaria

## Fabric Definition Engine

Tools:

- `artel_fabric_list_workspaces`
- `artel_fabric_list_items`
- `artel_fabric_get_item`
- `artel_fabric_get_report_definition`
- `artel_fabric_get_semantic_model_definition`

La recuperación de definiciones usa las APIs oficiales `getDefinition`. Aunque la operación sea de lectura, Microsoft exige permisos/scopes de lectura-escritura para esas APIs. El MCP no expone `updateDefinition` en esta versión.

Las definiciones devuelven manifiesto compacto por defecto. El contenido PBIR/TMDL solo se incluye cuando se pide expresamente y queda sujeto a un presupuesto global de caracteres.

## PBIR Canvas Inspector

El motor geométrico es único para local y Fabric:

- `artel_pbir_inspect_local_canvas`
- `artel_fabric_inspect_report_canvas`

Revisa por página:

- `width` / `height` del canvas;
- número de visuales y grupos;
- visuales fuera de límites;
- intersecciones entre visuales;
- pequeñas desviaciones de bordes o centros (`alignment_tolerance`);
- órdenes de tabulación duplicados;
- gaps horizontales y verticales frecuentes.

La estructura geométrica proviene de los archivos PBIR oficiales `page.json` y `visual.json`. El inspector es read-only y no mueve visuales.

Salida compacta por defecto:

```text
page_count
visual_count
overlap_count
bounds_issue_count
alignment_drift_count
pages[].findings
pages[].spacing
```

Usa `include_visuals=true` únicamente cuando el consumidor necesite cada coordenada individual.

## Política de escritura

Por defecto:

```text
ARTEL_ALLOW_WRITES=false
```

Las operaciones mutantes soportadas requieren simultáneamente:

```text
dry_run=false
confirm=true
ARTEL_ALLOW_WRITES=true
```

`DELETE` permanece bloqueado. Fabric Definition Engine y PBIR Canvas Inspector siguen siendo read-only.

## Pruebas

```powershell
python -m compileall -q src
python -m pytest
```

GitHub Actions ejecuta pruebas en Python 3.11, 3.12 y 3.13.

## Roadmap inmediato

1. **V1.4** — PBIR Canvas Inspector read-only y validación contra PBIP real.
2. **V1.5** — TMDL Model Inspector: tablas, medidas, relaciones, roles y dependencias.
3. **V1.6** — Canvas/Model planners `dry_run`: propuestas de cambios sin escribir.
4. **V1.7+** — escrituras quirúrgicas protegidas con checkpoint, rollback y evidencia.

## Integración

Los consumidores no deberían necesitar conocer si una operación se resuelve mediante Python local, REST, Fabric, PAC CLI o automatización visual. El MCP abstrae la implementación y devuelve contratos consistentes.

## Seguridad

Este repositorio no debe contener:

- tokens;
- contraseñas;
- client secrets;
- cookies;
- connection strings con credenciales;
- payloads productivos sensibles.

Si el repositorio se mantiene público, no incorporar lógica operacional propietaria que no deba exponerse. Para configuraciones y playbooks internos, usar un repositorio privado o una capa de configuración separada.
