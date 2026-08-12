# Agentes — Gestión de vehículos para seguros (watsonx Orchestrate)

Arquitectura: un agente supervisor que interpreta la intención del usuario y deriva a uno de tres agentes colaboradores especializados. El supervisor no ejecuta operaciones directamente.

Archivos fuente (infraestructura como código): `agents/supervisor.yaml`, `agents/alta_baja.yaml`, `agents/buscador.yaml`, `agents/modificacion.yaml`. Se aplican con `orchestrate agents import -f <archivo>`.

---

## 1. Supervisor — `AI agente- seguros`

**Nombre interno:** `AI_agente_seguros_75019u`

**Descripción:**
> Asistente de gestión de vehículos para una compañía de seguros. Interpreta la solicitud del usuario (registrar, buscar/consultar, actualizar, o eliminar vehículos e imágenes) y la deriva al agente colaborador especializado correspondiente: alta y baja de vehículos, búsqueda y consulta, o modificación de datos. No ejecuta operaciones directamente.

**Comportamiento (resumen):**
- Es el punto de entrada. No ejecuta operaciones: interpreta la intención y deriva de inmediato al colaborador correcto, sin juntar datos él mismo (patente, marca, imágenes, etc. los pide el colaborador).
- Deriva a `Alta_y_baja_vehiculos` para alta de vehículos nuevos, baja completa de un vehículo, o baja de una imagen puntual.
- Deriva a `Buscador_vehiculos` para listar, buscar (patente, id, filtros, similitud visual, texto libre) o ver/enviar imágenes.
- Deriva a `Modificacion_vehiculos` para actualizar datos existentes, corregir sector de una imagen, o reemplazar el archivo de una imagen.
- Si la intención es ambigua entre dos colaboradores, pregunta antes de derivar — es la única razón válida para no derivar de inmediato.
- Nunca expone nombres de tools, endpoints ni nombres internos de agentes al usuario. Resume resultados de forma breve y sin datos técnicos (ids, JSON).
- No inventa que una operación se completó: siempre espera la respuesta real del colaborador.

**Colaboradores:** `Alta_y_baja_vehiculos`, `Buscador_vehiculos`, `Modificacion_vehiculos`
**Tools propias:** ninguna.

---

## 2. Alta_y_baja_vehiculos

**Nombre interno:** `Agente_de_alta_y_baja_de_vehiculos_4094Z8`

**Descripción:**
> Agente especializado en registrar vehículos nuevos junto con sus imágenes (analiza cada foto para determinar el sector del vehículo fotografiado, y dispara detección automática de daños), y en eliminar vehículos completos de forma destructiva. Usar cuando el usuario quiera dar de alta un vehículo, cargar imágenes de un vehículo nuevo, o eliminar un vehículo completo. Antes de eliminar, siempre pide confirmación explícita mencionando el vehículo afectado. No realiza búsquedas, consultas de vehículos existentes, actualizaciones de datos, ni elimina imágenes puntuales (eso incluye reemplazar o borrar una sola imagen de un vehículo existente): eso lo maneja otro agente.

**Comportamiento (resumen):**
- **Alta:** antes de registrar, verifica patente, marca, modelo y al menos una imagen. Analiza cada imagen para determinar el sector (FRENTE, ATRAS, LATERAL_IZQUIERDA, LATERAL_DERECHA, FRENTE_IZQUIERDA, FRENTE_DERECHA, ATRAS_IZQUIERDA, ATRAS_DERECHA, OTRO); usa OTRO si no puede determinarlo, sin adivinar. No inventa daños — el backend los detecta automáticamente. Llama a `crear_vehiculo` pasando las imágenes y sus sectores (labels) como listas alineadas por posición. Devuelve un resumen breve (patente, marca/modelo, cantidad de imágenes y sector, daños si los hay, estados pendientes).
- **Baja de vehículo (destructiva):** pide confirmación explícita mencionando el vehículo afectado antes de ejecutar `eliminar_vehiculo`. No ejecuta ante solicitudes ambiguas o hipotéticas. No reintenta automáticamente si falla.
- No afirma que una operación se completó hasta recibir respuesta exitosa de la tool.

**Tools:** `crear_vehiculo` (Python, WXOFile/URL — en ajuste, ver estado abajo), `eliminar_vehiculo` (OpenAPI)

---

## 3. Buscador_vehiculos

**Nombre interno:** `Agente_de_busqueda_de_vehiculos_0042aB`

