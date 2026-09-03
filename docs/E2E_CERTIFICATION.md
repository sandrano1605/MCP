# ARTEL MCP V1.7 — End-to-End Certification Pack

Objetivo: reemplazar micro-sprints de validación por un gate único, reproducible y read-only.

## 1. Offline self-test

Tool: `artel_self_test`

Crea un laboratorio temporal y comprueba en una sola ejecución:

- PBIP sintético con 2 páginas PBIR;
- layering esperado;
- oclusión intencional;
- visual fuera de bounds;
- tabOrder duplicado;
- TMDL con 2 tablas;
- 4 medidas DAX de prueba y hashes de expresión;
- relación bidireccional;
- RLS positivo;
- caso negativo sin RLS cuando `expect_rls=true`;
- planner siempre `DRY_RUN`, `apply=false`, `write_ready=0`;
- export Power Automate sintético con pasos LLM/gates/email;
- detección de secreto embebido sin revelar valor;
- guardas GET/POST/PATCH/PUT/DELETE.

No usa cloud y no escribe fuera del directorio temporal.

## 2. Certificación PBIP real

Tool: `artel_certify_local_bi`

Consolida en una sola salida:

- inventario PBIP activo;
- Canvas Inspector PBIR;
- Model Inspector TMDL;
- extracción/hash de todas las medidas;
- RLS y relaciones;
- planner read-only;
- scanner de secretos;
- Power Automate export opcional;
- estado explícito de runtime pendiente.

El resultado separa:

- `engine_status`: si el motor de auditoría funcionó;
- `project_status`: si el proyecto tiene hallazgos;
- `status`: PASS / REVIEW / FAIL.

Un proyecto con hallazgos puede devolver `engine_status=PASS` y `project_status=REVIEW`.

## 3. Power Automate

Tool: `artel_audit_power_automate_export`

Contrato por defecto:

1. Payload_LLM
2. LLM_Adapter
3. Parse_JSON_LLM
4. Semantic_Grounding_Gate
5. InsightFinal
6. HTML_Email_Final
7. Send_Email

La tool revisa presencia, `runAfter`, estructura, pasos faltantes e indicadores de secretos. No devuelve valores de credenciales.

Esto es auditoría estática. La ejecución real del flujo se certifica en un gate runtime separado.

## 4. Runtime final

Después de PASS del self-test y auditoría local, el gate runtime debe cubrir en una sola sesión:

- Power BI Desktop / semantic model cargado;
- consultas DAX conocidas con expected results;
- aislamiento por vendedor con dos identidades/sellers;
- flujo Power Automate test/pilot;
- fallback del LLM;
- grounding/gates;
- evidencia del correo final sin envío productivo;
- cero escrituras Fabric salvo autorización explícita.

## 5. Regla de evidencia

`runtime actual > API real > test determinístico > inspección estructural > revisión estática`.

Nunca declarar certificación runtime a partir de TMDL/PBIR solamente.
