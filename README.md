# MCP

Repositorio base para servidores MCP utilitarios, con foco en flujos reales de Power BI Desktop y otras apps de Windows.

## Estado actual

Servidor disponible:

- `windows-capture`

Ruta:

- [servers/windows-capture](C:\Users\alonso.moya\OneDrive - ARTEL S.A\Escritorio\Modelo datos power BI\power-MCP\MCP\servers\windows-capture)

## Objetivo del repo

Separar MCPs utilitarios del repo operativo principal de Power BI para:

- mantener servidores reutilizables,
- probar capacidades nuevas en un repo limpio,
- documentar integración antes de incrustarlas en otros MCP.

## Servidor actual: `windows-capture`

Capacidades:

- listar ventanas de Windows,
- activar una ventana,
- capturar una ventana específica,
- capturar una región puntual,
- wrappers orientados a Power BI Desktop.

Tools:

- `windows_list_windows`
- `windows_activate_window`
- `windows_capture_window`
- `windows_capture_region`
- `windows_get_foreground_window`
- `powerbi_list_desktop_windows`
- `powerbi_activate_report_window`
- `powerbi_capture_report_window`

## Estructura

- `servers/windows-capture/server.py`
- `servers/windows-capture/README.md`
- `servers/windows-capture/requirements.txt`
- `docs/POWERBI_INTEGRATION.md`
- `.mcp.json.example`
- `AGENTS.md`

## Requisitos

- Windows
- Python 3.10+
- `mcp`
- `pywin32`

Instalación sugerida:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\servers\windows-capture\requirements.txt
```

## Ejecución

```powershell
.\.venv\Scripts\python.exe .\servers\windows-capture\server.py
```

## Prueba rápida

```powershell
.\.venv\Scripts\python.exe .\servers\windows-capture\server.py --self-test --title "analisis_disponibilidad"
```

## Configuración MCP

Ejemplo:

- [.mcp.json.example](C:\Users\alonso.moya\OneDrive - ARTEL S.A\Escritorio\Modelo datos power BI\power-MCP\MCP\.mcp.json.example)

## Integración futura

Este repo deja el servidor aislado y estable.

La incrustación posterior recomendada es:

1. probar el MCP aquí,
2. usarlo desde `.mcp.json` del workspace,
3. si la capacidad se consolida, agregar wrappers o “superpoderes” dentro de un MCP de dominio, por ejemplo uno de Power BI.
