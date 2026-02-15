from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import json
from icalendar import Calendar, Event as ICalEvent
from openai import OpenAI
import os
from typing import List, Dict, Any
import re

load_dotenv()

app = Flask(__name__)
CORS(app)


# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

class Assignment:
    def __init__(self, name: str, due_date: str, hours_needed: float, priority: int):
        self.name = name
        self.due_date = datetime.fromisoformat(due_date)
        self.hours_needed = hours_needed
        self.priority = priority
        
class Activity:
    def __init__(self, name: str, hours: float, priority: int, due_date: str = None, 
                 is_weekly: bool = False):
        self.name = name
        self.hours = hours
        self.priority = priority
        self.due_date = datetime.fromisoformat(due_date) if due_date else None
        self.is_weekly = is_weekly

def parse_ical(ical_content: str) -> List[Dict[str, Any]]:
    """Parse iCalendar content and extract events, expanding recurring events"""
    events = []
    try:
        from dateutil.rrule import rrulestr
        
        cal = Calendar.from_ical(ical_content)
        for component in cal.walk():
            if component.name == "VEVENT":
                summary = str(component.get('summary', 'Untitled'))
                dtstart = component.get('dtstart').dt
                dtend = component.get('dtend').dt
                rrule_str = component.get('rrule')
                
                # Convert date to datetime if needed
                if not isinstance(dtstart, datetime):
                    dtstart = datetime.combine(dtstart, datetime.min.time())
                if not isinstance(dtend, datetime):
                    dtend = datetime.combine(dtend, datetime.min.time())
                
                if rrule_str:
                    # Expand recurring event
                    try:
                        # Create rrule and generate occurrences starting from today
                        rrule = rrulestr(str(rrule_str), dtstart=dtstart)
                        
                        # Start from today or the event's start date, whichever is later
                        start_date = max(dtstart, datetime.now() - timedelta(days=7))  # Include last week
                        end_date = datetime.now() + timedelta(days=120)
                        
                        occurrences = list(rrule.between(start_date, end_date, inc=True))
                        
                        # Calculate duration
                        duration = dtend - dtstart
                        
                        # Create an event for each occurrence
                        for occurrence in occurrences[:100]:  # Limit to 100 instances
                            events.append({
                                'summary': summary,
                                'start': occurrence.isoformat(),
                                'end': (occurrence + duration).isoformat(),
                                'rrule': None  # Mark as expanded
                            })
                    except Exception as e:
                        print(f"Error expanding recurring event: {e}")
                        # If expansion fails, add the single instance
                        events.append({
                            'summary': summary,
                            'start': dtstart.isoformat(),
                            'end': dtend.isoformat(),
                            'rrule': str(rrule_str)
                        })
                else:
                    # Single event
                    events.append({
                        'summary': summary,
                        'start': dtstart.isoformat(),
                        'end': dtend.isoformat(),
                        'rrule': None
                    })
    except Exception as e:
        print(f"Error parsing iCal: {e}")
    
    return events

def generate_schedule_with_ai(calendar_events: List[Dict], assignments: List[Dict], 
                               activities: List[Dict], preferences: Dict) -> List[Dict]:
    """Use OpenAI to generate an optimized study schedule"""
    
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Prepare the prompt
    prompt = f"""You are a smart scheduling assistant for a CMU student. Your job is to schedule study blocks for assignments and activities.

TODAY'S DATE: {today}
IMPORTANT: Schedule all study blocks starting from TODAY or later. Do not schedule anything in the past.

CALENDAR EVENTS (already scheduled):
{json.dumps(calendar_events, indent=2)}

ASSIGNMENTS (need to schedule):
{json.dumps(assignments, indent=2)}

ACTIVITIES (optional, fill extra time):
{json.dumps(activities, indent=2)}

PREFERENCES:
- Wake up time: {preferences.get('wake_time', '08:00')}
- Bedtime: {preferences.get('bed_time', '23:00')}

RULES:
1. Each study block must be at least 30 minutes
2. For blocks longer than 3 hours, mix different assignments (guideline, not hard rule)
3. Don't schedule during existing calendar events
4. Only schedule between wake time and bedtime
5. Prioritize by due date first, then by priority (1=highest, 5=lowest)
6. Handle recurring events properly (e.g., "Math class every MWF")
7. For activities with is_weekly=true, spread hours across the week
8. Only schedule far enough into the future to complete all assignments
9. Activities are optional - only schedule if there's extra time after assignments
10. CRITICAL: All study blocks must be on {today} or later dates. No past dates!

OUTPUT FORMAT:
Return a JSON array of study blocks. Each block should have:
- name: string (what to work on)
- start: ISO datetime string (MUST be {today} or later)
- end: ISO datetime string
- type: "assignment" or "activity"

Example:
[
  {{
    "name": "Set Theory Homework",
    "start": "2026-02-15T14:00:00",
    "end": "2026-02-15T16:30:00",
    "type": "assignment"
  }}
]

IMPORTANT: 
- Return ONLY valid JSON, no other text
- Ensure all times are in ISO format
- Don't overlap with existing calendar events
- Be smart about spacing study sessions throughout available days
- ALL DATES MUST BE {today} OR LATER
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert scheduling assistant. Return only valid JSON. Schedule all study blocks from today forward, never in the past."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        # Extract JSON from response
        content = response.choices[0].message.content.strip()
        
        print(f"AI Response: {content[:500]}...")  # Print first 500 chars
        
        # Remove markdown code blocks if present
        if content.startswith('```'):
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
        
        schedule = json.loads(content)
        
        print(f"Successfully parsed {len(schedule)} study blocks")
        
        return schedule
        
    except Exception as e:
        print(f"Error calling OpenAI: {e}")
        import traceback
        traceback.print_exc()
        return []

def adjust_schedule_with_ai(existing_schedule: List[Dict], calendar_events: List[Dict],
                            assignments: List[Dict], preferences: Dict) -> List[Dict]:
    """Use OpenAI to adjust schedule for new conflicts with minimal changes"""
    
    prompt = f"""You are a smart scheduling assistant. A student has an existing study schedule, but new calendar events have been added that conflict with some study blocks.

