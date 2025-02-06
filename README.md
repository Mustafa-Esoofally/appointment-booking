# Email-Based Appointment Booking System

This project implements an automated appointment booking system that monitors Gmail for appointment requests and manages them using Google Calendar.

## Features

- Monitors Gmail for new appointment request emails
- Uses LangChain agents to process and understand email content
- Automatically sends booking links to users
- Integrates with Google Calendar for appointment management

## Prerequisites

1. Python 3.8 or higher
2. Google Cloud Project with Gmail and Calendar APIs enabled
3. OAuth 2.0 credentials from Google Cloud Console

## Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd appointment-booking
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up Google Cloud credentials:
   - Go to Google Cloud Console
   - Enable Gmail API and Google Calendar API
   - Create OAuth 2.0 credentials
   - Download the credentials and save as `credentials.json` in the project root

5. Create a `.env` file with the following variables:
```env
OPENAI_API_KEY=your_openai_api_key
BOOKING_APP_URL=your_booking_app_url
```

## Usage

1. Run the email monitoring service:
```bash
python src/main.py
```

2. The first time you run the script, it will open a browser window for Google OAuth authentication.

3. After authentication, the service will continuously monitor your Gmail for new appointment requests.

## How it Works

1. The service checks for new unread emails every 5 minutes
2. When a new email is found, the LangChain agent analyzes it to determine if it's an appointment request
3. If it is an appointment request, the system:
   - Checks calendar availability
   - Sends a booking link to the sender
   - Marks the email as read

## Development

- The main components are in the `src` directory:
  - `gmail_monitor.py`: Gmail integration
  - `calendar_service.py`: Google Calendar integration
  - `appointment_agent.py`: LangChain agent implementation
  - `main.py`: Main service runner

## Error Handling

- The service includes error handling and retry mechanisms
- If an error occurs while processing emails, it will wait 1 minute before retrying
- All errors are logged to the console

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request 