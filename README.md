# MCP

Repositorio de servidores MCP reutilizables para automatización, auditoría y evidencia técnica.

## Principios

- `read-first`: inspeccionar antes de modificar.
- seguridad por defecto: escrituras bloqueadas salvo habilitación y confirmación explícitas.
- herramientas pequeñas y descubribles para que distintos clientes MCP/LLM puedan utilizarlas.
- resultados estructurados y testeables.
- API/formatos oficiales antes que automatización visual cuando sea posible.
- evidencia runtime antes de declarar una operación validada.

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

Servidor Python orientado a Power BI, PBIP y Power Platform.

Código:

- `src/artel_powerplatform_mcp/`

Estado V1.1:

- autodiscovery de capacidades;
- health check sin revelar secretos;
- inventario local PBIP/TMDL/PBIR/DAX;
- validación de blueprint S510;
- scanner de indicadores de secretos con salida redactada;
- Power BI ExecuteQueries;
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
3. `artel_inspect_bi_project`
4. `artel_scan_embedded_secrets`

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

`DELETE` permanece bloqueado en esta etapa.

## Pruebas

```powershell
python -m compileall -q src
pytest
```

GitHub Actions ejecuta las pruebas en Python 3.11 y 3.12.

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
