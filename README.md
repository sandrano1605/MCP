# MCP

Repositorio de servidores MCP reutilizables para automatización, auditoría y evidencia técnica.

## Principios

- `read-first`: inspeccionar antes de modificar.
- seguridad por defecto: escrituras bloqueadas salvo habilitación y confirmación explícitas.
- herramientas pequeñas y descubribles para que distintos clientes MCP/LLM puedan utilizarlas.
- resultados estructurados y testeables.
- API/formatos oficiales antes que automatización visual cuando sea posible.
- evidencia runtime antes de declarar una operación validada.
- minimizar contexto: manifests primero, contenido completo solo bajo demanda.

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

Servidor Python orientado a Power BI, PBIP, Microsoft Fabric y Power Platform.

Código:

- `src/artel_powerplatform_mcp/`

Estado V1.3:

- autodiscovery de capacidades;
- health check sin revelar secretos;
- Auth Broker para Fabric, Power BI y Power Platform;
- Microsoft Entra Device Code Flow con tokens solo en memoria;
- inventario local PBIP/TMDL/PBIR/DAX;
- validación de blueprint S510;
- scanner de indicadores de secretos con salida redactada;
- Power BI ExecuteQueries;
- Fabric discovery: workspaces e items;
- Fabric Definition Engine read-only para Reports y Semantic Models;
- soporte de respuestas Fabric LRO `202 Accepted` + polling;
- decodificación segura `InlineBase64` con o sin padding;
- manifiesto PBIR/TMDL compacto por defecto;
- contenido textual opt-in con presupuesto total de caracteres;
- cliente Power Platform configurable;
- guardas `dry_run`, `confirm` y `ARTEL_ALLOW_WRITES`;
- respuestas MCP estructuradas;
- pruebas unitarias y CI.

## Instalación del servidor ARTEL

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Configura variables a partir de `.env.example`. No guardes `.env` reales en Git.

## Ejecución

```powershell
artel-powerplatform-mcp
```

Las primeras tools recomendadas para cualquier cliente MCP son:

1. `artel_list_capabilities`
2. `artel_health`
3. `artel_auth_status`
4. `artel_inspect_bi_project`
5. `artel_scan_embedded_secrets`

## Fabric Definition Engine

Tools principales:

- `artel_fabric_list_workspaces`
- `artel_fabric_list_items`
- `artel_fabric_get_item`
- `artel_fabric_get_report_definition`
- `artel_fabric_get_semantic_model_definition`

La recuperación de definiciones usa las APIs oficiales `getDefinition`. Aunque la operación sea de lectura, Microsoft exige permisos/scopes de lectura-escritura para estas APIs. El servidor no expone ninguna tool de `updateDefinition` en V1.3 y `ARTEL_ALLOW_WRITES=false` permanece como default.

Para ahorrar tokens/contexto, las tools de definición devuelven por defecto:

```text
format
part_count
total_decoded_bytes
paths
parts: path + bytes + tipo
```

El contenido PBIR/TMDL solo se incluye cuando se solicita explícitamente:

```text
include_content=true
```

El presupuesto `max_content_chars` es global para toda la respuesta, no por archivo.

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

`DELETE` permanece bloqueado en esta etapa. Fabric Definition Engine V1.3 no contiene operaciones de escritura.

## Pruebas

```powershell
python -m compileall -q src
python -m pytest
```

GitHub Actions ejecuta las pruebas en Python 3.11, 3.12 y 3.13.

## Roadmap inmediato

1. **V1.3** — Fabric Definition Engine read-only: PBIR/TMDL + LRO.
2. **V1.4** — PBIR Canvas Inspector: páginas, visuales, posiciones, overlaps, alineación y grid.
3. **V1.5** — TMDL Model Inspector: tablas, medidas, relaciones, roles y dependencias.
4. **V1.6** — planners `dry_run`: propuestas de cambios sin escribir.
5. **V1.7+** — escrituras quirúrgicas protegidas, solo después de gates y evidencia.

## Integración

La estrategia recomendada es mantener servidores base independientes y exponer wrappers de dominio sobre capacidades estabilizadas. Los consumidores no deberían necesitar conocer si una operación se resuelve mediante Python local, REST, Fabric, PAC CLI o automatización visual.

## Seguridad

Este repositorio no debe contener:

- tokens;
- contraseñas;
- client secrets;
- cookies;
- connection strings con credenciales;
- payloads productivos sensibles.

Si el repositorio se mantiene público, no incorporar lógica operacional propietaria que no deba exponerse. Para configuraciones y playbooks internos, preferir un repositorio privado o una capa de configuración separada.
