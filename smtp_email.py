"""SMTP delivery of the student's complete assessment report."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from dotenv import dotenv_values


def send_report_email(to_email, subject, body, deployment_settings=None):
    values = dotenv_values(Path(__file__).with_name('.env'))
    deployment_settings = deployment_settings or {}
    def setting(key, default=''):
        return str(deployment_settings.get(key) or os.getenv(key) or values.get(key) or default).strip()
    host = setting('SMTP_HOST')
    username = setting('SMTP_USERNAME')
    password = deployment_settings.get('SMTP_PASSWORD') or os.getenv('SMTP_PASSWORD') or values.get('SMTP_PASSWORD') or ''
    sender = setting('SMTP_FROM_EMAIL')
    if not all([host, username, password, sender]):
        return False, 'SMTP settings missing. Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD and SMTP_FROM_EMAIL in Streamlit Secrets or local .env.'
    try:
        port = int(setting('SMTP_PORT', '587'))
        if not 1 <= port <= 65535: raise ValueError()
    except ValueError:
        return False, 'SMTP_PORT must be a valid port number.'
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = to_email
    message.set_content(body)
    message.add_attachment(body.encode('utf-8'), maintype='text', subtype='plain', filename='complete_assessment_report.txt')
    try:
        context = ssl.create_default_context()
        if port == 465:
            connection = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
        else:
            connection = smtplib.SMTP(host, port, timeout=30)
        with connection as server:
            if port != 465:
                server.starttls(context=context)
            server.login(username, password)
            refused = server.send_message(message)
            if refused:
                return False, 'The mail server rejected the recipient. Your report remains available to download.'
        return True, 'Report accepted by the mail server for delivery.'
    except smtplib.SMTPAuthenticationError:
        return False, 'SMTP login failed. Check the username and SMTP/app password.'
    except (smtplib.SMTPException, OSError):
        return False, 'Email delivery could not be confirmed. Check your mail server logs before retrying.'
