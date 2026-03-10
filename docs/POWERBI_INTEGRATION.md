# Integración con Power BI

## Objetivo

Usar `windows-capture` como capacidad visual complementaria de Power BI Desktop.

## Stack recomendado

1. `powerbi-modeling`
   - modelo vivo
2. `pbip_visual_mcp`
   - estructura del `.pbip`
3. `windows-capture`
   - evidencia visual real de la ventana

## Workflow recomendado

1. abrir Power BI Desktop,
2. ubicar la ventana correcta,
3. capturar PNG real,
4. revisar diseño,
5. recién después editar layout o visuales.

## Tools Power BI

- `powerbi_list_desktop_windows`
- `powerbi_activate_report_window`
- `powerbi_capture_report_window`

## Regla

No concluir sobre layout sin evidencia visual válida de la ventana correcta.

## Fase siguiente

Si esta integración se consolida, los wrappers futuros a agregar son:

- `powerbi_capture_active_window`
- `powerbi_capture_canvas_region`
- `powerbi_capture_page_review`
