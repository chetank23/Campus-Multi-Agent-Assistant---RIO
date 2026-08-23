from typing import Optional
from pydantic import BaseModel, ConfigDict

class BuildingBase(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    location: Optional[str] = None
    number_of_floors: Optional[int] = None

class BuildingCreate(BuildingBase):
    name: str
    code: str

class BuildingUpdate(BuildingBase):
    pass

class BuildingResponse(BuildingBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
