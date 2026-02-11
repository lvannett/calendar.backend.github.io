from datetime import datetime, timedelta, time as dt_time
from typing import List, Tuple, Dict
from sqlalchemy.orm import Session
from models import User, Assignment, ClassSchedule, Meeting, StudyBlock
import logging

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, user: User, db: Session):
        self.user = user
        self.db = db
        
    def parse_time(self, time_str: str) -> dt_time:
        """Parse time string 'HH:MM' to datetime.time object"""
        hours, minutes = map(int, time_str.split(':'))
        return dt_time(hours, minutes)
    
    def combine_datetime(self, date: datetime, time: dt_time) -> datetime:
        """Combine date and time into datetime"""
        return datetime.combine(date.date(), time)
    
    def get_available_slots(self, start_date: datetime, end_date: datetime) -> List[Tuple[datetime, datetime]]:
        """
        Get all available time slots for the user between start_date and end_date.
        Excludes: before wake time, after bedtime, classes, existing meetings.
        Returns list of (start_time, end_time) tuples.
        """
        available_slots = []
        wake_time = self.parse_time(self.user.wake_time)
        bed_time = self.parse_time(self.user.bedtime)
        
        current_date = start_date.date()
        end = end_date.date()
        
        while current_date <= end:
            # Daily available window
            day_start = self.combine_datetime(datetime.combine(current_date, wake_time), wake_time)
            day_end = self.combine_datetime(datetime.combine(current_date, bed_time), bed_time)
            
            # Get busy periods for this day
            busy_periods = self._get_busy_periods(current_date)
            
            # Find free slots within the day
            free_slots = self._subtract_busy_periods(day_start, day_end, busy_periods)
            available_slots.extend(free_slots)
            
            current_date += timedelta(days=1)
        
        return available_slots
    
    def _get_busy_periods(self, date: datetime.date) -> List[Tuple[datetime, datetime]]:
        """Get all busy periods (classes + meetings) for a specific date"""
        busy_periods = []
        
        # Get recurring classes for this day of week
        day_of_week = date.weekday()  # 0=Monday, 6=Sunday
        classes = self.db.query(ClassSchedule).filter(
            ClassSchedule.user_id == self.user.id,
            ClassSchedule.day_of_week == day_of_week
        ).all()
        
        for cls in classes:
            start_time = self.parse_time(cls.start_time)
            end_time = self.parse_time(cls.end_time)
            start_dt = self.combine_datetime(datetime.combine(date, start_time), start_time)
            end_dt = self.combine_datetime(datetime.combine(date, end_time), end_time)
            busy_periods.append((start_dt, end_dt))
        
        # Get meetings for this day
        day_start = datetime.combine(date, dt_time(0, 0))
        day_end = datetime.combine(date, dt_time(23, 59))
        meetings = self.db.query(Meeting).filter(
            Meeting.user_id == self.user.id,
            Meeting.start_time >= day_start,
            Meeting.start_time < day_end
        ).all()
        
        for meeting in meetings:
            busy_periods.append((meeting.start_time, meeting.end_time))
        
        # Sort by start time
        busy_periods.sort(key=lambda x: x[0])
        
        # Merge overlapping periods
        merged = []
        for start, end in busy_periods:
            if merged and start <= merged[-1][1]:
                # Overlapping, extend the previous period
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        
        return merged
    
    def _subtract_busy_periods(
        self, 
        start: datetime, 
        end: datetime, 
        busy_periods: List[Tuple[datetime, datetime]]
    ) -> List[Tuple[datetime, datetime]]:
        """Subtract busy periods from a time range to get free slots"""
        free_slots = []
        current = start
        
        for busy_start, busy_end in busy_periods:
            if current < busy_start:
                # There's free time before this busy period
                free_slots.append((current, busy_start))
            current = max(current, busy_end)
        
        # Add remaining time after last busy period
        if current < end:
            free_slots.append((current, end))
        
        return free_slots
    
    def estimate_assignment_time(self, assignment: Assignment) -> int:
        """
        Estimate time needed for an assignment in minutes.
        Priority:
        1. User-provided estimated_time_minutes
        2. Average of similar assignments (same category) that were completed
        3. Default to 120 minutes (2 hours)
        """
        if assignment.estimated_time_minutes:
            return assignment.estimated_time_minutes
        
        # Look for completed assignments in the same category
        similar_completed = self.db.query(Assignment).filter(
            Assignment.user_id == self.user.id,
            Assignment.category == assignment.category,
            Assignment.completed == True,
            Assignment.actual_time_minutes.isnot(None)
        ).all()
        
        if similar_completed:
            avg_time = sum(a.actual_time_minutes for a in similar_completed) / len(similar_completed)
            return int(avg_time)
        
        # Default
        return 120  # 2 hours
    
    def generate_study_schedule(self, days_ahead: int = 14) -> List[StudyBlock]:
        """
        Generate optimized study schedule for upcoming assignments.
        
        Algorithm:
        1. Get all incomplete assignments
        2. Sort by due date and priority
        3. Estimate time needed for each
        4. Allocate study blocks in available slots
        5. Ensure variety (don't study same subject too long)
        6. Respect max block duration
        """
        # Clear existing study blocks
        self.db.query(StudyBlock).filter(
            StudyBlock.user_id == self.user.id,
            StudyBlock.status == "scheduled"
        ).delete()
        self.db.commit()
        
        # Get incomplete assignments
        assignments = self.db.query(Assignment).filter(
            Assignment.user_id == self.user.id,
            Assignment.completed == False
        ).order_by(Assignment.due_date, Assignment.priority.desc()).all()
        
        if not assignments:
            return []
        
        # Calculate work needed for each assignment
        work_needed = {}  # assignment_id -> minutes_remaining
        for assignment in assignments:
            work_needed[assignment.id] = self.estimate_assignment_time(assignment)
        
        # Get available time slots
        start_date = datetime.now()
        end_date = start_date + timedelta(days=days_ahead)
        available_slots = self.get_available_slots(start_date, end_date)
        
        # Allocate study blocks
        study_blocks = []
        last_assignment_studied = None
        max_block_minutes = self.user.default_study_block_minutes
        
        for slot_start, slot_end in available_slots:
            slot_duration = int((slot_end - slot_start).total_seconds() / 60)
            
            # Skip very short slots (less than 30 minutes)
            if slot_duration < 30:
                continue
            
            remaining_slot = slot_duration
            current_time = slot_start
            
            while remaining_slot >= 30:  # At least 30 min blocks
                # Find next assignment to work on
                # Prefer variety - don't repeat the same assignment consecutively
                assignment_to_study = None
                
                for assignment in assignments:
                    if work_needed.get(assignment.id, 0) > 0:
                        # Prefer different assignment than last one (for variety)
                        if assignment.id != last_assignment_studied:
                            assignment_to_study = assignment
                            break
                
                # If all remaining assignments are the same, take it anyway
                if not assignment_to_study:
                    for assignment in assignments:
                        if work_needed.get(assignment.id, 0) > 0:
                            assignment_to_study = assignment
                            break
                
                if not assignment_to_study:
                    break  # All work done!
                
                # Determine block duration
                needed = work_needed[assignment_to_study.id]
                block_duration = min(needed, max_block_minutes, remaining_slot)
                
                # Create study block
                block_end = current_time + timedelta(minutes=block_duration)
                
                # Don't schedule too close to due date (leave at least 1 hour buffer)
                if block_end <= assignment_to_study.due_date - timedelta(hours=1):
                    study_block = StudyBlock(
                        user_id=self.user.id,
                        assignment_id=assignment_to_study.id,
                        start_time=current_time,
                        end_time=block_end,
                        status="scheduled"
                    )
                    study_blocks.append(study_block)
                    
                    # Update tracking
                    work_needed[assignment_to_study.id] -= block_duration
                    last_assignment_studied = assignment_to_study.id
                
                # Move to next part of slot
                current_time = block_end
                remaining_slot -= block_duration
        
        # Save to database
        self.db.bulk_save_objects(study_blocks)
        self.db.commit()
        
        logger.info(f"Generated {len(study_blocks)} study blocks for user {self.user.username}")
        return study_blocks
    
    def regenerate_schedule(self):
        """Regenerate the entire study schedule (useful after adding/removing meetings)"""
        return self.generate_study_schedule()
