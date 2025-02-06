from typing import Dict, Optional
import os
import logging
from paymanai import Paymanai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('payment_service.log'),
        logging.StreamHandler()
    ]
)

# Initialize Payman client
client = Paymanai(
    x_payman_api_secret=os.getenv('PAYMAN_API_KEY'),
    environment="sandbox"  # Use "production" for live transactions
)

def generate_checkout_link(
    amount: float,
    customer_email: str,
    customer_name: str,
    appointment_type: str,
    metadata: Optional[Dict[str, any]] = None
) -> Optional[str]:
    """
    Generate a checkout URL for appointment payment.
    
    Args:
        amount: The payment amount in dollars
        customer_email: Customer's email address
        customer_name: Customer's name
        appointment_type: Type of appointment (follow_up, consultation, general)
        metadata: Additional metadata for the payment
    
    Returns:
        str: Checkout URL if successful, None otherwise
    """
    try:
        # Generate a unique customer ID based on email
        customer_id = f"cust_{hash(customer_email)}"
        
        # Default metadata if none provided
        if metadata is None:
            metadata = {}
        
        # Add appointment-specific metadata
        metadata.update({
            'appointment_type': appointment_type,
            'source': 'appointment_booking'
        })
        
        # Create checkout session
        response = client.payments.initiate_customer_deposit(
            amount_decimal=amount,
            customer_id=customer_id,
            customer_email=customer_email,
            customer_name=customer_name,
            memo=f"{appointment_type.replace('_', ' ').title()} Appointment Payment",
            fee_mode='ADD_TO_AMOUNT',  # Customer pays fees
            metadata=metadata
        )
        
        logging.info(f"Generated checkout URL for {customer_email} - Amount: ${amount}")
        return response.checkout_url
        
    except Exception as e:
        logging.error(f"Error generating checkout link: {str(e)}")
        return None

def get_appointment_cost(appointment_type: str, duration: int) -> float:
    """
    Calculate appointment cost based on type and duration.
    
    Args:
        appointment_type: Type of appointment (follow_up, consultation, general)
        duration: Duration in minutes
    
    Returns:
        float: Cost in dollars
    """
    # Base rates per hour
    base_rates = {
        'consultation': 200.00,  # $200/hour for consultations
        'follow_up': 150.00,    # $150/hour for follow-ups
        'general': 100.00       # $100/hour for general appointments
    }
    
    # Get base rate for appointment type
    hourly_rate = base_rates.get(appointment_type, base_rates['general'])
    
    # Calculate cost based on duration
    cost = (hourly_rate / 60) * duration
    
    return round(cost, 2)  # Round to 2 decimal places 