EXISTING STUDY SCHEDULE:
{json.dumps(existing_schedule, indent=2)}

UPDATED CALENDAR EVENTS (including new conflicts):
{json.dumps(calendar_events, indent=2)}

ORIGINAL ASSIGNMENTS (for reference):
{json.dumps(assignments, indent=2)}

PREFERENCES:
- Wake up time: {preferences.get('wake_time', '08:00')}
- Bedtime: {preferences.get('bed_time', '23:00')}

TASK:
Adjust the study schedule to avoid conflicts with calendar events. Make MINIMAL changes - only move blocks that actually conflict.

RULES:
1. Keep as many original blocks as possible
2. Only move/reschedule blocks that conflict with calendar events
3. Maintain the same study block rules (30 min minimum, mix assignments in long blocks)
4. Don't schedule during existing calendar events
5. Only schedule between wake time and bedtime

OUTPUT FORMAT:
Return a JSON array of the ADJUSTED study blocks with the same format as before.

IMPORTANT: Return ONLY valid JSON, no other text.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert scheduling assistant. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        content = response.choices[0].message.content.strip()
        
        # Remove markdown code blocks if present
        if content.startswith('```'):
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'\s*```$', '', content)
        
        schedule = json.loads(content)
        return schedule
        
    except Exception as e:
        print(f"Error calling OpenAI: {e}")
        return existing_schedule

def create_ical_export(study_blocks: List[Dict]) -> str:
    """Generate iCalendar file from study blocks"""
    cal = Calendar()
    cal.add('prodid', '-//CMU Schedule Planner//EN')
    cal.add('version', '2.0')
    
    print(f"Creating iCal with {len(study_blocks)} blocks")
    
    for i, block in enumerate(study_blocks):
        try:
            event = ICalEvent()
            event.add('summary', block.get('name', f'Study Block {i+1}'))
            event.add('dtstart', datetime.fromisoformat(block['start']))
            event.add('dtend', datetime.fromisoformat(block['end']))
            event.add('description', f"Type: {block.get('type', 'study')}")
            cal.add_component(event)
        except Exception as e:
            print(f"Error adding block {i} to calendar: {e}")
            print(f"Block data: {block}")
    
    ical_string = cal.to_ical().decode('utf-8')
    print(f"Generated iCal string, length: {len(ical_string)}")
    
    return ical_string

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'message': 'CMU Schedule Planner API is running'})

@app.route('/api/test/schedule', methods=['GET'])
def test_schedule():
    """Test endpoint that returns dummy study blocks"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    test_blocks = []
    
    # Generate 3 test study blocks for tomorrow
    tomorrow = now + timedelta(days=1)
    tomorrow = tomorrow.replace(hour=14, minute=0, second=0, microsecond=0)
    
    for i in range(3):
        start = tomorrow + timedelta(hours=i*2)
        end = start + timedelta(hours=1.5)
        test_blocks.append({
            'name': f'Test Study Block {i+1}',
            'start': start.isoformat(),
            'end': end.isoformat(),
            'type': 'assignment'
        })
    
    return jsonify({'schedule': test_blocks, 'count': len(test_blocks)})

@app.route('/api/calendar/parse', methods=['POST'])
def parse_calendar():
    """Parse uploaded iCalendar file"""
    try:
        data = request.get_json()
        ical_content = data.get('ical_content', '')
        
        events = parse_ical(ical_content)
        return jsonify({'events': events})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/schedule/generate', methods=['POST'])
def generate_schedule():
    """Generate study schedule using AI"""
    try:
        data = request.get_json()
        
        calendar_events = data.get('calendar_events', [])
        assignments = data.get('assignments', [])
        activities = data.get('activities', [])
        preferences = data.get('preferences', {})
        
        print(f"Generating schedule with {len(calendar_events)} calendar events, {len(assignments)} assignments")
        
        # Generate schedule using OpenAI
        schedule = generate_schedule_with_ai(calendar_events, assignments, activities, preferences)
        
        print(f"AI returned {len(schedule)} study blocks")
        if len(schedule) > 0:
            print(f"Sample block: {schedule[0]}")
        
        return jsonify({'schedule': schedule})
    except Exception as e:
        print(f"Error in generate_schedule: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400

@app.route('/api/schedule/adjust', methods=['POST'])
def adjust_schedule():
    """Adjust existing schedule for new conflicts"""
    try:
        data = request.get_json()
        
        existing_schedule = data.get('existing_schedule', [])
        calendar_events = data.get('calendar_events', [])
        assignments = data.get('assignments', [])
        preferences = data.get('preferences', {})
        
        # Adjust schedule using OpenAI
        adjusted_schedule = adjust_schedule_with_ai(existing_schedule, calendar_events, 
                                                     assignments, preferences)
        
        return jsonify({'schedule': adjusted_schedule})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/schedule/export', methods=['POST'])
def export_schedule():
    """Export schedule as iCalendar file"""
    try:
        data = request.get_json()
        study_blocks = data.get('schedule', [])
        
        print(f"Exporting {len(study_blocks)} study blocks")
        if len(study_blocks) > 0:
            print(f"Sample block for export: {study_blocks[0]}")
        
        ical_content = create_ical_export(study_blocks)
        
        print(f"Generated iCal content, length: {len(ical_content)}")
        
        return jsonify({'ical_content': ical_content})
    except Exception as e:
        print(f"Error in export_schedule: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
