from typing import Optional
from pydantic import BaseModel, ConfigDict


class DepartmentBase(BaseModel):
    department_code: Optional[str] = None
    name: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    department_code: str
    name: str


class DepartmentUpdate(DepartmentBase):
    pass


class DepartmentResponse(DepartmentBase):
    id: int

    model_config = ConfigDict(from_attributes=True)