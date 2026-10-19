from typing import Optional
from pydantic import BaseModel, ConfigDict


class DepartmentBase(BaseModel):
    department_code: str
    name: str


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    department_code: Optional[str] = None
    name: Optional[str] = None


class DepartmentResponse(DepartmentBase):
    id: int

    model_config = ConfigDict(from_attributes=True)