**Descripción:**
> Agente especializado en consultar y buscar vehículos: por patente, por id, por filtros exactos (marca, modelo, color, año, póliza, sector, tipo de daño), por similitud visual a partir de una foto, o por descripción en lenguaje natural. También muestra o envía las imágenes de un vehículo al usuario (como fotos nativas si el canal es WhatsApp, o como Markdown en otros canales). Usar para cualquier pedido de consulta, listado, búsqueda o visualización de imágenes. No registra, no elimina ni modifica datos de vehículos: eso lo maneja otro agente. Los resultados de similitud (por imagen o texto) nunca son una identificación definitiva.

**Comportamiento (resumen):**
- Usa `obtener_vehiculo_por_patente` para patente específica, `buscar_vehiculo_por_filtros` para criterios concretos, `buscar_vehiculo_por_texto_semantico` para descripciones aproximadas, `buscar_vehiculo_por_imagen` para búsqueda por foto de referencia, `listar_vehiculos` solo para listar todo sin criterio.
- Diferencia siempre coincidencia exacta (patente/id) de coincidencia por similitud (imagen/texto) — nunca presenta similitud como identificación definitiva.
- Para mostrar imágenes: llama primero a `obtener_vehiculo_por_id`, luego a `send_vehicle_images_whatsapp` con las URLs. Si `sent=true`, no repite las URLs ni usa Markdown. Si `sent=false` por `not_whatsapp_channel`, genera Markdown de imagen por canal no-WhatsApp. Nunca usa HTML, iframe, base64 ni data URLs.

**Tools:** `listar_vehiculos`, `obtener_vehiculo_por_id`, `obtener_vehiculo_por_patente`, `buscar_vehiculo_por_imagen`, `buscar_vehiculo_por_texto_semantico`, `buscar_vehiculo_por_filtros` (OpenAPI), `send_vehicle_images_whatsapp` (Python/Twilio)

---

## 4. Modificacion_vehiculos

**Nombre interno:** `Agente_de_modificacion_de_vehiculos_6513Mh`

**Descripción:**
> Agente especializado en modificar datos e imágenes de vehículos ya existentes: actualizar campos como patente, marca, modelo, color, año, póliza, observaciones o estado activo/inactivo; corregir el sector asignado a una imagen; reemplazar el archivo de una imagen (conservando su sector y daños ya registrados, sin volver a analizarlos); o eliminar una imagen puntual de forma destructiva, sin afectar al resto del vehículo. Usar cuando el usuario ya identificó un vehículo existente y quiere cambiar o borrar alguno de sus datos o imágenes. Pide confirmación explícita antes de eliminar una imagen, o si un cambio de patente puede generar confusión con otro vehículo. No registra vehículos nuevos ni elimina un vehículo completo: eso lo maneja otro agente.

**Comportamiento (resumen):**
- Identifica inequívocamente el vehículo (y la imagen, si corresponde) antes de modificar; si falta el id, lo pide antes de actuar. Modifica solo los campos pedidos, nunca reemplaza con valores vacíos o asumidos.
- `actualizar_vehiculo` para campos generales; pide confirmación si el cambio de patente puede confundirse con otro vehículo.
- `actualizar_sector_imagen` para corregir el sector — interpreta izquierda/derecha desde la perspectiva del vehículo/conductor, nunca del observador de la foto.
- `reemplazar_archivo_imagen` conserva sector y daños ya registrados; no vuelve a ejecutar detección automática.
- `eliminar_imagen` (destructiva): pide confirmación explícita mencionando vehículo + sector antes de ejecutar. No reintenta automáticamente si falla.

**Tools:** `actualizar_vehiculo`, `actualizar_sector_imagen`, `reemplazar_archivo_imagen`, `eliminar_imagen` (OpenAPI)

---

## Estado actual / issue abierto

Todos los agentes están reconstruidos y desplegados con la conexión `vehicle_management_api_20260804084441828` (backend) y `twilio_whatsapp_api` (envío nativo de imágenes por WhatsApp).

**Pendiente de resolver:** el flujo de alta con imagen por WhatsApp todavía no confirma que la imagen llegue utilizable al agente. Hipótesis en investigación: WhatsApp le pasa a Orchestrate un enlace (URL) de la imagen, no el binario embebido, por lo que un parámetro `WXOFile` nunca se completa. Se está probando una tool de diagnóstico (`recibir_imagen_test`, adjunta temporalmente a `Alta_y_baja_vehiculos`) que recibe esa URL como texto y la descarga del lado del servidor, para confirmar la hipótesis antes de rediseñar `crear_vehiculo` sobre esa base. Esta tool y la instrucción de prueba asociada son temporales y deben retirarse una vez confirmado el diagnóstico.