from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProgramBase(BaseModel):
    department_id: Optional[int] = None
    program_name: Optional[str] = None
    degree: Optional[str] = None
    duration: Optional[int] = None


class ProgramCreate(ProgramBase):
    department_id: int
    program_name: str
    degree: str
    duration: int


class ProgramUpdate(ProgramBase):
    pass


class ProgramResponse(ProgramBase):
    id: int

    model_config = ConfigDict(from_attributes=True)