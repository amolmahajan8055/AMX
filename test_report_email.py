import json
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError
from report_email import send_report_email

class BrevoTests(unittest.TestCase):
    def test_success_and_payload(self):
        response=MagicMock(); response.__enter__.return_value.status=201
        with patch('report_email.dotenv_values',return_value={'BREVO_API_KEY':'test-key','BREVO_FROM_EMAIL':'sender@example.com'}), patch('report_email.os.getenv',return_value=None), patch('report_email.urlopen',return_value=response) as send:
            ok,message=send_report_email('candidate@example.com','Report','Full report')
            self.assertTrue(ok)
            request=send.call_args.args[0]
            self.assertEqual(request.full_url,'https://api.brevo.com/v3/smtp/email')
            self.assertEqual(json.loads(request.data)['textContent'],'Full report')
            self.assertEqual(json.loads(request.data)['to'],[{'email':'candidate@example.com'}])
    def test_missing_settings_does_not_send(self):
        with patch('report_email.dotenv_values',return_value={}),patch('report_email.os.getenv',return_value=None),patch('report_email.urlopen') as send:
            self.assertFalse(send_report_email('candidate@example.com','Report','Report')[0])
            send.assert_not_called()
    def test_errors_do_not_leak_credentials(self):
        for error in [HTTPError('url',401,'test-secret',None,None),HTTPError('url',429,'test-secret',None,None),URLError('test-secret')]:
            with patch('report_email.dotenv_values',return_value={'BREVO_API_KEY':'test-secret','BREVO_FROM_EMAIL':'sender@example.com'}),patch('report_email.os.getenv',return_value=None),patch('report_email.urlopen',side_effect=error):
                ok,message=send_report_email('candidate@example.com','Report','Report')
                self.assertFalse(ok)
                self.assertNotIn('test-secret',message)

if __name__=='__main__':unittest.main()
