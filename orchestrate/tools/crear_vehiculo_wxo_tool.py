"""
Tool: crear_vehiculo (v2 - por URL, no WXOFile)

Por que existe:
  La v1 de esta tool usaba un parametro WXOFile para recibir las imagenes,
  pero se confirmo (con documentacion de Twilio + trace real de Orchestrate)
  que WhatsApp/Twilio nunca entrega el binario de la imagen al webhook: solo
  entrega una URL (MediaUrl0) que hay que descargar aparte, con autenticacion
  Basic (Account SID / Auth Token). Orchestrate le pasa esa URL al modelo como
  un mensaje de texto plano. Por eso WXOFile nunca se completaba.

  Esta version recibe la URL de cada imagen como texto (image_urls: List[str])
  y las descarga del lado del servidor (igual que se valido con la tool de
  diagnostico recibir_imagen_test), antes de reenviarlas multipart al backend.

  Ademas, llama al backend directamente con requests, apuntando al path
  exacto sin barra final y siempre por HTTPS, con allow_redirects=False, para
  evitar la cadena de redirects (307 -> 302 http) que degradaba el POST a GET
  y perdia el body completo (incluida la imagen).

Conexiones necesarias (ya existen, no hace falta crear ninguna):
  - app_id="vehicle_management_api_20260804084441828" (api_key_auth): API key
    del backend, para el POST /vehicles.
  - app_id="twilio_whatsapp_api" (key_value_creds): Account SID / Auth Token
    de Twilio, para descargar las imagenes si la URL requiere autenticacion.

Import de la tool (CLI del ADK) -- ojo, ahora depende de DOS connections; el
flag -a solo acepta una, así que despues de importar hay que vincular la
segunda conexion manualmente desde la UI (pestaña Conectores de la tool):

  orchestrate tools import -k python \
      -f crear_vehiculo_wxo_tool.py \
      -r requirements_crear_vehiculo.txt \
      -a vehicle_management_api_20260804084441828

  (despues, en la UI: Herramientas -> crear_vehiculo -> Conectores ->
   Añadir conexión existente -> twilio_whatsapp_api)
"""

import json
from typing import List, Optional

import requests

from ibm_watsonx_orchestrate.agent_builder.connections import ConnectionType
from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.run import connections

BACKEND_URL = "https://abm-backend-74934092886.southamerica-east1.run.app/vehicles"
BACKEND_APP_ID = "vehicle_management_api_20260804084441828"
TWILIO_APP_ID = "twilio_whatsapp_api"

LABELS_VALIDOS = {
    "FRENTE",
    "ATRAS",
    "LATERAL_IZQUIERDA",
    "LATERAL_DERECHA",
    "FRENTE_IZQUIERDA",
    "FRENTE_DERECHA",
    "ATRAS_IZQUIERDA",
    "ATRAS_DERECHA",
    "OTRO",
}


def _descargar_imagen(url: str, account_sid: Optional[str], auth_token: Optional[str]):
    """Descarga una imagen desde su URL. Reintenta con Basic Auth de Twilio
    si la primera descarga (sin auth) falla con 401/403.

    Returns:
        tuple (ok: bool, contenido: bytes|None, content_type: str|None, error: str|None)
    """
    try:
        resp = requests.get(url, timeout=30)
    except Exception as e:
        return False, None, None, f"No se pudo descargar la imagen: {e}"

    if resp.status_code in (401, 403) and account_sid and auth_token:
        try:
            resp = requests.get(url, timeout=30, auth=(account_sid, auth_token))
        except Exception as e:
            return False, None, None, f"No se pudo descargar la imagen (con auth): {e}"

    if resp.status_code != 200:
        return False, None, None, f"La descarga de la imagen devolvió HTTP {resp.status_code}."

    return True, resp.content, resp.headers.get("Content-Type", "application/octet-stream"), None


