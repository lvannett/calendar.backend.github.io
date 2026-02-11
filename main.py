from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
import logging

from database import get_db, engine
from models import Base, User, Assignment, ClassSchedule, Meeting, StudyBlock
from schemas import (
    UserCreate, UserLogin, Token, UserResponse, UserPreferencesUpdate,
    AssignmentCreate, AssignmentUpdate, AssignmentComplete, AssignmentResponse,
    ClassScheduleCreate, ClassScheduleResponse,
    MeetingCreate, MeetingResponse,
    PublicMeetingRequest, AvailabilityResponse, AvailableSlot,
    StudyBlockResponse, CalendarResponse, CalendarEvent
)
from auth import (
    get_password_hash, create_access_token, authenticate_user, get_current_user
)
from scheduler import Scheduler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="CMUCal API",
    description="Smart scheduling system for college duties and academics",
    version="1.0.1"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============= Authentication Endpoints =============

@app.post("/api/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """Register a new user"""
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        username=user_data.username,
        hashed_password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    logger.info(f"New user registered: {user_data.username}")
    return new_user


@app.post("/api/auth/login", response_model=Token)
def login(user_data: UserLogin, db: Session = Depends(get_db)):
    """Login and receive JWT token"""
    user = authenticate_user(db, user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    access_token = create_access_token(data={"sub": user.username})
    logger.info(f"User logged in: {user.username}")
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user


# ============= User Preferences Endpoints =============

@app.get("/api/preferences", response_model=UserResponse)
def get_preferences(current_user: User = Depends(get_current_user)):
    """Get user preferences"""
    return current_user


@app.put("/api/preferences", response_model=UserResponse)
def update_preferences(
    preferences: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user preferences"""
    if preferences.wake_time is not None:
        current_user.wake_time = preferences.wake_time
    if preferences.bedtime is not None:
        current_user.bedtime = preferences.bedtime
    if preferences.default_study_block_minutes is not None:
        current_user.default_study_block_minutes = preferences.default_study_block_minutes
    
    db.commit()
    db.refresh(current_user)
    
    logger.info(f"User preferences updated: {current_user.username}")
    return current_user


# ============= Assignment Endpoints =============

@app.get("/api/assignments", response_model=List[AssignmentResponse])
def get_assignments(
    completed: bool = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all assignments, optionally filtered by completion status"""
    query = db.query(Assignment).filter(Assignment.user_id == current_user.id)
    
    if completed is not None:
        query = query.filter(Assignment.completed == completed)
    
    assignments = query.order_by(Assignment.due_date).all()
    return assignments


@app.post("/api/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    assignment_data: AssignmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new assignment"""
    new_assignment = Assignment(
        user_id=current_user.id,
        **assignment_data.model_dump()
    )
    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)
    
    # Regenerate study schedule
    scheduler = Scheduler(current_user, db)
    scheduler.regenerate_schedule()
    
    logger.info(f"Assignment created: {new_assignment.title}")
    return new_assignment


@app.put("/api/assignments/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(
    assignment_id: int,
    assignment_data: AssignmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an assignment"""
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.user_id == current_user.id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    # Update fields
    update_data = assignment_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assignment, field, value)
    
    db.commit()
    db.refresh(assignment)
    
    # Regenerate study schedule
    scheduler = Scheduler(current_user, db)
    scheduler.regenerate_schedule()
    
    logger.info(f"Assignment updated: {assignment.title}")
    return assignment


@app.delete("/api/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an assignment"""
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.user_id == current_user.id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    db.delete(assignment)
    db.commit()
    
    # Regenerate study schedule
    scheduler = Scheduler(current_user, db)
    scheduler.regenerate_schedule()
    
    logger.info(f"Assignment deleted: {assignment.title}")
    return None


@app.post("/api/assignments/{assignment_id}/complete", response_model=AssignmentResponse)
def complete_assignment(
    assignment_id: int,
    completion_data: AssignmentComplete,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mark an assignment as complete"""
    assignment = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.user_id == current_user.id
    ).first()
    
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    
    assignment.completed = True
    assignment.completed_at = datetime.utcnow()
    if completion_data.actual_time_minutes:
        assignment.actual_time_minutes = completion_data.actual_time_minutes
    
    db.commit()
    db.refresh(assignment)
    
    # Regenerate study schedule
    scheduler = Scheduler(current_user, db)
    scheduler.regenerate_schedule()
    
    logger.info(f"Assignment completed: {assignment.title}")
    return assignment


# ============= Class Schedule Endpoints =============

@app.get("/api/classes", response_model=List[ClassScheduleResponse])
def get_classes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all class schedules"""
    classes = db.query(ClassSchedule).filter(
        ClassSchedule.user_id == current_user.id
    ).order_by(ClassSchedule.day_of_week, ClassSchedule.start_time).all()
    return classes


@app.post("/api/classes", response_model=ClassScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_class(
    class_data: ClassScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a new class to schedule"""
    new_class = ClassSchedule(
        user_id=current_user.id,
        **class_data.model_dump()
    )
    db.add(new_class)
    db.commit()
    db.refresh(new_class)
    
    # Regenerate study schedule
    scheduler = Scheduler(current_user, db)
    scheduler.regenerate_schedule()
    
    logger.info(f"Class added: {new_class.title}")
    return new_class


@app.delete("/api/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a class from schedule"""
    class_schedule = db.query(ClassSchedule).filter(
        ClassSchedule.id == class_id,
        ClassSchedule.user_id == current_user.id
    ).first()
    
    if not class_schedule:
        raise HTTPException(status_code=404, detail="Class not found")
    
    db.delete(class_schedule)
    db.commit()
    
    # Regenerate study schedule
    scheduler = Scheduler(current_user, db)
    scheduler.regenerate_schedule()
    
    logger.info(f"Class deleted: {class_schedule.title}")
    return None


# ============= Meeting Endpoints =============

@app.get("/api/meetings", response_model=List[MeetingResponse])
def get_meetings(
    start_date: datetime = None,
    end_date: datetime = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all meetings, optionally filtered by date range"""
    query = db.query(Meeting).filter(Meeting.user_id == current_user.id)
    
    if start_date:
        query = query.filter(Meeting.start_time >= start_date)
    if end_date:
        query = query.filter(Meeting.start_time <= end_date)
    
    meetings = query.order_by(Meeting.start_time).all()
    return meetings


@app.post("/api/meetings", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def create_meeting(
    meeting_data: MeetingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new meeting"""
    new_meeting = Meeting(
        user_id=current_user.id,
        created_by_owner=True,
        **meeting_data.model_dump()
    )
    db.add(new_meeting)
    db.commit()
    db.refresh(new_meeting)
    
    # Regenerate study schedule
    scheduler = Scheduler(current_user, db)
    scheduler.regenerate_schedule()
    
    logger.info(f"Meeting created: {new_meeting.title}")
    return new_meeting


@app.delete("/api/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(
    meeting_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a meeting"""
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id,
        Meeting.user_id == current_user.id
    ).first()
    
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    db.delete(meeting)
    db.commit()
    
    # Regenerate study schedule
    scheduler = Scheduler(current_user, db)
    scheduler.regenerate_schedule()
    
    logger.info(f"Meeting deleted: {meeting.title}")
    return None


# ============= Public Meeting Scheduler Endpoints =============

@app.get("/api/public/availability/{username}", response_model=AvailabilityResponse)
def get_public_availability(
    username: str,
    days_ahead: int = 7,
    db: Session = Depends(get_db)
):
    """Get available time slots for a user (public endpoint)"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    scheduler = Scheduler(user, db)
    start_date = datetime.now()
    end_date = start_date + timedelta(days=days_ahead)
    
    available_slots = scheduler.get_available_slots(start_date, end_date)
    
    # Filter out slots shorter than 30 minutes
    filtered_slots = [
        AvailableSlot(start_time=start, end_time=end)
        for start, end in available_slots
        if (end - start).total_seconds() / 60 >= 30
    ]
    
    return AvailabilityResponse(
        username=username,
        available_slots=filtered_slots
    )


@app.post("/api/public/schedule/{username}", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
def schedule_public_meeting(
    username: str,
    meeting_data: PublicMeetingRequest,
    db: Session = Depends(get_db)
):
    """Schedule a meeting with a user (public endpoint)"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate that the requested time is actually available
    scheduler = Scheduler(user, db)
    start_date = datetime.now()
    end_date = meeting_data.start_time + timedelta(days=1)
    available_slots = scheduler.get_available_slots(start_date, end_date)
    
    # Check if requested time fits in an available slot
    is_available = False
    for slot_start, slot_end in available_slots:
        if slot_start <= meeting_data.start_time and meeting_data.end_time <= slot_end:
            is_available = True
            break
    
    if not is_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requested time slot is not available"
        )
    
    # Create meeting
    new_meeting = Meeting(
        user_id=user.id,
        created_by_owner=False,
        **meeting_data.model_dump()
    )
    db.add(new_meeting)
    db.commit()
    db.refresh(new_meeting)
    
    # Regenerate study schedule
    scheduler.regenerate_schedule()
    
    logger.info(f"Public meeting scheduled for {username}: {new_meeting.title}")
    return new_meeting


# ============= Study Block Endpoints =============

@app.get("/api/study-blocks", response_model=List[StudyBlockResponse])
def get_study_blocks(
    start_date: datetime = None,
    end_date: datetime = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get scheduled study blocks"""
    query = db.query(StudyBlock).filter(StudyBlock.user_id == current_user.id)
    
    if start_date:
        query = query.filter(StudyBlock.start_time >= start_date)
    if end_date:
        query = query.filter(StudyBlock.start_time <= end_date)
    
    study_blocks = query.order_by(StudyBlock.start_time).all()
    
    # Enrich with assignment details
    response = []
    for block in study_blocks:
        assignment = db.query(Assignment).filter(Assignment.id == block.assignment_id).first()
        response.append(StudyBlockResponse(
            id=block.id,
            assignment_id=block.assignment_id,
            assignment_title=assignment.title if assignment else "Unknown",
            assignment_category=assignment.category if assignment else "Unknown",
            start_time=block.start_time,
            end_time=block.end_time,
            status=block.status
        ))
    
    return response


@app.post("/api/study-blocks/regenerate", response_model=List[StudyBlockResponse])
def regenerate_study_blocks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Regenerate study schedule"""
    scheduler = Scheduler(current_user, db)
    scheduler.regenerate_schedule()
    
    # Return updated study blocks
    study_blocks = db.query(StudyBlock).filter(
        StudyBlock.user_id == current_user.id,
        StudyBlock.status == "scheduled"
    ).order_by(StudyBlock.start_time).all()
    
    response = []
    for block in study_blocks:
        assignment = db.query(Assignment).filter(Assignment.id == block.assignment_id).first()
        response.append(StudyBlockResponse(
            id=block.id,
            assignment_id=block.assignment_id,
            assignment_title=assignment.title if assignment else "Unknown",
            assignment_category=assignment.category if assignment else "Unknown",
            start_time=block.start_time,
            end_time=block.end_time,
            status=block.status
        ))
    
    logger.info(f"Study schedule regenerated for {current_user.username}")
    return response


# ============= Calendar View Endpoint =============

@app.get("/api/calendar", response_model=CalendarResponse)
def get_calendar(
    start_date: datetime,
    end_date: datetime,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all calendar events (assignments, classes, meetings, study blocks) for date range"""
    events = []
    
    # Get assignments
    assignments = db.query(Assignment).filter(
        Assignment.user_id == current_user.id,
        Assignment.due_date >= start_date,
        Assignment.due_date <= end_date
    ).all()
    
    for assignment in assignments:
        events.append(CalendarEvent(
            id=assignment.id,
            type="assignment",
            title=assignment.title,
            description=assignment.description,
            start_time=assignment.due_date,
            end_time=None,
            category=assignment.category,
            completed=assignment.completed
        ))
    
    # Get classes (expand recurring classes to actual dates)
    classes = db.query(ClassSchedule).filter(ClassSchedule.user_id == current_user.id).all()
    current_date = start_date.date()
    while current_date <= end_date.date():
        day_of_week = current_date.weekday()
        for cls in classes:
            if cls.day_of_week == day_of_week:
                # Parse times
                start_parts = cls.start_time.split(':')
                end_parts = cls.end_time.split(':')
                start_dt = datetime.combine(current_date, datetime.min.time().replace(
                    hour=int(start_parts[0]), minute=int(start_parts[1])
                ))
                end_dt = datetime.combine(current_date, datetime.min.time().replace(
                    hour=int(end_parts[0]), minute=int(end_parts[1])
                ))
                
                events.append(CalendarEvent(
                    id=cls.id,
                    type="class",
                    title=cls.title,
                    description="",
                    start_time=start_dt,
                    end_time=end_dt
                ))
        current_date += timedelta(days=1)
    
    # Get meetings
    meetings = db.query(Meeting).filter(
        Meeting.user_id == current_user.id,
        Meeting.start_time >= start_date,
        Meeting.start_time <= end_date
    ).all()
    
    for meeting in meetings:
        events.append(CalendarEvent(
            id=meeting.id,
            type="meeting",
            title=meeting.title,
            description=meeting.description,
            start_time=meeting.start_time,
            end_time=meeting.end_time
        ))
    
    # Get study blocks
    study_blocks = db.query(StudyBlock).filter(
        StudyBlock.user_id == current_user.id,
        StudyBlock.start_time >= start_date,
        StudyBlock.start_time <= end_date
    ).all()
    
    for block in study_blocks:
        assignment = db.query(Assignment).filter(Assignment.id == block.assignment_id).first()
        events.append(CalendarEvent(
            id=block.id,
            type="study_block",
            title=f"Study: {assignment.title if assignment else 'Unknown'}",
            description=assignment.category if assignment else "",
            start_time=block.start_time,
            end_time=block.end_time,
            category=assignment.category if assignment else None
        ))
    
    return CalendarResponse(events=events)


# ============= Health Check =============

@app.get("/")
def root():
    """Health check endpoint"""
    return {
        "message": "CMUCal API is running",
        "version": "1.0.1",
        "status": "healthy"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)