import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SENDER_EMAIL = "noreply@monetizeit.com" # TODO: Replace with your verified sender email

async def send_welcome_email(recipient_email: str, username: str):
    message = Mail(
        from_email=SENDER_EMAIL,
        to_emails=recipient_email,
        subject='Welcome to MonetizeIt!',
        html_content=f'''
        <strong>Hello {username},</strong>
        <p>Welcome to MonetizeIt! We're excited to have you on board.</p>
        <p>Start monetizing your APIs today!</p>
        <p>Best regards,<br>The MonetizeIt Team</p>
        '''
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Welcome email sent to {recipient_email}. Status Code: {response.status_code}")
    except Exception as e:
        print(f"Error sending welcome email to {recipient_email}: {e}")
