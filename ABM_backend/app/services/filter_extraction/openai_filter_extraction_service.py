import json

from openai import AsyncOpenAI

from app.core.logging import logger
from app.core.settings import settings
from app.enums.image_detail import ImageDetailType
from app.enums.image_label import ImageLabel
from app.modules.vehicles.schemas.vehicle_filter_query import VehicleFilterQuery
from app.services.filter_extraction.filter_extraction_service import (
    FilterExtractionService,
)

# Sinónimos / lenguaje coloquial más comunes para cada tipo de daño, para
# que el modelo pueda mapear expresiones libres del usuario ("hundimiento",
# "golpe", "choque") al ENUM correcto sin que el usuario tenga que conocer
# el nombre técnico exacto (ImageDetailType) en ningún momento.
_DETAIL_TYPE_HINTS: dict[ImageDetailType, str] = {
    ImageDetailType.ABOLLADURA: "abolladura, hundimiento leve, marca sin impacto violento",
    ImageDetailType.CHOQUE: "choque, impacto, colisión, accidente, golpe fuerte con daño de chapa hundida y desalineada",
    ImageDetailType.VIDRIO_ROTO: "vidrio roto, cristal roto, luna rota, parabrisas roto",
    ImageDetailType.RAYON: "rayón, rayado, raspón, marca de roce",
    ImageDetailType.GRIETA: "grieta, rajadura, fisura",
    ImageDetailType.ROTO: "roto, quebrado, partido, destrozado",
    ImageDetailType.OXIDO: "óxido, oxidación, herrumbre, corrosión",
    ImageDetailType.CALCOMANIA: "calcomanía, sticker, adhesivo, pegatina",
    ImageDetailType.PIEZA_FALTANTE: "pieza faltante, falta una pieza, pieza perdida",
    ImageDetailType.DANO_PINTURA: "daño de pintura, pintura dañada, descascarado",
    ImageDetailType.DEFORMACION: "deformación, deformado, torcido",
    ImageDetailType.OTRO_COLOR: "decoloración, cambio de color, pintura despareja",
    ImageDetailType.OTRO: "otro tipo de daño que NO encaje claramente en ninguna categoría anterior",
}

# Igual criterio para los sectores (label), con variantes coloquiales.
_LABEL_HINTS: dict[ImageLabel, str] = {
    ImageLabel.FRENTE: "frente, parte delantera, adelante",
    ImageLabel.ATRAS: "atrás, parte trasera, la parte de atrás, baúl",
    ImageLabel.LATERAL_IZQUIERDA: "lateral izquierdo, lado izquierdo, costado izquierdo",
    ImageLabel.LATERAL_DERECHA: "lateral derecho, lado derecho, costado derecho",
    ImageLabel.FRENTE_IZQUIERDA: "frente izquierdo, delantera izquierda",
    ImageLabel.FRENTE_DERECHA: "frente derecho, delantera derecha",
    ImageLabel.ATRAS_IZQUIERDA: "trasera izquierda, atrás a la izquierda",
    ImageLabel.ATRAS_DERECHA: "trasera derecha, atrás a la derecha",
    ImageLabel.OTRO: "otro sector no especificado",
}

# Guard de consistencia: si alguien agrega un ImageDetailType nuevo y se
# olvida de sumarle su entrada de sinónimos acá, el modelo de IA jamás
# va a poder mapear ese valor correctamente y todo va a caer en "OTRO"
# de forma silenciosa (como pasó con CHOQUE). Fallar rápido al arrancar
# la app es preferible a un bug de negocio silencioso en producción.
_missing_hints = set(ImageDetailType) - set(_DETAIL_TYPE_HINTS.keys())
if _missing_hints:
    raise RuntimeError(
        f"Faltan sinónimos en _DETAIL_TYPE_HINTS para: "
        f"{[d.value for d in _missing_hints]}. Actualizá "
        f"openai_filter_extraction_service.py antes de arrancar la app."
    )

_missing_label_hints = set(ImageLabel) - set(_LABEL_HINTS.keys())
if _missing_label_hints:
    raise RuntimeError(
        f"Faltan sinónimos en _LABEL_HINTS para: "
        f"{[l.value for l in _missing_label_hints]}. Actualizá "
        f"openai_filter_extraction_service.py antes de arrancar la app."
    )

