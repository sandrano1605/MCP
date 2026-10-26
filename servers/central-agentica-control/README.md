# Central Agéntica — MCP Orquestador (V0.1.0)

Servidor MCP `stdio` y CLI de control para la instancia local Central Agéntica en AF9328.

**Objetivo:** administrar hasta seis agentes ChatGPT como un solo sistema, monitorear su progreso y finalización, y recuperar tareas con continuidad contextual sin duplicar ejecuciones.

## Capacidades comprobables

- **Observación 1–6:** salud, fase, iteración, `run_id`, DOM, presión de memoria/CPU.
- **Contexto de tarea:** objetivo y último `task-state` guardados en SQLite local (no sube conversaciones).
- **Sigue / Solo:** planificación contextual y restauración del mismo `run_id` únicamente desde checkpoint validado.
- **Alta de agentes:** transición de layout a seis paneles conservando los paneles existentes.
- **Relevo seguro:** cada mutación requiere `prepare` → aprobación explícita de un solo uso → comprobación de resultado.
- **Monitor continuo:** proceso lateral independiente que registra cambios significativos en los seis, sin enviar mensajes.
- **Cierre certificado:** estado `done`, pendientes vacíos, evidencias y registro de ejecución coherente; un panel verde no basta.
- **Mejora continua:** bitácora de incidentes y reglas para priorizar pruebas de regresión.

## Ubicación y requisitos

Python 3.10+, `mcp` SDK, Central Agéntica V5.7.5+ con API local en `127.0.0.1:8792`.
La aplicación puede estar abierta mientras corre este servidor. No importa ni edita `Cookies`, `Web Data`, credenciales o borradores.

Configurar `CENTRAL_AGENTICA_APP_ROOT` a la carpeta de la instancia instalada. Se usa exclusivamente para leer el `STATE_JS` confiable del runtime.
El directorio `%LOCALAPPDATA%\central_agentica_control` contiene bitácoras e intenciones, **solo locales**.

## Inicio con APPANOL Trabajo

Ejemplos en PowerShell desde esta carpeta:

```powershell
$env:CENTRAL_AGENTICA_APP_ROOT = 'C:\ruta\Central_Agentica_V575_RECOVERY_CANDIDATE'
python cli.py status
python cli.py monitor
python cli.py agent 3
python cli.py context 3
python cli.py prepare-layout 6
```

Para ejecutar un cambio preparado **solo con aprobación explícita**, usar:

```powershell
python cli.py approve '<approval_token>' APROBAR_CAMBIO_CONTROLADO
python cli.py status
```

El token vence en 120 segundos, se consume antes del POST, y un timeout jamás autoriza reintentar. Crear un nuevo plan tras reconciliar el resultado.

## MCP stdio

```powershell
python -m pip install -r requirements.txt
python server.py
```

Ejemplo de configuración: `mcp.config.example.json`. Registrar el servidor en un cliente MCP compatible. **No está instalado automáticamente como conector remoto de ChatGPT**: requiere configuración/autenticación de la integración y un túnel seguro si el cliente se ejecuta fuera del equipo. No publicar el puerto 8792.

## Seguridad y límites

- No tiene herramientas de shell arbitrario, JS arbitrario, Retry, borrado de sesión o despliegue PRD/SAP.
- No inicia automáticamente un agente con respuesta incierta, borrador externo o `run_id` discrepante.
- No promete que ChatGPT siga procesando cuando se cierra la aplicación local.
- `/api/layout` agrega paneles pero no garantiza tener un chat autenticado ni una tarea asignada a cada uno.
- Nuevas asignaciones de agentes 5/6 requieren conversación de proyecto y objetivo confirmados antes de iniciar.
- Las operaciones mutables se consideran **aceptadas** cuando responde la API, y solo **verificadas** tras nueva lectura.

Ver `OPERACIONES.md`, `ARQUITECTURA.md`, `CAMBIOS.md` y `ESTADO_PROYECTO.json`.
