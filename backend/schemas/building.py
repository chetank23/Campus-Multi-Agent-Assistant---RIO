from typing import Optional
from pydantic import BaseModel, ConfigDict, computed_field

class BuildingBase(BaseModel):
    name: str
    code: Optional[str] = None
    location: Optional[str] = None
    number_of_floors: Optional[int] = None

class BuildingCreate(BuildingBase):
    pass

class BuildingUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    location: Optional[str] = None
    number_of_floors: Optional[int] = None

class BuildingResponse(BuildingBase):
    id: int

    @computed_field
    def building_name(self) -> str:
        return self.name or ""

    @computed_field
    def floors(self) -> int:
        return self.number_of_floors or 0

    model_config = ConfigDict(from_attributes=True)
