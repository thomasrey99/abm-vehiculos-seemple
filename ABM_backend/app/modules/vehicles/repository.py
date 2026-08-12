from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.image_detail import ImageDetail
from app.models.vehicle import Vehicle
from app.models.vehicle_image import VehicleImage

from sqlalchemy import select, and_

from app.modules.vehicles.schemas.vehicle_filter_query import VehicleFilterQuery

class VehicleRepository:

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db

    async def create(
        self,
        vehicle: Vehicle,
    ) -> Vehicle:

        self.db.add(vehicle)

        await self.db.flush()

        await self.db.refresh(vehicle)

        return vehicle

    async def update(
        self,
        vehicle: Vehicle,
    ) -> Vehicle:

        await self.db.flush()

        await self.db.refresh(vehicle)

        return vehicle

    async def get_by_id(
        self,
        vehicle_id: UUID,
    ) -> Vehicle | None:

        stmt = (
            select(Vehicle)
            .where(Vehicle.id == vehicle_id)
            .options(
                selectinload(Vehicle.images).selectinload(
                    VehicleImage.details
                ),
            )
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_by_license_plate(
        self,
        license_plate: str,
    ) -> Vehicle | None:

        stmt = (
            select(Vehicle)
            .where(
                Vehicle.license_plate == license_plate
            )
            .options(
                selectinload(Vehicle.images).selectinload(
                    VehicleImage.details
                ),
            )
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def get_all(
        self,
    ) -> list[Vehicle]:

        stmt = (
            select(Vehicle)
            .options(
                selectinload(Vehicle.images).selectinload(
                    VehicleImage.details
                ),
            )
            .order_by(Vehicle.created_at.desc())
        )

        result = await self.db.execute(stmt)

        return list(result.scalars().all())

    async def get_image_by_id(
        self,
        image_id: UUID,
    ) -> VehicleImage | None:

        stmt = (
            select(VehicleImage)
            .where(VehicleImage.id == image_id)
            .options(selectinload(VehicleImage.details))
        )

        result = await self.db.execute(stmt)

        return result.scalar_one_or_none()

    async def delete(
        self,
        vehicle: Vehicle,
    ) -> None:

        await self.db.delete(vehicle)

    async def delete_image(
        self,
        image: VehicleImage,
    ) -> None:

        await self.db.delete(image)
        
    async def search_by_filters(
        self,
        filters: VehicleFilterQuery,
    ) -> list[Vehicle]:
        """
        Busca vehículos combinando (con AND) los filtros presentes en
        `filters`. Los campos de texto (`brand`, `model`, `color`,
        `license_plate`, `insurance_policy`) usan coincidencia parcial
        insensible a mayúsculas (ILIKE). `label` y `detail_type` no son
        columnas del vehículo: se resuelven con un EXISTS correlacionado
        contra `vehicle_images` (y `image_details` cuando corresponde),
        de forma que "choque atrás" exija que exista UNA MISMA imagen
        cuyo label sea "atrás" Y que tenga ese daño puntual — no que el
        vehículo tenga, por separado, alguna imagen "atrás" y algún otro
        daño "choque" en cualquier otra foto.
        """

        stmt = (
            select(Vehicle)
            .options(
                selectinload(Vehicle.images).selectinload(
                    VehicleImage.details
                ),
            )
        )

        conditions = []

        if filters.license_plate:
            conditions.append(
                Vehicle.license_plate.ilike(f"%{filters.license_plate.strip()}%")
            )

        if filters.brand:
            conditions.append(Vehicle.brand.ilike(f"%{filters.brand.strip()}%"))

        if filters.model:
            conditions.append(Vehicle.model.ilike(f"%{filters.model.strip()}%"))

        if filters.color:
            conditions.append(Vehicle.color.ilike(f"%{filters.color.strip()}%"))

        if filters.year is not None:
            conditions.append(Vehicle.year == filters.year)

        if filters.insurance_policy:
            conditions.append(
                Vehicle.insurance_policy.ilike(
                    f"%{filters.insurance_policy.strip()}%"
                )
            )

        if filters.label or filters.detail_type or filters.has_damage:
            image_stmt = select(VehicleImage.id).where(
                VehicleImage.vehicle_id == Vehicle.id
            )

            if filters.label:
                image_stmt = image_stmt.where(
                    VehicleImage.label == filters.label
                )

            if filters.detail_type:
                image_stmt = image_stmt.join(
                    ImageDetail, ImageDetail.image_id == VehicleImage.id
                ).where(ImageDetail.detail_type == filters.detail_type)
            elif filters.has_damage:
                # No se pidió un tipo puntual de daño, pero sí que exista
                # ALGUNO registrado (ej. "daños en la parte trasera"). Sin
                # este join, una imagen sin ningún ImageDetail igual
                # matchearía por el solo hecho de tener el label correcto.
                image_stmt = image_stmt.join(
                    ImageDetail, ImageDetail.image_id == VehicleImage.id
                )

            conditions.append(image_stmt.exists())

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(Vehicle.created_at.desc())

        result = await self.db.execute(stmt)

        return list(result.unique().scalars().all())