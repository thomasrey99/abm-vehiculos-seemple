"""
Tool: crear_vehiculo

Por que existe:
  La tool OpenAPI original (POST /vehicles, multipart/form-data con
  `files: array<binary>`) no permite que Orchestrate reciba ni reenvie
  correctamente el archivo de imagen -- un multipart generico con
  `format: binary` no tiene forma de pedirle el archivo al usuario ni de
  mapear el adjunto real del chat a ese campo. La via soportada por
  Orchestrate para esto es un parametro tipado WXOFile en una Python tool.

  Ademas, esta tool llama al backend directamente con requests, apuntando
  al path exacto sin barra final y siempre por HTTPS, evitando la cadena de
  redirects (307 -> 302 http) que degradaba el POST a GET y perdia el body
  completo (incluida la imagen).

Conexion necesaria:

  Ya existe (la crea automaticamente el import de la tool OpenAPI original):
  app_id="vehicle_management_api_20260804084441828", tipo api_key_auth.
  La reutilizamos aca, no hace falta crear una conexion nueva.

Import de la tool (CLI del ADK):

  orchestrate tools import -k python \
      -f crear_vehiculo_wxo_tool.py \
      -r requirements_crear_vehiculo.txt \
      -a vehicle_management_api_20260804084441828
"""

from typing import List, Optional

from ibm_watsonx_orchestrate.agent_builder.connections import ConnectionType
from ibm_watsonx_orchestrate.agent_builder.tools import tool, WXOFile
from ibm_watsonx_orchestrate.run import connections

BACKEND_URL = "https://abm-backend-74934092886.southamerica-east1.run.app/vehicles"
APP_ID = "vehicle_management_api_20260804084441828"

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


@tool(
    name="crear_vehiculo",
    description=(
        "Registra un vehiculo nuevo junto con sus imagenes. Requiere patente, "
        "marca, modelo, y al menos una imagen con su sector (label) ya "
        "identificado por el agente a partir de la foto (FRENTE, ATRAS, "
        "LATERAL_IZQUIERDA, LATERAL_DERECHA, FRENTE_IZQUIERDA, FRENTE_DERECHA, "
        "ATRAS_IZQUIERDA, ATRAS_DERECHA u OTRO). No inventes danios: si no se "
        "informan, el backend los detecta automaticamente."
    ),
    expected_credentials=[
        {"app_id": APP_ID, "type": ConnectionType.API_KEY_AUTH},
    ],
)
def crear_vehiculo(
    license_plate: str,
    brand: str,
    model: str,
    images: List[WXOFile],
    labels: List[str],
    color: Optional[str] = None,
    year: Optional[int] = None,
    insurance_policy: Optional[str] = None,
    observations: Optional[str] = None,
) -> dict:
    """Crea un vehiculo con sus imagenes, llamando directo al backend.

    Args:
        license_plate: Patente del vehiculo.
        brand: Marca.
        model: Modelo.
        images: Lista de archivos de imagen (adjuntos reales del usuario).
        labels: Lista de sectores, en el mismo orden que `images`. Cada valor
            debe ser uno de: FRENTE, ATRAS, LATERAL_IZQUIERDA,
            LATERAL_DERECHA, FRENTE_IZQUIERDA, FRENTE_DERECHA,
            ATRAS_IZQUIERDA, ATRAS_DERECHA, OTRO.
        color: Color del vehiculo (opcional).
        year: Anio del vehiculo (opcional).
        insurance_policy: Numero de poliza (opcional).
        observations: Observaciones (opcional).

    Returns:
        dict: la respuesta cruda del backend (success, message, data, error),
        o un dict con "success": False y "error" si algo fallo antes de
        llegar al backend (por ejemplo, labels invalidos o desalineados).
    """
    if not images:
        return {"success": False, "error": "No se recibio ninguna imagen.", "data": None}

    if len(images) != len(labels):
        return {
            "success": False,
            "error": (
                f"Se recibieron {len(images)} imagenes pero {len(labels)} labels. "
                "Deben venir en pares, una label por imagen."
            ),
            "data": None,
        }

    labels_normalizados = [l.strip().upper() for l in labels]
    invalidos = [l for l in labels_normalizados if l not in LABELS_VALIDOS]
    if invalidos:
        return {
            "success": False,
            "error": f"Labels invalidos: {invalidos}. Deben ser uno de {sorted(LABELS_VALIDOS)}.",
            "data": None,
        }

    creds = connections.api_key(APP_ID)
    # El SDK puede devolver un objeto con atributo .api_key o un dict segun
    # la version; contemplamos ambos casos.
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
            {"filename": WXOFile.get_file_name(img), "label": lbl, "details": []}
            for img, lbl in zip(images, labels_normalizados)
        ],
    }

    files_payload = []
    for img in images:
        nombre = WXOFile.get_file_name(img)
        tipo = WXOFile.get_file_type(img) or "application/octet-stream"
        contenido = WXOFile.get_content(img)
        files_payload.append(("files", (nombre, contenido, tipo)))

    import json
    import requests

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
                f"El backend redirigio la solicitud (status {response.status_code}) "
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