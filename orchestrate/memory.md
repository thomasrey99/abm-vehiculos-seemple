# Memoria del proyecto: Agente de seguros — gestión de vehículos (watsonx Orchestrate)

Ver contexto completo y detallado en `CONTEXTO_proyecto_agente_seguros.md` y `README_agentes.md`. Este archivo es el resumen para memoria persistente del proyecto.

## Qué es
Sistema de 4 agentes en IBM watsonx Orchestrate (supervisor + 3 colaboradores) para una compañía de seguros: registrar vehículos con fotos, buscarlos, modificarlos y eliminarlos. Backend propio FastAPI en Cloud Run (`https://abm-backend-74934092886.southamerica-east1.run.app`). Canal principal: WhatsApp vía Twilio. Repo local: `~/OneDrive/Desktop/ABM_vehiculos_Seemple-/orchestrate`, agentes como YAML en `agents/`, gestionados con el ADK CLI (`orchestrate agents import -f ...`, `orchestrate tools import ...`).

## Agentes
- Supervisor `AI_agente_seguros_75019u` ("AI agente- seguros"): deriva, no ejecuta (excepto lo de abajo).
- `Agente_de_alta_y_baja_de_vehiculos_4094Z8` ("Alta_y_baja_vehiculos"): alta con fotos + baja completa.
- `Agente_de_busqueda_de_vehiculos_0042aB` ("Buscador_vehiculos"): búsquedas y envío de imágenes.
- `Agente_de_modificacion_de_vehiculos_6513Mh` ("Modificacion_vehiculos"): edición de datos/imágenes puntuales.

Conexiones: `vehicle_management_api_20260804084441828` (api_key_auth, backend), `twilio_whatsapp_api` (key_value: account_sid/auth_token).

## Bugs resueltos
1. **Loop de derivación del supervisor**: instrucciones ambiguas hacían que juntara datos él mismo en vez de derivar. Fix: regla explícita de "derivar de inmediato al identificar intención".
2. **Redirect que perdía el POST**: `POST /vehicles/` → 307 → `POST http://.../vehicles` (degradado a http, bug de `X-Forwarded-Proto` detrás de Cloud Run) → 302 → el cliente convierte a GET → se pierde el body/imagen → el agente alucinaba éxito. Pendiente arreglar en el backend (agregar `ProxyHeadersMiddleware`). Mitigado en la tool nueva de `crear_vehiculo` con `allow_redirects=False` y URL exacta sin barra.
3. Se descartó (tras confirmar el bug #2) la hipótesis de que había que mover `crear_vehiculo` al supervisor — se revirtió, quedó en `Alta_y_baja_vehiculos`.
4. Reset completo del proyecto (se borraron y recrearon agentes/tools/conexiones) para partir limpio. Los tool names pasaron de slugs feos (import por UI) a nombres limpios por `operationId` (import por CLI) — hay que mantener los YAML de agentes sincronizados con esos nombres.
5. Bug de ADK: `orchestrate tools import -k openapi ... --app-id <existente>` crashea (no combinar esos flags).
6. Las tools importadas por CLI no quedan con la conexión vinculada a nivel de cada agente — hay que ir a la UI, Herramientas → tool → Conectores → Añadir conexión existente, una vez por tool por agente.

## Issue abierto (en investigación activa)
`crear_vehiculo` recibía imágenes con parámetro `WXOFile` (según guía de IBM) pero **la imagen nunca llegaba** al probarlo real por WhatsApp — el agente respondía con un mensaje genérico pidiendo "archivo adjunto, no enlace", igual que en TODAS las arquitecturas anteriores probadas. Hipótesis actual: WhatsApp le pasa a Orchestrate un link/URL de la imagen, no el binario, por lo que WXOFile nunca se completa.

**Se armó una tool de diagnóstico** (`recibir_imagen_test`, v2, recibe `imagen_url: str` y la descarga server-side con `requests`, con fallback a Basic Auth de Twilio) para confirmar esta hipótesis. Import y prueba por WhatsApp ("test imagen" + foto) **quedaron pendientes de ejecutar** — ver sección 6 de `CONTEXTO_proyecto_agente_seguros.md` para los próximos pasos exactos según el resultado.