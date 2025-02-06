import streamlit as st
import os
from datetime import datetime, timedelta
import pytz
from calendar_service import get_calendar_service, get_available_slots, create_appointment
from gmail_monitor import get_gmail_service, send_booking_link
from urllib.parse import parse_qs
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from payment_service import generate_checkout_link, get_appointment_cost
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('booking.log'),
        logging.StreamHandler()
    ]
)

# Set timezone to EST
EST = pytz.timezone('America/New_York')

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar'
]

def get_current_time_est():
    """Get current time in EST timezone."""
    return datetime.now(EST)

def initialize_services():
    """Initialize calendar and gmail services if not already in session state."""
    try:
        # Check if token.json exists and initialize credentials
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
            
        return True
    except Exception as e:
        st.error(f"Error initializing services: {str(e)}")
        return False

def initialize_booking_state():
    """Initialize or reset booking state."""
    if 'booking_step' not in st.session_state:
        st.session_state.booking_step = 1
    if 'selected_slot' not in st.session_state:
        st.session_state.selected_slot = None
    if 'customer_details' not in st.session_state:
        st.session_state.customer_details = {}
    if 'payment_url' not in st.session_state:
        st.session_state.payment_url = None
    if 'appointment_type' not in st.session_state:
        # Get appointment type from URL parameters
        st.session_state.appointment_type = st.query_params.get('type', 'general')
    if 'customer_email' not in st.session_state:
        st.session_state.customer_email = st.query_params.get('email', '')

def format_slot_time(slot):
    """Format time slot for display."""
    start_time = datetime.fromisoformat(slot['start'])
    end_time = datetime.fromisoformat(slot['end'])
    return f"{start_time.strftime('%B %d, %Y %I:%M %p')} - {end_time.strftime('%I:%M %p')} EST"

def create_confirmed_appointment(slot, customer_details, appointment_type, duration):
    """Create a confirmed appointment in the calendar."""
    try:
        start_time = datetime.fromisoformat(slot['start'])
        
        appointment = create_appointment(
            st.session_state.calendar_service,
            start_time,
            duration,
            f"{appointment_type.replace('_', ' ').title()} - {customer_details['name']}",
            f"Type: {appointment_type}\nPhone: {customer_details['phone']}\nNotes: {customer_details['notes']}",
            customer_details['email']
        )
        
        if appointment:
            # Send confirmation email
            confirmation_message = f"""
            Your {appointment_type.replace('_', ' ')} appointment has been confirmed!
            
            Details:
            Date & Time: {format_slot_time(slot)}
            Duration: {duration} minutes
            
            Please remember:
            - Arrive 5 minutes early
            - Bring any relevant medical records
            - 24-hour cancellation notice required
            
            Thank you for booking with us!
            """
            
            send_booking_link(
                st.session_state.gmail_service,
                customer_details['email'],
                None,  # No thread_id for confirmation emails
                confirmation_message,
                subject="Your Appointment Confirmation"
            )
            
            return True
    except Exception as e:
        logging.error(f"Error creating appointment: {str(e)}")
    
    return False

