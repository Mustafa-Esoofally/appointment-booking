from typing import List, Dict, Optional
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64
import os
import logging
import email

def get_gmail_service(credentials):
    """Create Gmail service instance."""
    return build('gmail', 'v1', credentials=credentials)

def extract_email_headers(headers: List[Dict]) -> Dict[str, str]:
    """Extract important headers from email."""
    header_map = {}
    for header in headers:
        name = header.get('name', '').lower()
        value = header.get('value', '')
        if name in ['from', 'to', 'subject', 'date']:
            # Extract email from "Name <email@domain.com>" format for 'from' and 'to'
            if name in ['from', 'to'] and '<' in value and '>' in value:
                header_map[f"{name}_name"] = value[:value.find('<')].strip()
                header_map[f"{name}_email"] = value[value.find('<')+1:value.find('>')]
            else:
                header_map[name] = value
    return header_map

def extract_email_body(payload: Dict) -> str:
    """Recursively extract email body from payload."""
    if 'body' in payload and 'data' in payload['body']:
        try:
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        except Exception as e:
            logging.error(f"Error decoding email body: {str(e)}")
            return ""
    
    if 'parts' in payload:
        text_content = ""
        html_content = ""
        
        for part in payload['parts']:
            mime_type = part.get('mimeType', '')
            if mime_type == 'text/plain':
                try:
                    if 'data' in part.get('body', {}):
                        text_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                except Exception as e:
                    logging.error(f"Error decoding text part: {str(e)}")
            elif mime_type == 'text/html':
                try:
                    if 'data' in part.get('body', {}):
                        html_content = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                except Exception as e:
                    logging.error(f"Error decoding HTML part: {str(e)}")
            elif mime_type.startswith('multipart/'):
                # Recursively process multipart messages
                text_content = extract_email_body(part)
        
        # Prefer plain text over HTML
        return text_content or html_content or ""
    
    return ""

def check_new_emails(service, query: str = "is:unread") -> List[Dict]:
    """Check for new unread emails that might contain appointment requests."""
    try:
        results = service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        email_data = []
        
        for message in messages:
            try:
                msg = service.users().messages().get(userId='me', id=message['id']).execute()
                headers = msg.get('payload', {}).get('headers', [])
                header_data = extract_email_headers(headers)
                
                # Get email body
                payload = msg.get('payload', {})
                body = extract_email_body(payload)
                
                if not body:
                    body = msg.get('snippet', '')
                
                email_data.append({
                    'id': msg['id'],
                    'threadId': msg['threadId'],
                    'snippet': msg['snippet'],
                    'body': body,
                    'headers': header_data,
                    'labels': msg.get('labelIds', [])
                })
            except Exception as e:
                logging.error(f"Error processing individual email {message['id']}: {str(e)}")
                continue
        
        return email_data
    except Exception as e:
        logging.error(f"Error checking emails: {str(e)}")
        return []

def send_booking_link(service, to: str, thread_id: str, booking_link: str, subject: str = None, message: str = None) -> bool:
    """Send a response email with the booking link."""
    try:
        # Create message container
        message_obj = MIMEMultipart('alternative')
        
        # Use provided message or default template
        if message is None:
            text_content = f"""
Dear Patient,

Thank you for your interest in booking an appointment!

Please use the following link to schedule your appointment:
{booking_link}

If you have any questions or need assistance, please don't hesitate to reply to this email.

Best regards,
Doctor's Office
"""
        else:
            text_content = message

        # Create HTML version by converting plain text to HTML
        paragraphs = text_content.split('\n\n')
        html_content = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
"""
        
        for p in paragraphs:
            if p.strip():
                # Replace the booking link with an HTML link
                if booking_link in p:
                    p = p.replace(booking_link, f'<a href="{booking_link}" style="color: #007bff;">{booking_link}</a>')
                # Convert newlines to <br> tags
                p = p.replace('\n', '<br>')
                html_content += f'    <p>{p}</p>\n'
        
        html_content += "</div>"
        
        # Attach parts
        part1 = MIMEText(text_content, 'plain')
        part2 = MIMEText(html_content, 'html')
        message_obj.attach(part1)
        message_obj.attach(part2)
        
        # Add headers
        message_obj['to'] = to
        message_obj['from'] = 'me'  # 'me' is a special value that represents the authenticated user
        message_obj['subject'] = subject or 'Your Appointment Booking Link'
        message_obj['In-Reply-To'] = thread_id
        message_obj['References'] = thread_id
        
        # Create the raw email
        raw = base64.urlsafe_b64encode(message_obj.as_bytes()).decode('utf-8')
        
        # Send the email
        sent_message = service.users().messages().send(
            userId='me',
            body={
                'raw': raw,
                'threadId': thread_id
            }
        ).execute()
        
        logging.info(f"Sent booking link email to {to} with message ID: {sent_message.get('id')}")
        return True
        
    except Exception as e:
        logging.error(f"Error sending booking link email to {to}: {str(e)}")
        return False

def mark_as_read(service, message_id: str) -> bool:
    """Mark an email as read."""
    try:
        # First, get the current labels
        msg = service.users().messages().get(userId='me', id=message_id).execute()
        current_labels = msg.get('labelIds', [])
        
        # Remove UNREAD label if present
        if 'UNREAD' in current_labels:
            service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            logging.info(f"Marked message {message_id} as read")
        return True
    except Exception as e:
        logging.error(f"Error marking message {message_id} as read: {str(e)}")
        return False 