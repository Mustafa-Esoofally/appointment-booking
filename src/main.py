import os
import time
import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

from appointment_agent import process_new_emails

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_service.log'),
        logging.StreamHandler()
    ]
)

# If modifying these scopes, delete the file token.json.
SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar'
]

def get_credentials():
    """Get valid user credentials from storage or user."""
    creds = None
    
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                creds = None
        
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return creds

def main():
    """Main function to run the appointment booking service."""
    logging.info("Starting appointment booking service...")
    check_interval = int(os.getenv('CHECK_INTERVAL_SECONDS', '300'))
    retry_interval = int(os.getenv('RETRY_INTERVAL_SECONDS', '60'))
    
    try:
        credentials = get_credentials()
        if not credentials:
            raise Exception("Failed to obtain valid credentials")
        
        while True:
            try:
                processed = process_new_emails(credentials)
                if processed > 0:
                    logging.info(f"Processed {processed} appointment requests")
                time.sleep(check_interval)
                
            except Exception as e:
                logging.error(f"Error processing emails: {str(e)}")
                time.sleep(retry_interval)
                credentials = get_credentials()  # Refresh credentials on error
                
    except KeyboardInterrupt:
        logging.info("Stopping appointment booking service...")
    except Exception as e:
        logging.error(f"Fatal error: {str(e)}")
        raise

if __name__ == "__main__":
    main() 