from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents import AgentExecutor, create_openai_functions_agent
from datetime import datetime
import os
import json
import logging
from pydantic import Field, BaseModel
import base64

from gmail_monitor import get_gmail_service, check_new_emails, send_booking_link, mark_as_read
from calendar_service import get_calendar_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('appointment_agent.log'),
        logging.StreamHandler()
    ]
)

BOOKING_APP_URL = os.getenv('BOOKING_APP_URL', 'http://localhost:3000/book')

class EmailAnalysisTool(BaseTool):
    name: str = "analyze_email"
    description: str = "Analyze email content to determine if it's an appointment request and its type."
    return_direct: bool = True
    
    def _run(self, content: str) -> Dict:
        """Analyze email content to determine if it's an appointment request."""
        content_lower = content.lower()
        
        # Keywords for different types of content
        keywords = {
            'appointment': ['appointment', 'book', 'schedule', 'meeting', 'consultation', 'visit'],
            'follow_up': ['follow', 'followup', 'follow-up', 'following up'],
            'consultation': ['consult', 'consultation', 'discuss', 'advice']
        }
        
        is_appointment = any(word in content_lower for word in keywords['appointment'])
        
        appointment_type = (
            'follow_up' if any(word in content_lower for word in keywords['follow_up'])
            else 'consultation' if any(word in content_lower for word in keywords['consultation'])
            else 'general'
        )
        
        return {
            "is_appointment": is_appointment,
            "type": appointment_type if is_appointment else "general"
        }
    
    def _arun(self, content: str):
        raise NotImplementedError("Async not implemented")

class SendBookingLinkTool(BaseTool):
    name: str = "send_booking_link"
    description: str = "Send booking link to user. Input: JSON with email, thread_id, and type."
    return_direct: bool = True
    
    def __init__(self, gmail_service):
        super().__init__(gmail_service=gmail_service)
        self._gmail_service = gmail_service
    
    def _run(self, data: str) -> bool:
        """Send booking link to the user."""
        try:
            data_dict = json.loads(data)
            appointment_type = data_dict.get('type', 'general')
            booking_link = f"{BOOKING_APP_URL}?type={appointment_type}"
            thread_id = data_dict.get('thread_id', '')
            
            # Create a personalized message based on appointment type
            subject = "Re: Schedule Your Appointment"
            if appointment_type == 'follow_up':
                message = f"""Thank you for requesting a follow-up appointment. I understand you'd like to schedule a follow-up visit.

Please use this personalized booking link to schedule your follow-up appointment:
{booking_link}

If you have any questions or need assistance, please don't hesitate to reply to this email.

Best regards,
Your Doctor's Office"""
            elif appointment_type == 'consultation':
                message = f"""Thank you for your interest in scheduling a consultation. We look forward to discussing your health concerns.

Please use this personalized booking link to schedule your consultation:
{booking_link}

If you have any specific concerns you'd like to discuss during the consultation, feel free to reply to this email.

Best regards,
Your Doctor's Office"""
            else:
                message = f"""Thank you for your interest in scheduling an appointment.

Please use this personalized booking link to schedule a time that works best for you:
{booking_link}

If you have any questions or need assistance, please don't hesitate to reply to this email.

Best regards,
Your Doctor's Office"""
            
            try:
                # Get the original message to properly set up threading
                original_message = self._gmail_service.users().messages().get(
                    userId='me',
                    id=thread_id,
                    format='metadata',
                    metadataHeaders=['Subject', 'Message-ID']
                ).execute()

                # Extract original subject and message ID
                original_subject = next((header['value'] for header in original_message.get('payload', {}).get('headers', []) 
                                      if header['name'].lower() == 'subject'), '')
                original_message_id = next((header['value'] for header in original_message.get('payload', {}).get('headers', []) 
                                         if header['name'].lower() == 'message-id'), '')

                # If original subject doesn't start with 'Re:', use it as is
                if not original_subject.lower().startswith('re:'):
                    subject = original_subject

                # Create message with proper threading headers
                message = {
                    'raw': base64.urlsafe_b64encode(
                        f'To: {data_dict["email"]}\n'
                        f'Subject: {subject}\n'
                        f'In-Reply-To: {original_message_id}\n'
                        f'References: {original_message_id}\n'
                        f'Content-Type: text/plain; charset="UTF-8"\n\n'
                        f'{message}'.encode()
                    ).decode(),
                    'threadId': thread_id
                }
                
                # Send reply
                sent_message = self._gmail_service.users().messages().send(
                    userId='me',
                    body=message
                ).execute()
                
                logging.info(f"Sent booking link reply in thread {thread_id}")
                return True
                
            except Exception as e:
                logging.error(f"Error sending reply: {str(e)}")
                return False
                
        except Exception as e:
            logging.error(f"Error in SendBookingLinkTool: {str(e)}")
            return False
    
    def _arun(self, data: str):
        raise NotImplementedError("Async not implemented")

