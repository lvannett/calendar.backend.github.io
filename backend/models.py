from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Time, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    wake_time = Column(String, default="07:00")  # Format: "HH:MM"
    bedtime = Column(String, default="23:00")
    default_study_block_minutes = Column(Integer, default=90)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    assignments = relationship("Assignment", back_populates="user", cascade="all, delete-orphan")
    classes = relationship("ClassSchedule", back_populates="user", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="user", cascade="all, delete-orphan")
    study_blocks = relationship("StudyBlock", back_populates="user", cascade="all, delete-orphan")


class Assignment(Base):
    __tablename__ = "assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    category = Column(String, default="General")  # e.g., "Math", "CS", "RA Duties"
    due_date = Column(DateTime, nullable=False)
    priority = Column(Integer, default=1)  # 1=low, 2=medium, 3=high
    estimated_time_minutes = Column(Integer, nullable=True)  # User can specify or leave null
    actual_time_minutes = Column(Integer, nullable=True)  # Filled when completed
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="assignments")
    study_blocks = relationship("StudyBlock", back_populates="assignment", cascade="all, delete-orphan")


class ClassSchedule(Base):
    __tablename__ = "class_schedule"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time = Column(String, nullable=False)  # Format: "HH:MM"
    end_time = Column(String, nullable=False)
    recurring = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="classes")


class Meeting(Base):
    __tablename__ = "meetings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, default="")
    attendee_name = Column(String, nullable=True)
    attendee_email = Column(String, nullable=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    created_by_owner = Column(Boolean, default=True)  # False if booked via public link
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="meetings")


class StudyBlock(Base):
    __tablename__ = "study_blocks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("assignments.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    status = Column(String, default="scheduled")  # scheduled, completed, skipped
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="study_blocks")
    assignment = relationship("Assignment", back_populates="study_blocks")
