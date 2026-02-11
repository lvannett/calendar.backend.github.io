from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


# ============= Auth Schemas =============
class UserCreate(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    wake_time: str
    bedtime: str
    default_study_block_minutes: int
    
    class Config:
        from_attributes = True


class UserPreferencesUpdate(BaseModel):
    wake_time: Optional[str] = None
    bedtime: Optional[str] = None
    default_study_block_minutes: Optional[int] = None


# ============= Assignment Schemas =============
class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    category: Optional[str] = "General"
    due_date: datetime
    priority: Optional[int] = Field(default=1, ge=1, le=3)
    estimated_time_minutes: Optional[int] = None


class AssignmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[int] = Field(default=None, ge=1, le=3)
    estimated_time_minutes: Optional[int] = None


class AssignmentComplete(BaseModel):
    actual_time_minutes: Optional[int] = None


class AssignmentResponse(BaseModel):
    id: int
    title: str
    description: str
    category: str
    due_date: datetime
    priority: int
    estimated_time_minutes: Optional[int]
    actual_time_minutes: Optional[int]
    completed: bool
    completed_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============= Class Schedule Schemas =============
class ClassScheduleCreate(BaseModel):
    title: str
    day_of_week: int = Field(ge=0, le=6)  # 0=Monday, 6=Sunday
    start_time: str  # Format: "HH:MM"
    end_time: str
    recurring: Optional[bool] = True


class ClassScheduleResponse(BaseModel):
    id: int
    title: str
    day_of_week: int
    start_time: str
    end_time: str
    recurring: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============= Meeting Schemas =============
class MeetingCreate(BaseModel):
    title: str
    description: Optional[str] = ""
    start_time: datetime
    end_time: datetime
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None


class MeetingResponse(BaseModel):
    id: int
    title: str
    description: str
    attendee_name: Optional[str]
    attendee_email: Optional[str]
    start_time: datetime
    end_time: datetime
    created_by_owner: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# ============= Public Meeting Scheduler Schemas =============
class PublicMeetingRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    attendee_name: str
    attendee_email: Optional[str] = None
    start_time: datetime
    end_time: datetime


class AvailableSlot(BaseModel):
    start_time: datetime
    end_time: datetime


class AvailabilityResponse(BaseModel):
    username: str
    available_slots: List[AvailableSlot]


# ============= Study Block Schemas =============
class StudyBlockResponse(BaseModel):
    id: int
    assignment_id: int
    assignment_title: str
    assignment_category: str
    start_time: datetime
    end_time: datetime
    status: str
    
    class Config:
        from_attributes = True


# ============= Calendar View Schema =============
class CalendarEvent(BaseModel):
    id: int
    type: str  # "assignment", "class", "meeting", "study_block"
    title: str
    description: Optional[str] = ""
    start_time: datetime
    end_time: Optional[datetime] = None
    category: Optional[str] = None
    completed: Optional[bool] = None


class CalendarResponse(BaseModel):
    events: List[CalendarEvent]
