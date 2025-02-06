from typing import Dict, List
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
from google.oauth2.credentials import Credentials
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('calendar_service.log'),
        logging.StreamHandler()
    ]
)

# Set timezone to EST
EST = pytz.timezone('America/New_York')

def get_calendar_service(credentials=None):
    """Get or create calendar service."""
    try:
        service = build('calendar', 'v3', credentials=credentials)
        return service
    except Exception as e:
        logging.error(f"Error creating calendar service: {str(e)}")
        return None

def localize_datetime(dt):
    """Convert datetime to EST timezone."""
    if dt.tzinfo is None:
        return EST.localize(dt)
    return dt.astimezone(EST)

def get_available_slots(calendar_service, start_datetime, end_datetime, duration_minutes=30):
    """Get available time slots between start and end datetime."""
    try:
        # Ensure datetimes are in EST
        start_datetime = localize_datetime(start_datetime)
        end_datetime = localize_datetime(end_datetime)
        
        # Get busy periods
        body = {
            "timeMin": start_datetime.isoformat(),
            "timeMax": end_datetime.isoformat(),
            "items": [{"id": "primary"}]
        }
        
        events_result = calendar_service.freebusy().query(body=body).execute()
        busy_periods = events_result.get("calendars", {}).get("primary", {}).get("busy", [])
        
        # Convert busy periods to EST
        busy_periods = [
            {
                'start': localize_datetime(datetime.fromisoformat(period['start'].replace('Z', '+00:00'))),
                'end': localize_datetime(datetime.fromisoformat(period['end'].replace('Z', '+00:00')))
            }
            for period in busy_periods
        ]
        
        # Define business hours (9 AM to 5 PM EST)
        business_start_hour = 9
        business_end_hour = 17
        
        # Generate available slots
        available_slots = []
        current_slot = start_datetime.replace(
            hour=business_start_hour,
            minute=0,
            second=0,
            microsecond=0
        )
        
        while current_slot < end_datetime:
            # Skip if outside business hours
            if current_slot.hour < business_start_hour or current_slot.hour >= business_end_hour:
                current_slot += timedelta(minutes=duration_minutes)
                continue
            
            # Move to next day if past business hours
            if current_slot.hour >= business_end_hour:
                current_slot = (current_slot + timedelta(days=1)).replace(
                    hour=business_start_hour,
                    minute=0,
                    second=0,
                    microsecond=0
                )
                continue
            
            slot_end = current_slot + timedelta(minutes=duration_minutes)
            is_available = True
            
            # Check if slot overlaps with any busy period
            for busy in busy_periods:
                busy_start = busy['start']
                busy_end = busy['end']
                
                if (current_slot >= busy_start and current_slot < busy_end) or \
                   (slot_end > busy_start and slot_end <= busy_end) or \
                   (current_slot <= busy_start and slot_end >= busy_end):
                    is_available = False
                    break
            
            if is_available:
                available_slots.append({
                    'start': current_slot.isoformat(),
                    'end': slot_end.isoformat()
                })
            
            current_slot += timedelta(minutes=duration_minutes)
        
        return available_slots
        
    except Exception as e:
        logging.error(f"Error getting available slots: {str(e)}")
        return []

def create_appointment(calendar_service, start_time, duration_minutes, summary, description, attendee_email):
    """Create a calendar appointment."""
    try:
        # Ensure start_time is in EST
        start_time = localize_datetime(start_time)
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'America/New_York',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'America/New_York',
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
        
        event = calendar_service.events().insert(
            calendarId='primary',
            body=event,
            sendUpdates='all'
        ).execute()
        
        logging.info(f"Created appointment: {event.get('htmlLink')}")
        return event
        
    except Exception as e:
        logging.error(f"Error creating appointment: {str(e)}")
        return None 