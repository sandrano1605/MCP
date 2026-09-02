# AGENTS.md

## Propósito

Este repositorio contiene servidores MCP utilitarios y reutilizables. Deben poder ser consumidos por distintos clientes MCP/LLM sin depender de conocimiento implícito de una conversación previa.

Regla base:

1. estabilizar y probar la capacidad en este repositorio;
2. exponer un contrato simple, documentado y estructurado;
3. recién después integrarla en stacks de dominio o producción.

## Principios obligatorios

- `read-first` por defecto;
- no guardar secretos ni tokens;
- no declarar `PASS` sin prueba correspondiente;
- preferir API/formatos oficiales sobre automatización UI;
- mantener tools pequeñas y composables;
- retornar resultados estructurados cuando sea posible;
- no exigir al LLM IDs, rutas o detalles que puedan descubrirse automáticamente;
- separar implementación determinística de interpretación generativa;
- minimizar contexto: manifest primero, contenido completo solo bajo demanda;
- nunca devolver Base64 de definiciones Fabric directamente al LLM si puede decodificarse y resumirse dentro del MCP.

## Servidores actuales

### `windows-capture`

Ruta:

- `servers/windows-capture/server.py`

Responsabilidad:

- enumerar ventanas;
- activar una ventana como best-effort;
- capturar ventanas o regiones;
- wrappers Power BI Desktop.

Para revisión Power BI Desktop:

1. `powerbi_list_desktop_windows`
2. `powerbi_activate_report_window`
3. `powerbi_capture_report_window`
4. revisar PNG
5. recién después concluir sobre layout o legibilidad.

La captura visual complementa, pero no sustituye, auditoría PBIP/TMDL/PBIR/DAX.

### `artel-powerplatform-mcp`

Ruta:

- `src/artel_powerplatform_mcp/`

Responsabilidad:

- inspección local de proyectos PBIP;
- inventario TMDL/PBIR/DAX;
- validaciones determinísticas;
- consultas Power BI read-only;
- Auth Broker seguro para Fabric/Power BI/Power Platform;
- discovery de Fabric;
- recuperación read-only de definiciones PBIR/TMDL con soporte LRO;
- acceso Power Platform protegido;
- scanner de secretos redactado;
- contratos estructurados para clientes MCP.

Al conectarse por primera vez, un cliente debe preferir:

1. `artel_list_capabilities`
2. `artel_health`
3. `artel_auth_status` cuando la tarea sea cloud;
4. la tool específica más pequeña para la tarea.

Para Fabric:

1. descubrir workspace/item antes de pedir IDs al usuario;
2. solicitar definición sin contenido primero;
3. inspeccionar `paths` y tamaños;
4. solicitar contenido solamente cuando una parte sea relevante;
5. no habilitar `updateDefinition` hasta que exista planner, dry-run, checkpoint, rollback y evidencia.

Nota: las APIs oficiales `getDefinition` de Report y Semantic Model exigen scopes de lectura-escritura aunque la operación ejecutada por este MCP sea de lectura. Ese requisito de OAuth no autoriza automáticamente escrituras en nuestras tools.

## Escrituras

`ARTEL_ALLOW_WRITES=false` es el estado seguro.

POST/PATCH/PUT solo pueden ejecutarse cuando coinciden:

- `dry_run=false`;
- `confirm=true`;
- `ARTEL_ALLOW_WRITES=true`.

`DELETE` permanece bloqueado hasta que exista una tool específica con checkpoint, rollback y pruebas.

Fabric V1.3 no expone `updateDefinition`.

## Git

Antes de modificar:

```powershell
git status --short
git branch --show-current
git log --oneline -10
```

No usar `git reset --hard`, `git clean`, `git add .` ni force push salvo autorización explícita y justificación.

## Pruebas

Si se toca el servidor ARTEL:

```powershell
python -m compileall -q src
python -m pytest
```

Si se toca `windows-capture`:

```powershell
python .\servers\windows-capture\server.py --self-test --title "analisis_disponibilidad"
```

No registrar una validación como aprobada si el comando no llegó a ejecutarse.

## Seguridad y repositorio público

No incorporar a un repositorio público lógica operacional, credenciales, destinatarios, identificadores o documentación interna que no deba exponerse. La configuración empresarial específica debe mantenerse en una capa privada cuando corresponda.
