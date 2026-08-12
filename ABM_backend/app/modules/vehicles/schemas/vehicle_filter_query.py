from pydantic import BaseModel, ConfigDict

from app.enums.image_detail import ImageDetailType
from app.enums.image_label import ImageLabel


class VehicleFilterQuery(BaseModel):
    """
    Filtros estructurados de búsqueda de vehículos, extraídos por IA a
    partir de una consulta en lenguaje natural. Todos los campos son
    opcionales: solo se aplican los que el modelo logró identificar en
    el texto; el resto queda en None y no restringe la búsqueda.
    """
    model_config = ConfigDict(extra="forbid")

    license_plate: str | None = None
    brand: str | None = None
    model: str | None = None
    color: str | None = None
    year: int | None = None
    insurance_policy: str | None = None
    label: ImageLabel | None = None
    detail_type: ImageDetailType | None = None
    has_damage: bool | None = None
    """
    True cuando el usuario pidió "vehículos con daños" (o similar) de
    forma GENÉRICA, sin especificar un tipo puntual (choque, rayón,
    etc.). Distinto de `detail_type`, que ya implica esta condición
    cuando está presente. Se usa para que, combinado con `label`, la
    búsqueda exija que exista una imagen de ese sector con AL MENOS UN
    daño registrado, en vez de devolver cualquier imagen de ese sector
    tenga o no daños.
    """