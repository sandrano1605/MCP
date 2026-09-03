# MCP

Repositorio de servidores MCP reutilizables para automatización, auditoría y evidencia técnica.

## Principios

- `read-first`: inspeccionar antes de modificar.
- seguridad por defecto: escrituras bloqueadas salvo habilitación y confirmación explícitas.
- tools pequeñas, autocontenidas y descubribles para que distintos clientes MCP/LLM puedan utilizarlas.
- resultados estructurados y testeables.
- API y formatos oficiales antes que automatización visual cuando sea posible.
- evidencia runtime antes de declarar una operación validada.
- minimizar contexto: resumen y diagnóstico primero; detalle completo solo bajo demanda.
- separar explícitamente análisis estático de validación runtime.

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

Servidor Python orientado a Power BI, PBIP, PBIR, TMDL, Microsoft Fabric y Power Platform.

Código:

- `src/artel_powerplatform_mcp/`

Estado V1.5:

- autodiscovery de capacidades y health check seguro;
- Auth Broker para Fabric, Power BI y Power Platform;
- Microsoft Entra Device Code Flow con tokens solo en memoria;
- inventario local PBIP/TMDL/PBIR/DAX;
- Power BI ExecuteQueries;
- Fabric discovery: workspaces e items;
- Fabric Definition Engine read-only para Reports y Semantic Models;
- soporte Fabric LRO `202 Accepted` + polling;
- decodificación segura `InlineBase64` con o sin padding;
- PBIR Canvas Inspector compartido entre fuente local y Fabric;
- clasificación semántica de overlaps: layering esperado, posible oclusión, overlay de contenido y overlap genérico;
- visuales ocultos fuera del análisis geométrico por defecto;
- TMDL Model Inspector compartido entre fuente local y Fabric;
- inventario de tablas, columnas, medidas, particiones, relaciones y roles/RLS;
- cross-filter y cardinalidad solo cuando están declarados en TMDL, sin inferir valores ausentes;
- dependencias DAX/RLS lexicales marcadas como `STATIC_LEXICAL`;
- expresiones DAX/RLS ocultas por defecto y disponibles solo bajo demanda;
- validación de blueprint S510;
- scanner de secretos con salida redactada;
- cliente Power Platform configurable;
- guardas `dry_run`, `confirm` y `ARTEL_ALLOW_WRITES`;
- respuestas MCP estructuradas;
- pruebas unitarias y CI en Python 3.11, 3.12 y 3.13.

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

El consumidor no debería necesitar rutas internas, blobs Base64 ni conocer qué cliente REST usa el servidor.

## Fabric Definition Engine

Tools principales:

- `artel_fabric_list_workspaces`
- `artel_fabric_list_items`
- `artel_fabric_get_item`
- `artel_fabric_get_report_definition`
- `artel_fabric_get_semantic_model_definition`

Las definiciones se obtienen mediante `getDefinition`. El contenido PBIR/TMDL completo no se devuelve por defecto; se priorizan manifiestos compactos y presupuestos globales de contenido.

## PBIR Canvas Inspector

Tools:

- `artel_pbir_inspect_local_canvas`
- `artel_fabric_inspect_report_canvas`

El mismo motor analiza PBIR local y PBIR recuperado desde Fabric. Revisa:

- tamaño del canvas;
- visuales activos y ocultos;
- visuales fuera de límites;
- overlaps e intersecciones;
- z-order;
- pequeños desvíos de alineación entre visuales no superpuestos;
- `tabOrder` duplicado;
- patrones de spacing.

Los overlaps se clasifican, entre otros, como:

```text
EXPECTED_LAYERING
POTENTIAL_OCCLUSION
CONTENT_OVERLAY
GENERIC_OVERLAP
```

Un `EXPECTED_LAYERING`, por ejemplo un shape de fondo debajo de contenido, puede registrarse como información sin convertir el canvas completo en `REVIEW`. Un shape por encima de contenido sigue requiriendo revisión.

La salida se limita al `ACTIVE_REPORT_DEFINITION`: respaldos históricos fuera del directorio activo no se mezclan con el reporte vigente.

## TMDL Model Inspector

Tools:

- `artel_tmdl_inspect_local_model`
- `artel_fabric_inspect_semantic_model`

El inspector procesa la definición TMDL activa y entrega, por defecto, un resumen compacto de:

```text
table_count
column_count
measure_count
partition_count
relationship_count
role_count
table_permission_count
rls_present
rls_secured_tables
cross_filtering_behavior_counts
```

Además devuelve las tablas resumidas, las relaciones y los roles/RLS.

Las relaciones incluyen, cuando TMDL lo declara:

- `fromColumn` / `toColumn`;
- tablas y columnas de origen/destino;
- `fromCardinality` / `toCardinality`;
- `crossFilteringBehavior`;
- `securityFilteringBehavior`;
- estado activo.

Si la cardinalidad no aparece explícitamente, el inspector devuelve `None` y `cardinality_explicit=false`; no inventa una cardinalidad basada en supuestos.

Las expresiones de medidas y filtros RLS no salen por defecto. Se mantienen metadatos seguros como longitud, hash SHA-256 y referencias léxicas. Para diagnóstico explícito se puede solicitar:

```text
include_measures=true
include_columns=true
include_expressions=true
```

Las referencias de expresiones se identifican como `STATIC_LEXICAL`: sirven para navegación y auditoría preliminar, no reemplazan al motor Tabular.

La salida marca siempre:

```text
analysis_mode=STATIC_TMDL
semantic_runtime_validated=false
```

Por tanto, detectar un rol o filtro en TMDL **no certifica aislamiento RLS**. La certificación vendedor/usuario requiere ExecuteQueries o evidencia runtime equivalente con la identidad adecuada.

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

`DELETE` permanece bloqueado. Fabric Definition Engine, Canvas Inspector y Model Inspector son read-only.

## Pruebas

```powershell
python -m compileall -q src
python -m pytest
```

GitHub Actions ejecuta pruebas en Python 3.11, 3.12 y 3.13.

## Roadmap inmediato

1. **V1.5** — TMDL Model Inspector read-only y calibración contra S510 real.
2. **V1.6** — Canvas/Model planners `dry_run`: propuestas determinísticas de cambio sin escribir.
3. **V1.7** — checkpoint/diff/rollback y mutaciones PBIR/TMDL locales protegidas.
4. **V1.8+** — despliegue Fabric `updateDefinition` protegido y evidencia post-deploy.
5. **Posterior** — Power Automate engine quirúrgico y certificación multi-vendedor/routing.

## Integración para cualquier LLM

El contrato busca que un cliente compatible con MCP pueda comenzar por `artel_list_capabilities`, seleccionar una tool de dominio y recibir un resultado consistente sin conocer si internamente se usó Python local, REST, Fabric, PAC CLI o una automatización visual.

## Seguridad

Este repositorio no debe contener:

- tokens;
- contraseñas;
- client secrets;
- cookies;
- connection strings con credenciales;
- payloads productivos sensibles.

Si el repositorio se mantiene público, no incorporar configuración, identificadores ni lógica operacional propietaria que no deba exponerse. Para configuración ARTEL, playbooks internos, tenant/workspace IDs y material operativo, usar una capa privada separada o convertir el repositorio a privado antes de incorporarlos.
