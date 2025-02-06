"""
Appointment Booking System package.
"""

from .appointment_agent import process_new_emails
from .calendar_service import get_calendar_service, get_available_slots, create_appointment
from .gmail_monitor import get_gmail_service, check_new_emails, send_booking_link, mark_as_read 

__version__ = "0.1.0" 