def create_appointment_agent(gmail_service):
    """Create the appointment management agent."""
    try:
        if not os.getenv('OPENAI_API_KEY'):
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # Create LLM
        llm = ChatOpenAI(temperature=0, model="gpt-3.5-turbo")
        
        # Create tools
        tools = [
            EmailAnalysisTool(),
            SendBookingLinkTool(gmail_service)
        ]
        
        # Create prompt
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="""You are an AI medical appointment assistant. Your task is to analyze emails and identify appointment requests.

For each email:
1. First, use analyze_email to determine if it's an appointment request and get its type
2. Then, based on the analysis result:
   - If is_appointment is true:
     * Use send_booking_link with the data: {"email": sender_email, "thread_id": thread_id, "type": type}
     * After sending, respond with: {"action": "sent_link", "details": {"email": sender_email, "type": type}}
   - If is_appointment is false:
     * Respond with: {"action": "no_action", "details": {"email": sender_email, "type": "general"}}

Example 1 - Appointment Request:
Input: "Hi, I would like to schedule a consultation for next week."
1. analyze_email result: {"is_appointment": true, "type": "consultation"}
2. send_booking_link with: {"email": "patient@email.com", "thread_id": "123", "type": "consultation"}
3. Final response: {"action": "sent_link", "details": {"email": "patient@email.com", "type": "consultation"}}

Example 2 - Non-Appointment Email:
Input: "Thank you for the prescription refill."
1. analyze_email result: {"is_appointment": false, "type": "general"}
2. Final response: {"action": "no_action", "details": {"email": "patient@email.com", "type": "general"}}

You must ALWAYS:
1. Use analyze_email first
2. If it's an appointment request, use send_booking_link
3. Respond with the exact JSON format shown in the examples"""),
            HumanMessage(content="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        # Create agent
        agent = create_openai_functions_agent(llm=llm, tools=tools, prompt=prompt)
        
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True
        )
        
        def process_email(input_data: Dict) -> Dict:
            """Process a single email using the agent."""
            try:
                content = input_data.get('body', input_data.get('snippet', ''))
                headers = input_data.get('headers', {})
                
                # Extract sender email
                sender_email = headers.get('from_email', '')
                if not sender_email and 'from' in headers:
                    from_header = headers['from']
                    if '<' in from_header and '>' in from_header:
                        sender_email = from_header[from_header.find('<')+1:from_header.find('>')]
                    else:
                        sender_email = from_header.strip()

                if not sender_email:
                    return {'action': 'error', 'reason': 'Could not determine sender email'}

                # Format input for agent
                agent_input = f"""Process this email:
From: {sender_email}
Subject: {headers.get('subject', '')}
Content: {content}
Thread ID: {input_data.get('threadId', '')}"""

                # Execute agent
                result = agent_executor.invoke({"input": agent_input})
                
                # Process response
                if isinstance(result, dict) and 'output' in result:
                    response = result['output']
                    if isinstance(response, str):
                        try:
                            response = json.loads(response)
                        except json.JSONDecodeError:
                            # Create a default response based on the email analysis
                            analysis_result = tools[0]._run(content)
                            response = {
                                "action": "sent_link" if analysis_result['is_appointment'] else "no_action",
                                "details": {
                                    "email": sender_email,
                                    "type": analysis_result['type']
                                }
                            }
                    
                    # Ensure response is a dictionary if it's not already
                    if not isinstance(response, dict):
                        response = {
                            "action": "no_action",
                            "details": {
                                "email": sender_email,
                                "type": "general"
                            }
                        }
                    
                    # Ensure required fields
                    if 'action' not in response:
                        analysis_result = tools[0]._run(content)
                        response['action'] = "sent_link" if analysis_result['is_appointment'] else "no_action"
                    
                    if 'details' not in response:
                        response['details'] = {}
                    response['details']['email'] = sender_email
                    if 'type' not in response['details']:
                        response['details']['type'] = 'general'
                    
                    # If it's an appointment request, send the booking link
                    if response['action'] == 'sent_link':
                        booking_data = json.dumps({
                            'email': sender_email,
                            'thread_id': input_data.get('threadId', ''),
                            'type': response['details']['type']
                        })
                        # Use the SendBookingLinkTool from tools list
                        booking_tool = next(tool for tool in tools if isinstance(tool, SendBookingLinkTool))
                        if not booking_tool._run(booking_data):
                            response['action'] = 'error'
                            response['reason'] = 'Failed to send booking link'
                        else:
                            # Mark the email as read only if we successfully sent the reply
                            mark_as_read(gmail_service, input_data.get('id', ''))
                    
                    return response
                
                return {
                    "action": "error",
                    "reason": "Invalid agent response format",
                    "details": {"error": str(result)}
                }
                
            except Exception as e:
                logging.error(f"Error processing email: {str(e)}")
                return {'action': 'error', 'reason': str(e)}
        
        return process_email
    except Exception as e:
        logging.error(f"Error creating appointment agent: {str(e)}")
        raise

def process_new_emails(credentials):
    """Process new emails for appointment requests."""
    try:
        if not os.getenv('OPENAI_API_KEY'):
            logging.error("OPENAI_API_KEY environment variable is not set")
            return 0
        
        gmail_service = get_gmail_service(credentials)
        agent = create_appointment_agent(gmail_service)
        new_emails = check_new_emails(gmail_service)
        
        if not new_emails:
            logging.info("No new emails to process")
            return 0
        
        processed_count = 0
        for email in new_emails:
            try:
                result = agent(email)
                
                if result['action'] == 'sent_link':
                    # Send booking link
                    booking_data = {
                        'email': result['details']['email'],
                        'thread_id': email['threadId'],
                        'type': result['details'].get('type', 'general')
                    }
                    if send_booking_link(
                        gmail_service,
                        booking_data['email'],
                        booking_data['thread_id'],
                        f"{BOOKING_APP_URL}?type={booking_data['type']}"
                    ):
                        processed_count += 1
                        logging.info(f"Sent booking link to {booking_data['email']}")
                        mark_as_read(gmail_service, email['id'])
                
                elif result['action'] == 'no_action':
                    logging.info(f"No action needed for email from {result['details']['email']}")
                    mark_as_read(gmail_service, email['id'])
                
                elif result['action'] == 'error':
                    logging.error(f"Error processing email: {result.get('reason', 'Unknown error')}")
                    continue
                
            except Exception as e:
                logging.error(f"Error processing email {email.get('id', 'unknown')}: {str(e)}")
                continue
        
        return processed_count
    except Exception as e:
        logging.error(f"Error in process_new_emails: {str(e)}")
        return 0 