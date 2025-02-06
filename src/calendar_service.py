from typing import Dict, List
from googleapiclient.discovery import build
from datetime import datetime, timedelta

def get_calendar_service(credentials):
    """Create Google Calendar service instance."""
    return build('calendar', 'v3', credentials=credentials)

def get_available_slots(
    service,
    start_date: datetime,
    end_date: datetime,
    duration_minutes: int = 60
) -> List[Dict]:
    """Get available time slots between start_date and end_date."""
    
    # Get busy slots
    body = {
        "timeMin": start_date.isoformat() + 'Z',
        "timeMax": end_date.isoformat() + 'Z',
        "items": [{"id": "primary"}]
    }
    
    busy_slots = service.freebusy().query(body=body).execute()
    busy_periods = busy_slots.get('calendars', {}).get('primary', {}).get('busy', [])
    
    # Create time slots
    available_slots = []
    current_slot = start_date
    
    while current_slot < end_date:
        slot_end = current_slot + timedelta(minutes=duration_minutes)
        
        # Check if slot is during business hours (9 AM to 5 PM)
        if 9 <= current_slot.hour < 17:
            is_available = True
            
            # Check if slot overlaps with any busy period
            for busy_period in busy_periods:
                busy_start = datetime.fromisoformat(busy_period['start'].replace('Z', '+00:00'))
                busy_end = datetime.fromisoformat(busy_period['end'].replace('Z', '+00:00'))
                
                if (current_slot >= busy_start and current_slot < busy_end) or \
                   (slot_end > busy_start and slot_end <= busy_end):
                    is_available = False
                    break
            
            if is_available:
                available_slots.append({
                    'start': current_slot.isoformat(),
                    'end': slot_end.isoformat()
                })
        
        current_slot += timedelta(minutes=duration_minutes)
    
    return available_slots

def create_appointment(
    service,
    start_time: datetime,
    end_time: datetime,
    summary: str,
    description: str,
    attendee_email: str
) -> Dict:
    """Create a calendar appointment."""
    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'UTC',
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'UTC',
        },
        'attendees': [
            {'email': attendee_email},
        ],
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 30},
            ],
        },
    }

    try:
        event = service.events().insert(
            calendarId='primary',
            body=event,
            sendUpdates='all'
        ).execute()
        return event
    except Exception as e:
        print(f"Error creating appointment: {str(e)}")
        return None 