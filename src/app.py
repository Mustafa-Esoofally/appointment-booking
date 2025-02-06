import streamlit as st
import os
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv
import time
from calendar_service import get_calendar_service, get_available_slots
from gmail_monitor import get_gmail_service, check_new_emails
from appointment_agent import process_new_emails
import logging
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_service.log'),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv()

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar'
]

def get_upcoming_appointments(calendar_service, days=30):
    """Get all upcoming appointments."""
    try:
        now = datetime.utcnow().isoformat() + 'Z'
        end_date = (datetime.utcnow() + timedelta(days=days)).isoformat() + 'Z'
        
        events_result = calendar_service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=end_date,
            maxResults=100,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        return events_result.get('items', [])
    except Exception as e:
        st.error(f"Error fetching appointments: {str(e)}")
        return []

def format_appointment_time(event):
    """Format the appointment time for display."""
    start = event['start'].get('dateTime', event['start'].get('date'))
    end = event['end'].get('dateTime', event['end'].get('date'))
    
    start_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
    end_time = datetime.fromisoformat(end.replace('Z', '+00:00'))
    
    return f"{start_time.strftime('%B %d, %Y %I:%M %p')} - {end_time.strftime('%I:%M %p')}"

def initialize_services():
    """Initialize Google services."""
    try:
        # Check if we already have valid credentials in session state
        if 'credentials' in st.session_state and st.session_state.credentials:
            creds = st.session_state.credentials
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
        else:
            # Check if token.json exists
            if os.path.exists('token.json'):
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
        
        # Store credentials in session state
        st.session_state.credentials = creds
        
        # Initialize services using credentials
        if 'calendar_service' not in st.session_state or st.session_state.calendar_service is None:
            st.session_state.calendar_service = get_calendar_service(creds)
            
        if 'gmail_service' not in st.session_state or st.session_state.gmail_service is None:
            st.session_state.gmail_service = get_gmail_service(creds)
            
        # Initialize monitoring state
        if 'last_check_time' not in st.session_state:
            st.session_state.last_check_time = datetime.now()
        if 'processed_count' not in st.session_state:
            st.session_state.processed_count = 0
        if 'auto_refresh' not in st.session_state:
            st.session_state.auto_refresh = False
        if 'check_interval' not in st.session_state:
            st.session_state.check_interval = int(os.getenv('CHECK_INTERVAL_SECONDS', '300'))
        
        return True
    except Exception as e:
        st.error(f"Error initializing services: {str(e)}")
        return False