def main():
    st.set_page_config(
        page_title="Book Appointment",
        page_icon="📅",
        layout="wide"
    )
    
    st.title("📅 Book Your Appointment")
    
    # Initialize services
    if not initialize_services():
        st.error("Unable to initialize required services. Please check your credentials and try again.")
        return
    
    # Initialize state
    initialize_booking_state()
    
    # Progress bar
    progress_text = {
        1: "Select Time Slot",
        2: "Confirm Details",
        3: "Complete Payment"
    }
    st.progress((st.session_state.booking_step - 1) / 2)
    st.subheader(progress_text[st.session_state.booking_step])
    
    if st.session_state.booking_step == 1:
        # Step 1: Select time slot
        current_time = get_current_time_est()
        start_date = current_time.date()
        end_date = start_date + timedelta(days=14)  # Show next 14 days
        
        available_slots = get_available_slots(
            st.session_state.calendar_service,
            datetime.combine(start_date, datetime.min.time(), tzinfo=EST),
            datetime.combine(end_date, datetime.max.time(), tzinfo=EST),
            30  # 30-minute slots
        )
        
        # Group slots by date
        current_date = None
        for slot in available_slots:
            slot_time = datetime.fromisoformat(slot['start'])
            if current_date != slot_time.date():
                current_date = slot_time.date()
                st.write(f"### {current_date.strftime('%A, %B %d')}")
            
            # Create a button for each time slot
            if st.button(slot_time.strftime('%I:%M %p EST'), key=slot['start']):
                st.session_state.selected_slot = slot
                st.session_state.booking_step = 2
                st.rerun()
        
        if not available_slots:
            st.info("No available slots in the next 14 days. Please try again later.")
    
    elif st.session_state.booking_step == 2:
        # Step 2: Confirm details
        st.write("### Selected Time")
        st.info(format_slot_time(st.session_state.selected_slot))
        
        st.write("### Appointment Type")
        st.info(st.session_state.appointment_type.replace('_', ' ').title())
        
        # Calculate cost
        duration = (
            datetime.fromisoformat(st.session_state.selected_slot['end']) -
            datetime.fromisoformat(st.session_state.selected_slot['start'])
        ).total_seconds() / 60
        
        cost = get_appointment_cost(st.session_state.appointment_type, int(duration))
        st.write("### Cost")
        st.info(f"${cost:.2f}")
        
        # Customer information form
        with st.form("booking_form"):
            email = st.text_input("Email", value=st.session_state.customer_email)
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number")
            notes = st.text_area("Additional Notes")
            
            if st.form_submit_button("Proceed to Payment"):
                st.session_state.customer_details = {
                    "email": email,
                    "name": name,
                    "phone": phone,
                    "notes": notes
                }
                
                # Generate payment link
                payment_url = generate_checkout_link(
                    amount=cost,
                    customer_email=email,
                    customer_name=name,
                    appointment_type=st.session_state.appointment_type,
                    metadata={
                        "phone": phone,
                        "appointment_time": st.session_state.selected_slot['start'],
                        "duration": duration,
                        "notes": notes
                    }
                )
                
                if payment_url:
                    st.session_state.payment_url = payment_url
                    st.session_state.booking_step = 3
                    st.rerun()
                else:
                    st.error("Failed to generate payment link. Please try again.")
    
    elif st.session_state.booking_step == 3:
        # Step 3: Payment and Confirmation
        st.write("### Complete Payment")
        st.write("""
        Please click the button below to complete your payment. After successful payment, 
        your appointment will be confirmed and you'll receive a confirmation email.
        
        Note: Please do not close this window until you complete the payment.
        """)
        
        # Display payment button
        payment_col1, payment_col2 = st.columns([1, 3])
        with payment_col1:
            st.link_button("Pay Now", st.session_state.payment_url, type="primary")
        
        # Add a button to confirm payment completion
        with payment_col2:
            if st.button("I've Completed the Payment"):
                # Create the appointment
                duration = (
                    datetime.fromisoformat(st.session_state.selected_slot['end']) -
                    datetime.fromisoformat(st.session_state.selected_slot['start'])
                ).total_seconds() / 60
                
                if create_confirmed_appointment(
                    st.session_state.selected_slot,
                    st.session_state.customer_details,
                    st.session_state.appointment_type,
                    int(duration)
                ):
                    st.success("""
                    ✅ Appointment Confirmed!
                    
                    A confirmation email has been sent to your email address.
                    You can close this window now.
                    """)
                    # Add a button to book another appointment
                    if st.button("Book Another Appointment"):
                        # Reset session state
                        for key in ['booking_step', 'selected_slot', 'customer_details', 'payment_url']:
                            if key in st.session_state:
                                del st.session_state[key]
                        st.rerun()
                else:
                    st.error("""
                    Failed to confirm appointment. Please contact support with your payment confirmation.
                    """)
        
        # Add option to go back
        if st.button("← Back"):
            st.session_state.booking_step = 2
            st.rerun()
    
    # Add navigation buttons
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.session_state.booking_step > 1:
            if st.button("← Back", key="back_main"):
                st.session_state.booking_step -= 1
                st.rerun()

if __name__ == "__main__":
    main() 