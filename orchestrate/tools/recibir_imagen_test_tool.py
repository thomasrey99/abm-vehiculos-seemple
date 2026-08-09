"""
Tool de prueba: recibir_imagen_test (v2 - por URL, no WXOFile)

Objetivo:
  La v1 (con WXOFile) nunca recibio la imagen -- el modelo respondia que
  le habia llegado como "enlace", no como adjunto. Esto sugiere que
  WhatsApp le pasa a Orchestrate una URL de la imagen (probablemente
  alojada en Twilio), no el binario embebido. Esta version prueba esa
  hipotesis: recibe la URL como string y la descarga del lado del server.

Import de la tool (CLI del ADK), desde la carpeta orchestrate/ del proyecto:

  orchestrate tools import -k python \
      -f tools/recibir_imagen_test_tool.py \
      -r tools/requirements.txt \
      -a twilio_whatsapp_api

(Reusa la conexion de Twilio por si la URL de la imagen requiere
autenticacion Basic con el Account SID / Auth Token para descargarse.)
"""

from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.connections import ConnectionType
from ibm_watsonx_orchestrate.agent_builder.tools import tool
from ibm_watsonx_orchestrate.run import connections

TWILIO_APP_ID = "twilio_whatsapp_api"


@tool(
    name="recibir_imagen_test",
    description=(
        "Tool de prueba: recibe la URL de una imagen que el usuario compartio "
        "(el enlace tal cual aparece en el mensaje, no hace falta que sea un "
        "archivo adjunto) y la descarga para confirmar que es accesible. "
        "Usar solo para verificar que las imagenes llegan correctamente."
    ),
    expected_credentials=[
        {"app_id": TWILIO_APP_ID, "type": ConnectionType.KEY_VALUE},
    ],
)
def recibir_imagen_test(imagen_url: str) -> dict:
    """Descarga una imagen a partir de su URL para confirmar que llega bien.

    Args:
        imagen_url (str): URL de la imagen tal como la recibio el agente
            (puede venir del mensaje de WhatsApp como un link).

    Returns:
        dict: {"ok": bool, "status_code": int|None, "content_type": str|None,
               "tamaño": int|None, "error": str|None}
    """
    import requests

    creds = connections.key_value(TWILIO_APP_ID)
    account_sid = creds.get("account_sid")
    auth_token = creds.get("auth_token")

    # Primero probamos sin autenticacion.
    try:
        resp = requests.get(imagen_url, timeout=30)
    except Exception as e:
        return {"ok": False, "status_code": None, "content_type": None, "tamaño": None, "error": str(e)}

    # Si Twilio la protege, reintentamos con Basic Auth (Account SID / Auth Token).
    if resp.status_code in (401, 403) and account_sid and auth_token:
        try:
            resp = requests.get(imagen_url, timeout=30, auth=(account_sid, auth_token))
        except Exception as e:
            return {"ok": False, "status_code": None, "content_type": None, "tamaño": None, "error": str(e)}

    if resp.status_code != 200:
        return {
            "ok": False,
            "status_code": resp.status_code,
            "content_type": resp.headers.get("Content-Type"),
            "tamaño": None,
            "error": f"HTTP {resp.status_code}",
        }

    return {
        "ok": True,
        "status_code": resp.status_code,
        "content_type": resp.headers.get("Content-Type"),
        "tamaño": len(resp.content),
        "error": None,
    }