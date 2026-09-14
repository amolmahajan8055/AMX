"""Candidate report delivery through Brevo transactional email API."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from dotenv import dotenv_values


def send_report_email(to_email: str, subject: str, body: str):
    settings = dotenv_values(Path(__file__).with_name('.env'))
    def setting(key, default=''):
        return (os.getenv(key) or settings.get(key) or default).strip()
    api_key = setting('BREVO_API_KEY')
    sender = setting('BREVO_FROM_EMAIL')
    name = setting('BREVO_FROM_NAME', 'CodeKerdos')
    if not api_key or not sender:
        return False, 'Email is not configured yet. Your report is available to download. Ask the admin to configure Brevo.'
    if '@' not in sender or '@' not in to_email:
        return False, 'A valid sender and candidate email address are required.'
    payload = dict(sender=dict(name=name, email=sender), to=[dict(email=to_email)], subject=subject, textContent=body)
    request = Request('https://api.brevo.com/v3/smtp/email', data=json.dumps(payload).encode('utf-8'), headers={'api-key':api_key, 'Content-Type':'application/json', 'Accept':'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=30) as response:
            if response.status == 201:
                return True, 'Report accepted by Brevo for delivery. Check your inbox and spam folder.'
            return False, 'Brevo did not confirm the email. Check the sending logs before retrying.'
    except HTTPError as error:
        messages = {400:'Brevo rejected the email. Check the verified sender and recipient settings.',401:'Brevo authentication failed. Ask the admin to check the API key.',403:'Brevo blocked the request. Ask the admin to check account and sender permissions.',429:'Brevo sending limit reached. Try again later.'}
        return False, messages.get(error.code, 'Brevo could not send the report. Check the sending logs before retrying.')
    except (URLError, TimeoutError, OSError):
        return False, 'Email delivery could not be confirmed. Check Brevo sending logs before retrying.'
