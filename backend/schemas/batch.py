from typing import Optional
from pydantic import BaseModel, ConfigDict

class BatchBase(BaseModel):
    section_id: Optional[int] = None
    batch_name: Optional[str] = None
    student_count: Optional[int] = None

class BatchCreate(BatchBase):
    section_id: int
    batch_name: str
    student_count: int

class BatchUpdate(BatchBase):
    pass

class BatchResponse(BatchBase):
    id: int

    model_config = ConfigDict(from_attributes=True)