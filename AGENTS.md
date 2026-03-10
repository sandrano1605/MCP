# AGENTS.md

## Propósito del repo

Este repo contiene MCPs utilitarios separados del repo operativo principal.

La regla base es:

- primero dejar el servidor funcionando y probado en este repo,
- después integrarlo en otros stacks,
- no mezclar prueba inicial con incrustación productiva.

## Estado actual

Servidor disponible:

- `windows-capture`

Ruta:

- `servers/windows-capture/server.py`

## Criterio técnico

Para apps desktop en Windows, no confiar en screenshots globales del escritorio si el objetivo es revisar una ventana específica.

Usar captura determinística por:

- `hwnd`
- título
- proceso

## Prioridades de desarrollo

1. fiabilidad de captura
2. errores accionables
3. integración simple por `stdio`
4. documentación breve y operativa
5. wrappers de dominio después de estabilizar la base

## Regla de integración futura

Cuando un MCP de este repo se quiera incrustar en otro stack:

1. no copiar a ciegas;
2. primero documentar el workflow;
3. después agregar wrappers de dominio;
4. mantener el servidor base independiente aquí.

## `windows-capture`

### Qué hace

- enumera ventanas,
- activa ventanas,
- captura ventanas o regiones,
- soporta Power BI Desktop con wrappers dedicados.

### Qué no hace todavía

- clics,
- teclado,
- navegación UI avanzada,
- OCR,
- lectura de controles internos.

### Límite importante

`SetForegroundWindow` puede fallar por reglas de foco de Windows.

Eso no debe romper la captura.

La activación debe tratarse como `best-effort`.

## Workflow Power BI recomendado

1. `powerbi_list_desktop_windows`
2. `powerbi_activate_report_window`
3. `powerbi_capture_report_window`
4. revisar PNG
5. recién después concluir sobre layout o legibilidad

## Mantenimiento

Si se toca `server.py`, siempre volver a correr:

```powershell
python .\servers\windows-capture\server.py --self-test --title "analisis_disponibilidad"
```

Y validar:

- que devuelve ventana correcta,
- que genera PNG válido,
- que no se cae si falla la activación.
