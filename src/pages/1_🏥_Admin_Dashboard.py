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

# Load environment variables
load_dotenv()

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar'
]

# Constants
DEFAULT_CHECK_INTERVAL = 10  # 10 seconds
MIN_CHECK_INTERVAL = 10      # 10 seconds
MAX_CHECK_INTERVAL = 900     # 15 minutes

def initialize_services():
    """Initialize Google services."""
    try:
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
        
        # Initialize services
        st.session_state.credentials = creds
        st.session_state.calendar_service = get_calendar_service(creds)
        st.session_state.gmail_service = get_gmail_service(creds)
        
        # Initialize monitoring state
        if 'last_check_time' not in st.session_state:
            st.session_state.last_check_time = datetime.now()
        if 'processed_count' not in st.session_state:
            st.session_state.processed_count = 0
        if 'auto_refresh' not in st.session_state:
            st.session_state.auto_refresh = True  # Auto-refresh enabled by default
        if 'check_interval' not in st.session_state:
            st.session_state.check_interval = int(os.getenv('CHECK_INTERVAL_SECONDS', str(DEFAULT_CHECK_INTERVAL)))
        
        return True
    except Exception as e:
        st.error(f"Error initializing services: {str(e)}")
        return False

def main():
    st.set_page_config(
        page_title="Admin Dashboard",
        page_icon="🏥",
        layout="wide"
    )
    
    st.title("🏥 Admin Dashboard")
    
    # Initialize services if not already initialized
    if 'credentials' not in st.session_state:
        with st.spinner("Initializing services..."):
            if not initialize_services():
                st.error("Failed to initialize services. Please check your credentials and try again.")
                return
    
    # Create tabs for different sections
    tab1, tab2 = st.tabs(["📊 Overview", "⚙️ Settings"])
    
    with tab1:
        st.header("System Overview")
        
        # Email monitoring status
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("### Email Monitor")
            if 'last_check_time' in st.session_state:
                time_diff = datetime.now() - st.session_state.last_check_time
                st.info(f"Last Check: {st.session_state.last_check_time.strftime('%I:%M:%S %p')} ({int(time_diff.total_seconds())}s ago)")
            st.success(f"Processed Requests: {st.session_state.processed_count}")
            
            # Auto-refresh toggle
            auto_refresh = st.toggle("Auto-refresh", value=st.session_state.auto_refresh)
            if auto_refresh != st.session_state.auto_refresh:
                st.session_state.auto_refresh = auto_refresh
                st.rerun()
        
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
    
    with tab2:
        st.header("Settings")
        
        st.write("### Email Monitor Settings")
        if st.session_state.auto_refresh:
            check_interval = st.slider(
                "Check interval (seconds)",
                min_value=MIN_CHECK_INTERVAL,
                max_value=MAX_CHECK_INTERVAL,
                value=st.session_state.check_interval,
                step=10
            )
            if check_interval != st.session_state.check_interval:
                st.session_state.check_interval = check_interval
                st.success(f"Check interval updated to {check_interval} seconds")
        
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
                next_check = int(st.session_state.check_interval - time_since_last_check)
                if next_check <= 5:
                    st.warning(f"Checking emails in {next_check} seconds...")
                else:
                    st.info(f"Next auto-check in {next_check} seconds")
                time.sleep(1)
                st.rerun()

if __name__ == "__main__":
    main() 