def _build_system_prompt() -> str:
    detail_lines = "\n".join(
        f"- {enum_value.value}: {hint}"
        for enum_value, hint in _DETAIL_TYPE_HINTS.items()
    )
    label_lines = "\n".join(
        f"- {enum_value.value}: {hint}"
        for enum_value, hint in _LABEL_HINTS.items()
    )

    return (
        "Sos un asistente que traduce consultas en lenguaje natural sobre "
        "vehículos a un conjunto de FILTROS ESTRUCTURADOS de búsqueda.\n\n"
        "Extraé ÚNICAMENTE los campos que el usuario mencionó explícita o "
        "implícitamente. Si un campo no se menciona ni se puede inferir "
        "con confianza, dejalo en null. NUNCA inventes valores.\n\n"
        "Campos:\n"
        "- license_plate: patente, tal como la escribió el usuario.\n"
        "- brand: marca (ej. Toyota, Ford).\n"
        "- model: modelo (ej. Corolla, Focus).\n"
        "- color: color del vehículo.\n"
        "- year: año (entero).\n"
        "- insurance_policy: número/identificador de póliza, solo si se "
        "menciona explícitamente.\n"
        "- label: SECTOR del vehículo donde está el daño mencionado (si "
        "el texto menciona una ubicación puntual). Elegí el ENUM más "
        "cercano según esta guía:\n"
        f"{label_lines}\n\n"
        "- detail_type: TIPO PUNTUAL de daño mencionado. El usuario casi "
        "nunca va a usar el nombre técnico exacto del enum (va a decir "
        "'hundimiento', 'choque', 'golpe', etc. en vez de 'ABOLLADURA'). "
        "Elegí SIEMPRE el ENUM MÁS ESPECÍFICO posible según esta guía de "
        "sinónimos, aunque la palabra exacta del usuario no aparezca "
        "literalmente en la lista. Usá 'OTRO' ÚNICAMENTE como último "
        "recurso, cuando el daño mencionado genuinamente no encaje en "
        "ninguna categoría más específica — NUNCA lo uses solo porque "
        "la palabra exacta no está en la guía, primero evaluá cuál "
        "categoría describe mejor el daño. Dejalo en null si el usuario "
        "NO menciona ningún tipo puntual de daño (por ejemplo, si solo "
        "dice 'con daños', 'dañado', 'con algún daño', sin especificar "
        "cuál):\n"
        f"{detail_lines}\n\n"
        "- has_damage: true cuando el usuario pide vehículos con daños de "
        "forma GENÉRICA, sin especificar cuál (ej. 'con daños', "
        "'dañados', 'que tengan algún daño registrado'). Dejalo en null "
        "si no menciona daños en absoluto, o si ya especificó un tipo "
        "puntual (en ese caso `detail_type` alcanza y no hace falta "
        "setear `has_damage`).\n\n"
        "Ejemplos:\n"
        "- 'choque atrás' → label=ATRAS, detail_type=CHOQUE, "
        "has_damage=null (NO 'OTRO').\n"
        "- 'rayón en la puerta' → detail_type=RAYON, has_damage=null.\n"
        "- 'auto con un hundimiento en el lateral' → "
        "detail_type=ABOLLADURA, has_damage=null.\n"
        "- 'vehículos con daños registrados en la parte trasera' → "
        "label=ATRAS, detail_type=null, has_damage=true.\n"
        "- 'autos dañados' → detail_type=null, has_damage=true.\n\n"
        "Si el texto menciona un daño (puntual o genérico) pero no un "
        "sector, dejá `label` en null. Si menciona un sector pero ningún "
        "daño, dejá `detail_type` y `has_damage` en null."
    )


_FILTER_SCHEMA = {
    "name": "vehicle_filter_query",
    "schema": {
        "type": "object",
        "properties": {
            "license_plate": {"type": ["string", "null"]},
            "brand": {"type": ["string", "null"]},
            "model": {"type": ["string", "null"]},
            "color": {"type": ["string", "null"]},
            "year": {"type": ["integer", "null"]},
            "insurance_policy": {"type": ["string", "null"]},
            "label": {"type": ["string", "null"]},
            "detail_type": {"type": ["string", "null"]},
            "has_damage": {"type": ["boolean", "null"]},
        },
        "required": [
            "license_plate", "brand", "model", "color", "year",
            "insurance_policy", "label", "detail_type", "has_damage",
        ],
        "additionalProperties": False,
    },
}


class OpenAIFilterExtractionService(FilterExtractionService):

    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self._system_prompt = _build_system_prompt()

    async def extract_filters(self, text: str) -> VehicleFilterQuery:
        try:
            response = await self._client.chat.completions.create(
                model=settings.OPENAI_FILTER_MODEL,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": text},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": _FILTER_SCHEMA,
                },
                temperature=0,
            )

            parsed = json.loads(response.choices[0].message.content)

            # Validamos que label/detail_type devueltos por el modelo
            # correspondan realmente a un valor del enum. Si el modelo
            # devolviera algo fuera de la lista (no debería, dado el
            # prompt, pero no confiamos ciegamente), lo descartamos en
            # vez de romper la búsqueda.
            label = None
            if parsed.get("label"):
                try:
                    label = ImageLabel(parsed["label"])
                except ValueError:
                    logger.warning(
                        "El modelo devolvió un label inválido: %s",
                        parsed.get("label"),
                    )

            detail_type = None
            if parsed.get("detail_type"):
                try:
                    detail_type = ImageDetailType(parsed["detail_type"])
                except ValueError:
                    logger.warning(
                        "El modelo devolvió un detail_type inválido: %s",
                        parsed.get("detail_type"),
                    )

            return VehicleFilterQuery(
                license_plate=parsed.get("license_plate"),
                brand=parsed.get("brand"),
                model=parsed.get("model"),
                color=parsed.get("color"),
                year=parsed.get("year"),
                insurance_policy=parsed.get("insurance_policy"),
                label=label,
                detail_type=detail_type,
                has_damage=parsed.get("has_damage"),
            )

        except Exception:
            logger.exception(
                "Falló la extracción de filtros vía OpenAI para el texto "
                "'%s'. Se continúa sin filtros (equivale a listar todos "
                "los vehículos).",
                text,
            )
            return VehicleFilterQuery()