import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tracker_security import TrackerStore
from streamlit.testing.v1 import AppTest

class TrackerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = TrackerStore(Path(self.folder.name)/'tracker.sqlite3')
        with self.store.connect() as db:
            for uid,role in [('admin','admin'),('aman','sales'),('sales02','sales')]:
                salt='01'*16
                db.execute('INSERT INTO users(id,name,role,salt,digest,referral) VALUES(?,?,?,?,?,?)',(uid,uid,role,salt,self.store.password_hash('test-password-123',salt),'ref-'+uid))
        self.admin=self.store.login('admin','test-password-123')
        self.aman=self.store.login('aman','test-password-123')
        self.other=self.store.login('sales02','test-password-123')
    def tearDown(self): self.folder.cleanup()
    def test_authentication_and_isolation(self):
        self.assertIsNone(self.store.login('aman','wrong'))
        self.assertIsNone(self.store.identity('forged-token'))
        own=self.store.submit({'candidate_name':'Own','student_mobile':'111'},referral='ref-aman')
        other=self.store.submit({'candidate_name':'Other','student_mobile':'222'},token=self.other)
        self.store.submit({'candidate_name':'Unassigned'})
        self.assertEqual([r['candidate_name'] for r in self.store.records(self.aman)],['Own'])
        self.assertEqual(len(self.store.records(self.admin)),3)
        with self.assertRaises(PermissionError): self.store.records(None)
        with self.assertRaises(PermissionError): self.store.update(self.aman,other,{'sales_notes':'overwrite'})
        with self.assertRaises(PermissionError): self.store.assign(self.aman,other,'aman')
        with self.assertRaises(ValueError): self.store.update(self.aman,own,{'owner':'sales02'})
        self.store.assign(self.admin,other,'aman')
        self.assertEqual(len(self.store.records(self.aman)),2)
        self.assertEqual(self.store.records(self.other),[])
    def test_password_reset_and_logout(self):
        with self.assertRaises(PermissionError): self.store.reset_password(self.aman,'sales02')
        password=self.store.reset_password(self.admin,'aman','Aman')
        self.assertIsNone(self.store.identity(self.aman))
        self.assertIsNone(self.store.login('aman','test-password-123'))
        token=self.store.login('aman',password)
        self.assertIsNotNone(token)
        self.store.logout(token)
        self.assertIsNone(self.store.identity(token))
    def test_legacy_is_admin_only_and_import_is_idempotent(self):
        csv=Path(self.folder.name)/'old.csv'
        csv.write_text('candidate_name,advisor_name\nLegacy,Aman\n')
        self.store.import_legacy(csv); self.store.import_legacy(csv)
        self.assertEqual(self.store.records(self.aman),[])
        self.assertEqual(len(self.store.records(self.admin)),1)
    def test_candidate_ui_has_no_private_controls_or_rows(self):
        self.store.submit({'candidate_name':'PRIVATE_OTHER_CANDIDATE','student_mobile':'SECRET_PHONE'},token=self.other)
        with patch('tracker_security.DB_PATH',self.store.path), patch.object(TrackerStore,'bootstrap'), patch.object(TrackerStore,'import_legacy'), patch.object(TrackerStore,'__init__',lambda obj: setattr(obj,'path',self.store.path)):
            app=AppTest.from_file('streamlit_app.py').run(timeout=30)
            self.assertFalse(app.exception)
            self.assertFalse(any(b.label.startswith('Sales Tracker') for b in app.button))
            self.assertFalse(any(b.label.endswith('CSV') for b in app.get('download_button')))
            self.assertFalse(any('PRIVATE_OTHER_CANDIDATE' in str(d.value) for d in app.dataframe))
            self.assertFalse(any('advisor_closure' in str(f.key) for f in app.get('form')))
    def test_staff_ui_sees_only_own_data(self):
        self.store.submit({'candidate_name':'Own','student_mobile':'111'},token=self.aman)
        self.store.submit({'candidate_name':'Other','student_mobile':'222'},token=self.other)
        with patch.object(TrackerStore,'bootstrap'), patch.object(TrackerStore,'import_legacy'), patch.object(TrackerStore,'__init__',lambda obj: setattr(obj,'path',self.store.path)):
            app=AppTest.from_file('streamlit_app.py')
            app.session_state['staff_token']=self.aman
            app.run(timeout=30)
            app.radio(key='workspace').set_value('Sales Tracker').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.dataframe[0].value['candidate_name'].tolist(),['Own'])
            self.assertNotIn('Account Management',app.radio(key='workspace').options)

    def test_session_expiry_and_lockout(self):
        import time, hashlib
        with self.store.connect() as db:
            db.execute('UPDATE sessions SET expires=? WHERE token=?',(time.time()-1,hashlib.sha256(self.aman.encode()).hexdigest()))
        self.assertIsNone(self.store.identity(self.aman))
        for _ in range(5): self.assertIsNone(self.store.login('sales02','wrong'))
        self.assertIsNone(self.store.login('sales02','test-password-123'))

    def test_admin_ui_sees_all_and_accounts(self):
        self.store.submit({'candidate_name':'Own'},token=self.aman)
        self.store.submit({'candidate_name':'Other'},token=self.other)
        with patch.object(TrackerStore,'bootstrap'), patch.object(TrackerStore,'import_legacy'), patch.object(TrackerStore,'__init__',lambda obj: setattr(obj,'path',self.store.path)):
            app=AppTest.from_file('streamlit_app.py')
            app.session_state['staff_token']=self.admin
            app.run(timeout=30)
            app.radio(key='workspace').set_value('Sales Tracker').run()
            self.assertFalse(app.exception)
            self.assertEqual(set(app.dataframe[0].value['candidate_name']),{'Own','Other'})
            app.radio(key='workspace').set_value('Account Management').run()
            self.assertFalse(app.exception)
            self.assertTrue(any(b.label=='Generate password' for b in app.button))

    def test_reminders_and_call_history_are_private(self):
        from datetime import date, timedelta
        today=date(2026,9,14)
        own=self.store.submit({'candidate_name':'Own','follow_up_frequency':'After 1 week','next_follow_up_date':today.isoformat()},token=self.aman)
        self.store.submit({'candidate_name':'Other','follow_up_frequency':'After 1 month','next_follow_up_date':today.isoformat()},token=self.other)
        self.store.submit({'candidate_name':'Tomorrow','follow_up_frequency':'After 1 week','next_follow_up_date':(today+timedelta(days=1)).isoformat()},token=self.aman)
        self.store.submit({'candidate_name':'None','follow_up_frequency':'No follow-up','next_follow_up_date':today.isoformat()},token=self.aman)
        self.assertEqual({r['candidate_name'] for r in self.store.reminders(self.aman,today)}, {'Own','Tomorrow'})
        with self.assertRaises(ValueError): self.store.update(self.aman,own,{'call_status':'Call completed','sales_notes':''})
        self.store.update(self.aman,own,{'call_status':'Call completed','sales_notes':'Discussed project plan','follow_up_frequency':'After 1 month','next_follow_up_date':today+timedelta(days=30)})
        self.assertEqual([r['candidate_name'] for r in self.store.reminders(self.aman,today)], ['Tomorrow'])
        row=next(r for r in self.store.records(self.aman) if r['record_id']==own)
        self.assertEqual(row['call_history'][0]['notes'],'Discussed project plan')
        self.assertEqual(row['call_history'][0]['sales_id'],'aman')
        self.store.update(self.aman,own,{'call_status':'Call completed','sales_notes':'No further calls needed','follow_up_frequency':'No follow-up','next_follow_up_date':today})
        row=next(r for r in self.store.records(self.aman) if r['record_id']==own)
        self.assertEqual(len(row['call_history']),2)
        self.assertEqual(row['next_follow_up_date'],'')

if __name__=='__main__': unittest.main()
