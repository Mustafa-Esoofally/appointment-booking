import streamlit as st
import os
from datetime import datetime, timedelta
from calendar_service import get_calendar_service, get_available_slots, create_appointment
from gmail_monitor import get_gmail_service, send_booking_link

def main():
    st.title("📅 Book Your Appointment")
    
    # Check if we have calendar service in session state
    if 'calendar_service' not in st.session_state or st.session_state.calendar_service is None:
        st.info("👋 Welcome to our appointment booking system!")
        st.warning("Please note that this is a direct booking link. If you received an email with a booking link, please use that instead.")
        
        if st.button("Go to Main Page"):
            st.switch_page("app.py")
        return
    
    # Appointment Booking Section
    st.header("Select Your Preferred Time")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Date selection
        selected_date = st.date_input(
            "Select Date",
            min_value=datetime.now().date(),
            max_value=(datetime.now() + timedelta(days=30)).date()
        )
        
        # Duration selection
        duration = st.selectbox(
            "Duration",
            options=[30, 60],
            format_func=lambda x: f"{x} minutes"
        )
        
        # Additional information
        st.info("""
        ℹ️ **Appointment Information**
        - Please select your preferred date and time
        - Standard appointments are 30 minutes
        - Extended consultations are 60 minutes
        - You'll receive a confirmation email once booked
        """)
    
    with col2:
        if selected_date:
            # Convert selected date to datetime
            start_date = datetime.combine(selected_date, datetime.min.time())
            end_date = datetime.combine(selected_date, datetime.max.time())
            
            # Get available slots
            available_slots = get_available_slots(
                st.session_state.calendar_service,
                start_date,
                end_date,
                duration
            )
            
            if available_slots:
                # Format slots for selection
                slot_options = {
                    f"{datetime.fromisoformat(slot['start']).strftime('%I:%M %p')} - {datetime.fromisoformat(slot['end']).strftime('%I:%M %p')}": slot
                    for slot in available_slots
                }
                
                selected_slot = st.selectbox(
                    "Available Time Slots",
                    options=list(slot_options.keys())
                )
                
                if selected_slot:
                    slot_data = slot_options[selected_slot]
                    
                    # Booking form
                    with st.form("booking_form"):
                        st.write("### Your Information")
                        name = st.text_input("Your Name")
                        email = st.text_input("Your Email")
                        description = st.text_area(
                            "Reason for Visit",
                            help="Please briefly describe the reason for your appointment"
                        )
                        
                        # Terms and conditions
                        st.write("### Terms & Conditions")
                        st.markdown("""
                        - 24-hour cancellation notice required
                        - Please arrive 5 minutes before your appointment
                        - Bring any relevant medical records
                        """)
                        
                        agree = st.checkbox("I agree to the terms and conditions")
                        
                        if st.form_submit_button("Book Appointment"):
                            if not (name and email and agree):
                                st.error("Please fill in all required fields and accept the terms")
                            else:
                                try:
                                    # Create appointment
                                    appointment = create_appointment(
                                        st.session_state.calendar_service,
                                        datetime.fromisoformat(slot_data['start']),
                                        datetime.fromisoformat(slot_data['end']),
                                        f"Appointment with {name}",
                                        description,
                                        email
                                    )
                                    
                                    if appointment:
                                        st.success("✅ Appointment booked successfully!")
                                        # Send confirmation email
                                        try:
                                            confirmation_message = f"""
                                            Your appointment has been confirmed!
                                            
                                            Details:
                                            Date: {selected_date}
                                            Time: {selected_slot}
                                            Duration: {duration} minutes
                                            
                                            Please remember:
                                            - Arrive 5 minutes early
                                            - Bring any relevant medical records
                                            - 24-hour cancellation notice required
                                            
                                            Thank you for booking with us!
                                            """
                                            send_booking_link(
                                                st.session_state.gmail_service,
                                                email,
                                                appointment['id'],
                                                confirmation_message
                                            )
                                            st.info("📧 Confirmation email sent!")
                                        except Exception as e:
                                            st.warning(f"Appointment booked but failed to send confirmation email: {str(e)}")
                                    else:
                                        st.error("Failed to book appointment")
                                except Exception as e:
                                    st.error(f"Error booking appointment: {str(e)}")
            else:
                st.info("No available slots for the selected date")
                st.write("Please try another date or duration")

if __name__ == "__main__":
    main() 