@tool(
    name="crear_vehiculo",
    description=(
        "Registra un vehiculo nuevo junto con sus imagenes. Requiere patente, "
        "marca, modelo, y al menos una imagen (como URL) con su sector (label) "
        "ya asignado por el agente segun el orden en que pidio cada foto "
        "(FRENTE, ATRAS, LATERAL_IZQUIERDA, LATERAL_DERECHA, u OTRO para "
        "imagenes extra). El label NO se determina analizando la imagen. Las "
        "URLs pueden venir como enlaces de texto (por ejemplo de WhatsApp), no "
        "hace falta que sean archivos adjuntos. No informes danios: el "
        "backend los detecta automaticamente al recibir cada imagen."
    ),
    expected_credentials=[
        {"app_id": BACKEND_APP_ID, "type": ConnectionType.API_KEY_AUTH},
        {"app_id": TWILIO_APP_ID, "type": ConnectionType.KEY_VALUE},
    ],
)
def crear_vehiculo(
    license_plate: str,
    brand: str,
    model: str,
    image_urls: List[str],
    labels: List[str],
    color: Optional[str] = None,
    year: Optional[int] = None,
    insurance_policy: Optional[str] = None,
    observations: Optional[str] = None,
) -> dict:
    """Crea un vehiculo con sus imagenes, descargandolas por URL y llamando
    directo al backend.

    Args:
        license_plate: Patente del vehiculo.
        brand: Marca.
        model: Modelo.
        image_urls: Lista de URLs de las imagenes tal como llegaron en el
            mensaje del usuario (por ejemplo, el enlace de WhatsApp/Twilio).
        labels: Lista de sectores, en el mismo orden que `image_urls`. Cada
            valor debe ser uno de: FRENTE, ATRAS, LATERAL_IZQUIERDA,
            LATERAL_DERECHA, FRENTE_IZQUIERDA, FRENTE_DERECHA,
            ATRAS_IZQUIERDA, ATRAS_DERECHA, OTRO.
        color: Color del vehiculo (opcional).
        year: Anio del vehiculo (opcional).
        insurance_policy: Numero de poliza (opcional).
        observations: Observaciones (opcional).

    Returns:
        dict: la respuesta cruda del backend (success, message, data, error),
        o un dict con "success": False y "error" si algo fallo antes de
        llegar al backend (labels invalidos/desalineados, o falla al
        descargar alguna imagen).
    """
    if not image_urls:
        return {"success": False, "error": "No se recibió ninguna imagen.", "data": None}

    if len(image_urls) != len(labels):
        return {
            "success": False,
            "error": (
                f"Se recibieron {len(image_urls)} imágenes pero {len(labels)} labels. "
                "Deben venir en pares, una label por imagen."
            ),
            "data": None,
        }

    labels_normalizados = [l.strip().upper() for l in labels]
    invalidos = [l for l in labels_normalizados if l not in LABELS_VALIDOS]
    if invalidos:
        return {
            "success": False,
            "error": f"Labels inválidos: {invalidos}. Deben ser uno de {sorted(LABELS_VALIDOS)}.",
            "data": None,
        }

    twilio_creds = connections.key_value(TWILIO_APP_ID)
    account_sid = twilio_creds.get("account_sid") if twilio_creds else None
    auth_token = twilio_creds.get("auth_token") if twilio_creds else None

    # Descargamos todas las imagenes antes de tocar el backend.
    archivos = []
    for idx, (url, label) in enumerate(zip(image_urls, labels_normalizados)):
        ok, contenido, content_type, error = _descargar_imagen(url, account_sid, auth_token)
        if not ok:
            return {
                "success": False,
                "error": f"No se pudo obtener la imagen #{idx + 1} ({label}): {error}",
                "data": None,
            }
        ext = "jpg" if "jpeg" in (content_type or "") else (content_type or "").split("/")[-1] or "jpg"
        nombre = f"{label.lower()}_{idx + 1}.{ext}"
        archivos.append({"nombre": nombre, "label": label, "contenido": contenido, "content_type": content_type})

    creds = connections.api_key_auth(BACKEND_APP_ID)
    api_key = getattr(creds, "api_key", None) or (
        creds.get("api_key") if isinstance(creds, dict) else None
    )

    request_payload = {
        "license_plate": license_plate,
        "brand": brand,
        "model": model,
        "color": color,
        "year": year,
        "insurance_policy": insurance_policy,
        "observations": observations,
        "images": [
            {"filename": a["nombre"], "label": a["label"], "details": []}
            for a in archivos
        ],
    }

    files_payload = [
        ("files", (a["nombre"], a["contenido"], a["content_type"]))
        for a in archivos
    ]

    response = requests.post(
        BACKEND_URL,
        headers={"X-API-Key": api_key},
        data={"request": json.dumps(request_payload)},
        files=files_payload,
        timeout=60,
        allow_redirects=False,
    )

    if response.status_code in (301, 302, 303, 307, 308):
        return {
            "success": False,
            "error": (
                f"El backend redirigió la solicitud (status {response.status_code}) "
                f"a {response.headers.get('Location')}. Revisar la URL del backend "
                "o el manejo de HTTPS/redirects en el servidor."
            ),
            "data": None,
        }

    try:
        return response.json()
    except ValueError:
        return {
            "success": False,
            "error": f"Respuesta no-JSON del backend (status {response.status_code}): {response.text[:300]}",
            "data": None,
        }