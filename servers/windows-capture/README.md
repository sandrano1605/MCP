# Windows Capture MCP

Servidor MCP para Windows orientado a captura determinística de ventanas desktop, con foco en Power BI Desktop.

## Tools

- `windows_list_windows`
- `windows_activate_window`
- `windows_capture_window`
- `windows_capture_region`
- `windows_get_foreground_window`
- `powerbi_list_desktop_windows`
- `powerbi_activate_report_window`
- `powerbi_capture_report_window`

## Diseño

- Lista y resuelve ventanas por `hwnd`, `title_contains` o `process_name`.
- Captura de ventana:
  1. intenta `PrintWindow`
  2. si falla o devuelve imagen vacía, cae a captura por región de pantalla
- Soporta `client_only=true` para trabajar con el área útil de apps como Power BI.

## Dependencias

Este servidor usa:

- `mcp` (SDK Python)
- `pywin32`
- PowerShell + `System.Drawing` para persistir PNG

Instalación sugerida:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

## Prueba rápida

```powershell
.\.venv\Scripts\python.exe .\server.py --self-test --title "analisis_disponibilidad"
```

## Registro MCP

Entrada sugerida en `.mcp.json`:

```json
{
  "mcpServers": {
    "windows-capture": {
      "type": "stdio",
      "command": "C:\\ruta\\al\\repo\\MCP\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\ruta\\al\\repo\\MCP\\servers\\windows-capture\\server.py"
      ]
    }
  }
}
```

## Workflow recomendado para Power BI

1. `powerbi_list_desktop_windows`
2. `powerbi_activate_report_window`
3. `powerbi_capture_report_window`

Wrappers Power BI:

- `powerbi_list_desktop_windows`: filtra por `PBIDesktop.exe`
- `powerbi_activate_report_window`: activa una ventana de reporte por titulo parcial
- `powerbi_capture_report_window`: captura el reporte de Power BI sin tener que pasar el nombre del proceso manualmente

## Nota importante

`SetForegroundWindow` puede fallar por reglas de foco de Windows.

Eso no debe romper la captura.

La activación se trata como `best-effort`; si Windows rechaza el foco, el servidor sigue intentando capturar la ventana.

Usar esto junto con:

- `powerbi-modeling` para modelo
- `pbip_visual_mcp` para estructura PBIP