def main():
    st.set_page_config(
        page_title="Medical Appointment System",
        page_icon="🏥",
        layout="wide"
    )
    
    st.title("🏥 Medical Appointment System")
    
    # Initialize services
    if not initialize_services():
        st.error("Unable to initialize required services. Please check your credentials and try again.")
        if st.button("Log in with Google"):
            initialize_services()  # This will trigger the OAuth flow
            st.rerun()  # Rerun the app after authentication
        return

    # Display Google Account Information
    with st.sidebar:
        st.header("🔑 Account Information")
        if hasattr(st.session_state, 'credentials') and st.session_state.credentials:
            try:
                if hasattr(st.session_state.credentials, 'id_token'):
                    email = st.session_state.credentials.id_token.get('email', 'Not available')
                else:
                    # Try to get email from token info
                    token_info = st.session_state.credentials.token_info
                    email = token_info.get('email', 'Not available') if token_info else 'Not available'
                st.success(f"Connected as: {email}")
            except Exception as e:
                st.success("Connected to Google Account")
            if st.button("Logout"):
                if os.path.exists('token.json'):
                    os.remove('token.json')
                st.session_state.clear()
                st.experimental_rerun()
        else:
            st.warning("Not connected to Google Account")
            if st.button("Connect Google Account"):
                initialize_services()
                st.experimental_rerun()
    
    # Create tabs for different sections
    tab1, tab2 = st.tabs(["📅 Appointments Manager", "📧 Email Monitor"])
    
    with tab1:
        st.header("Appointments Overview")
        
        # Create two columns for the main content
        left_col, right_col = st.columns([2, 1])
        
        with left_col:
            st.subheader("Upcoming Appointments")
            # Filter options
            col1, col2 = st.columns(2)
            with col1:
                days_filter = st.selectbox(
                    "Show appointments for next",
                    options=[7, 14, 30, 60],
                    format_func=lambda x: f"{x} days",
                    index=2
                )
            
            with col2:
                status_filter = st.multiselect(
                    "Status",
                    options=["Confirmed", "Pending", "Cancelled"],
                    default=["Confirmed", "Pending"]
                )
            
            # Fetch and display appointments
            appointments = get_upcoming_appointments(st.session_state.calendar_service, days_filter)
            
            if appointments:
                for event in appointments:
                    with st.expander(f"📅 {event.get('summary', 'Untitled Appointment')}"):
                        col1, col2 = st.columns([2, 1])
                        
                        with col1:
                            st.write("**Time:**", format_appointment_time(event))
                            st.write("**Description:**", event.get('description', 'No description provided'))
                            
                            # Get attendee information
                            attendees = event.get('attendees', [])
                            if attendees:
                                st.write("**Patient Email:**", attendees[0].get('email', 'No email provided'))
                                st.write("**Status:**", attendees[0].get('responseStatus', 'pending').title())
                        
                        with col2:
                            if st.button("Cancel Appointment", key=event['id']):
                                try:
                                    st.session_state.calendar_service.events().delete(
                                        calendarId='primary',
                                        eventId=event['id']
                                    ).execute()
                                    st.success("Appointment cancelled successfully!")
                                    st.experimental_rerun()
                                except Exception as e:
                                    st.error(f"Error cancelling appointment: {str(e)}")
            else:
                st.info("No upcoming appointments found")

        with right_col:
            st.subheader("Available Slots")
            start_date = datetime.now().date()
            end_date = start_date + timedelta(days=7)  # Show next 7 days
            
            available_slots = get_available_slots(
                st.session_state.calendar_service,
                datetime.combine(start_date, datetime.min.time()),
                datetime.combine(end_date, datetime.max.time()),
                30
            )
            
            # Display available slots in a compact format
            current_date = None
            for slot in available_slots:
                slot_time = datetime.fromisoformat(slot['start'])
                if current_date != slot_time.date():
                    current_date = slot_time.date()
                    st.write(f"**{current_date.strftime('%A, %B %d')}**")
                st.write(f"• {slot_time.strftime('%I:%M %p')}")
            
            if not available_slots:
                st.info("No available slots in the next 7 days")
    
    with tab2:
        st.header("📧 Email Monitor Status")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("### Status")
            if 'last_check_time' in st.session_state:
                time_diff = datetime.now() - st.session_state.last_check_time
                st.info(f"Last Check: {st.session_state.last_check_time.strftime('%I:%M:%S %p')} ({int(time_diff.total_seconds())}s ago)")
            st.success(f"Processed Requests: {st.session_state.processed_count}")
            
            # Auto-refresh toggle
            auto_refresh = st.toggle("Auto-refresh", value=st.session_state.auto_refresh)
            if auto_refresh != st.session_state.auto_refresh:
                st.session_state.auto_refresh = auto_refresh
                st.experimental_rerun()
            
            if st.session_state.auto_refresh:
                check_interval = st.slider(
                    "Check interval (seconds)",
                    min_value=60,
                    max_value=900,
                    value=st.session_state.check_interval,
                    step=60
                )
                if check_interval != st.session_state.check_interval:
                    st.session_state.check_interval = check_interval
        
        with col2:
            st.write("### Controls")
            if st.button("Check Emails Now"):
                with st.spinner("Checking emails..."):
                    count = process_new_emails(st.session_state.credentials)
                    st.session_state.processed_count += count
                    st.session_state.last_check_time = datetime.now()
                    if count > 0:
                        st.success(f"Processed {count} new appointment requests!")
                    else:
                        st.info("No new appointment requests found.")
        
        # Auto-refresh logic
        if st.session_state.auto_refresh:
            time_since_last_check = (datetime.now() - st.session_state.last_check_time).total_seconds()
            if time_since_last_check >= st.session_state.check_interval:
                with st.spinner("Auto-checking emails..."):
                    count = process_new_emails(st.session_state.credentials)
                    st.session_state.processed_count += count
                    st.session_state.last_check_time = datetime.now()
                    if count > 0:
                        st.success(f"Auto-processed {count} new appointment requests!")
                st.rerun()
            else:
                st.info(f"Next auto-check in {int(st.session_state.check_interval - time_since_last_check)} seconds")
                time.sleep(1)
                st.rerun()

if __name__ == "__main__":
    main() 