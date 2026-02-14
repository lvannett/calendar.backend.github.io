"""
Test script for CMU Schedule Planner API
Run this to verify your backend is working correctly
"""

import requests
import json

# Change this to your deployed backend URL or use localhost for local testing
API_URL = "http://localhost:5000"  # Change to your Render URL when deployed

def test_health():
    """Test health check endpoint"""
    print("Testing health check...")
    response = requests.get(f"{API_URL}/api/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    print()

def test_calendar_parse():
    """Test calendar parsing with sample iCal data"""
    print("Testing calendar parsing...")
    
    sample_ical = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
SUMMARY:Math Class
DTSTART:20240215T100000
DTEND:20240215T113000
END:VEVENT
END:VCALENDAR"""
    
    response = requests.post(
        f"{API_URL}/api/calendar/parse",
        json={"ical_content": sample_ical}
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    print()

def test_schedule_generation():
    """Test schedule generation (requires OpenAI API key to be set)"""
    print("Testing schedule generation...")
    
    data = {
        "calendar_events": [
            {
                "summary": "Math Class",
                "start": "2024-02-15T10:00:00",
                "end": "2024-02-15T11:30:00"
            }
        ],
        "assignments": [
            {
                "name": "Set Theory Homework",
                "due_date": "2024-02-20T23:59:00",
                "hours_needed": 6,
                "priority": 1
            }
        ],
        "activities": [
            {
                "name": "Guitar Practice",
                "hours": 3,
                "priority": 3,
                "is_weekly": True
            }
        ],
        "preferences": {
            "wake_time": "08:00",
            "bed_time": "23:00"
        }
    }
    
    response = requests.post(
        f"{API_URL}/api/schedule/generate",
        json=data
    )
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        schedule = response.json()
        print(f"Generated {len(schedule.get('schedule', []))} study blocks")
        print(f"First few blocks:")
        for block in schedule.get('schedule', [])[:3]:
            print(f"  - {block.get('name')}: {block.get('start')} to {block.get('end')}")
    else:
        print(f"Error: {response.text}")
    print()

if __name__ == "__main__":
    print("=== CMU Schedule Planner API Tests ===\n")
    
    try:
        test_health()
        test_calendar_parse()
        
        # Uncomment this when you have OpenAI API key configured
        # test_schedule_generation()
        
        print("✓ Basic tests completed successfully!")
        print("\nNote: Schedule generation test is commented out.")
        print("Uncomment it in test_api.py after setting up your OpenAI API key.")
        
    except requests.exceptions.ConnectionError:
        print("✗ Error: Could not connect to the API.")
        print(f"Make sure the server is running at {API_URL}")
    except Exception as e:
        print(f"✗ Error: {e}")
