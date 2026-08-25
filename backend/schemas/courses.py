from typing import Optional
from pydantic import BaseModel, ConfigDict

# Course
class CourseBase(BaseModel):
    course_code: Optional[str] = None
    course_name: Optional[str] = None
    department_id: Optional[int] = None
    course_type: Optional[str] = None
    credits: Optional[int] = None
    lecture_hours: Optional[int] = None
    tutorial_hours: Optional[int] = None
    practical_hours: Optional[int] = None
    requires_lab: Optional[bool] = False

class CourseCreate(CourseBase):
    course_code: str
    course_name: str
    department_id: int
    course_type: str

class CourseUpdate(CourseBase):
    pass

class CourseResponse(CourseBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# CourseAssignment
class CourseAssignmentBase(BaseModel):
    course_id: Optional[int] = None
    faculty_id: Optional[int] = None
    section_id: Optional[int] = None
    batch_id: Optional[int] = None

class CourseAssignmentCreate(CourseAssignmentBase):
    course_id: int
    faculty_id: int
    section_id: Optional[int] = None
    batch_id: Optional[int] = None

class CourseAssignmentUpdate(CourseAssignmentBase):
    pass

class CourseAssignmentResponse(CourseAssignmentBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ElectiveGroup
class ElectiveGroupBase(BaseModel):
    name: Optional[str] = None
    semester_id: Optional[int] = None
    department_id: Optional[int] = None

class ElectiveGroupCreate(ElectiveGroupBase):
    name: str
    semester_id: int
    department_id: int

class ElectiveGroupUpdate(ElectiveGroupBase):
    pass

class ElectiveGroupResponse(ElectiveGroupBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

# ElectiveGroupCourse
class ElectiveGroupCourseBase(BaseModel):
    group_id: Optional[int] = None
    course_id: Optional[int] = None

class ElectiveGroupCourseCreate(ElectiveGroupCourseBase):
    group_id: int
    course_id: int

class ElectiveGroupCourseUpdate(ElectiveGroupCourseBase):
    pass

class ElectiveGroupCourseResponse(ElectiveGroupCourseBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
