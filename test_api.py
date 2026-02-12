"""
Example test script to demonstrate API functionality
Run with: python test_api.py
"""

import requests
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"  # Change to your deployed URL

def test_complete_workflow():
    """Test the complete workflow of the RA/CA Scheduler"""
    
    print("=== RA/CA Scheduler API Test ===\n")
    
    # 1. Register a user
    print("1. Registering new user...")
    register_response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "username": "test_ra",
            "password": "securepassword123"
        }
    )
    print(f"   Status: {register_response.status_code}")
    if register_response.status_code != 201:
        print(f"   Error: {register_response.json()}")
        return
    
    # 2. Login
    print("\n2. Logging in...")
    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "username": "test_ra",
            "password": "securepassword123"
        }
    )
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"   Token received: {token[:20]}...")
    
    # 3. Update preferences
    print("\n3. Updating user preferences...")
    prefs_response = requests.put(
        f"{BASE_URL}/api/preferences",
        headers=headers,
        json={
            "wake_time": "07:00",
            "bedtime": "23:00",
            "default_study_block_minutes": 90
        }
    )
    print(f"   Preferences updated: {prefs_response.json()}")
    
    # 4. Add a class schedule
    print("\n4. Adding class schedule...")
    class_response = requests.post(
        f"{BASE_URL}/api/classes",
        headers=headers,
        json={
            "title": "Intro to Computer Science",
            "day_of_week": 0,  # Monday
            "start_time": "10:00",
            "end_time": "11:30"
        }
    )
    print(f"   Class added: {class_response.json()['title']}")
    
    # 5. Create assignments
    print("\n5. Creating assignments...")
    assignments = [
        {
            "title": "CS Homework 1",
            "category": "Computer Science",
            "due_date": (datetime.now() + timedelta(days=3)).isoformat(),
            "priority": 2,
            "estimated_time_minutes": 120
        },
        {
            "title": "RA Bulletin Board",
            "category": "RA Duties",
            "due_date": (datetime.now() + timedelta(days=5)).isoformat(),
            "priority": 1,
            "estimated_time_minutes": 60
        },
        {
            "title": "Math Problem Set",
            "category": "Mathematics",
            "due_date": (datetime.now() + timedelta(days=7)).isoformat(),
            "priority": 3,
            "estimated_time_minutes": 180
        }
    ]
    
    for assignment in assignments:
        response = requests.post(
            f"{BASE_URL}/api/assignments",
            headers=headers,
            json=assignment
        )
        print(f"   - Created: {response.json()['title']}")
    
    # 6. View study blocks
    print("\n6. Viewing generated study blocks...")
    study_blocks_response = requests.get(
        f"{BASE_URL}/api/study-blocks",
        headers=headers
    )
    study_blocks = study_blocks_response.json()
    print(f"   Generated {len(study_blocks)} study blocks:")
    for block in study_blocks[:5]:  # Show first 5
        start = datetime.fromisoformat(block['start_time'].replace('Z', '+00:00'))
        print(f"   - {start.strftime('%a %m/%d %I:%M %p')}: {block['assignment_title']} ({block['assignment_category']})")
    
    # 7. Create a meeting
    print("\n7. Creating a meeting...")
    meeting_response = requests.post(
        f"{BASE_URL}/api/meetings",
        headers=headers,
        json={
            "title": "RA Staff Meeting",
            "description": "Weekly staff meeting",
            "start_time": (datetime.now() + timedelta(days=2, hours=5)).isoformat(),
            "end_time": (datetime.now() + timedelta(days=2, hours=6)).isoformat()
        }
    )
    print(f"   Meeting created: {meeting_response.json()['title']}")
    
    # 8. Check public availability
    print("\n8. Checking public availability (for meeting scheduling)...")
    availability_response = requests.get(
        f"{BASE_URL}/api/public/availability/test_ra",
        params={"days_ahead": 3}
    )
    available_slots = availability_response.json()['available_slots']
    print(f"   Found {len(available_slots)} available time slots")
    if available_slots:
        print(f"   First available: {available_slots[0]['start_time']}")
    
    # 9. Get calendar view
    print("\n9. Getting calendar view...")
    start_date = datetime.now().isoformat()
    end_date = (datetime.now() + timedelta(days=7)).isoformat()
    calendar_response = requests.get(
        f"{BASE_URL}/api/calendar",
        headers=headers,
        params={
            "start_date": start_date,
            "end_date": end_date
        }
    )
    events = calendar_response.json()['events']
    print(f"   Total events in next 7 days: {len(events)}")
    
    event_counts = {}
    for event in events:
        event_type = event['type']
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
    
    for event_type, count in event_counts.items():
        print(f"   - {event_type}: {count}")
    
    # 10. Complete an assignment
    print("\n10. Completing an assignment...")
    assignments_response = requests.get(
        f"{BASE_URL}/api/assignments",
        headers=headers
    )
    first_assignment = assignments_response.json()[0]
    
    complete_response = requests.post(
        f"{BASE_URL}/api/assignments/{first_assignment['id']}/complete",
        headers=headers,
        json={"actual_time_minutes": 100}
    )
    print(f"   Completed: {complete_response.json()['title']}")
    print(f"   Actual time: {complete_response.json()['actual_time_minutes']} minutes")
    
    print("\n=== Test Complete! ===")
    print("\nThe API is working correctly. Study blocks should have been")
    print("automatically regenerated after adding assignments and meetings.")


if __name__ == "__main__":
    try:
        test_complete_workflow()
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to API. Make sure the server is running at", BASE_URL)
    except Exception as e:
        print(f"Error: {e}")
