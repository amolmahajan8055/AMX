from contextlib import contextmanager
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

DB_PATH = Path(__file__).with_name('data') / 'private_tracker.sqlite3'
BOOTSTRAP_PATH = Path(__file__).with_name('data') / 'admin_setup.txt'

class TrackerStore:
    def __init__(self, path=DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, salt TEXT NOT NULL, digest TEXT NOT NULL, referral TEXT UNIQUE NOT NULL, failures INTEGER DEFAULT 0, locked_until REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, owner TEXT, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            ''')
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()
    @staticmethod
    def password_hash(password, salt):
        return hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    def bootstrap(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users LIMIT 1').fetchone(): return
            password = secrets.token_urlsafe(18)
            salt = secrets.token_hex(16)
            db.execute('INSERT INTO users(id,name,role,salt,digest,referral) VALUES(?,?,?,?,?,?)', ('admin','Administrator','admin',salt,self.password_hash(password,salt),secrets.token_urlsafe(24)))
            for i in range(1,11):
                uid = 'aman' if i == 1 else f'sales{i:02}'
                name = 'Aman' if i == 1 else f'Sales {i:02}'
                salt = secrets.token_hex(16)
                db.execute('INSERT INTO users(id,name,role,salt,digest,referral) VALUES(?,?,?,?,?,?)',(uid,name,'sales',salt,self.password_hash(secrets.token_urlsafe(24),salt),secrets.token_urlsafe(24)))
            BOOTSTRAP_PATH.write_text(f'CodeKerdos admin setup\nSales ID: admin\nPassword: {password}\n\nSign in, change the admin password, then remove this file. Generate the ten sales passwords in Account Management.\n',encoding='utf-8')
    def login(self, uid, password):
        uid = uid.strip().lower()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            user = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if not user:
                self.password_hash(password, '00'*16)
                return None
            if user['locked_until'] > time.time(): return None
            if not hmac.compare_digest(user['digest'],self.password_hash(password,user['salt'])):
                failures = user['failures']+1
                db.execute('UPDATE users SET failures=?,locked_until=? WHERE id=?',(failures,time.time()+300 if failures>=5 else 0,uid))
                return None
            db.execute('UPDATE users SET failures=0,locked_until=0 WHERE id=?',(uid,))
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+8*3600))
            return token
    def identity(self, token):
        if not token: return None
        with self.connect() as db:
            row = db.execute('SELECT u.id,u.name,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
            return dict(row) if row else None
    def require_staff(self, token, admin=False):
        user = self.identity(token)
        if not user or (admin and user['role']!='admin'): raise PermissionError('Staff access required')
        return user
    def logout(self, token):
        with self.connect() as db: db.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),))
    def accounts(self, token):
        self.require_staff(token,admin=True)
        with self.connect() as db: return [dict(r) for r in db.execute('SELECT id,name,role,referral FROM users ORDER BY id')]
    def reset_password(self, token, uid, name=None):
        self.require_staff(token,admin=True)
        password = secrets.token_urlsafe(18)
        self._set_password(uid,password,name)
        return password
    def change_password(self, token, password):
        user=self.require_staff(token)
        if len(password)<12: raise ValueError('Use at least 12 characters')
        self._set_password(user['id'],password)
    def _set_password(self, uid, password, name=None):
        salt=secrets.token_hex(16)
        with self.connect() as db:
            db.execute('UPDATE users SET salt=?,digest=?,name=COALESCE(?,name),failures=0,locked_until=0 WHERE id=?',(salt,self.password_hash(password,salt),name,uid))
            db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
    def referral(self, token):
        user=self.require_staff(token)
        with self.connect() as db: return db.execute('SELECT referral FROM users WHERE id=?',(user['id'],)).fetchone()[0]
    def owner_for_referral(self, referral):
        if not referral: return None
        with self.connect() as db:
            row=db.execute("SELECT id FROM users WHERE referral=? AND role='sales'",(referral,)).fetchone()
            return row[0] if row else None
    def submit(self, payload, token=None, referral=None):
        user=self.identity(token)
        owner=user['id'] if user and user['role']=='sales' else self.owner_for_referral(referral)
        record_id=secrets.token_urlsafe(24)
        with self.connect() as db: db.execute('INSERT INTO records VALUES(?,?,?)',(record_id,owner,json.dumps(payload,ensure_ascii=False)))
        return record_id
    def records(self, token):
        user=self.require_staff(token)
        with self.connect() as db:
            rows=db.execute('SELECT * FROM records' if user['role']=='admin' else 'SELECT * FROM records WHERE owner=?',() if user['role']=='admin' else (user['id'],)).fetchall()
            return [dict(json.loads(r['payload']),record_id=r['id'],sales_id=r['owner'] or 'Unassigned') for r in rows]
    def update(self, token, record_id, changes):
        user=self.require_staff(token)
        allowed={'advisor_name','lead_status','payment_status','follow_up_frequency','next_follow_up_date','call_conclusion','sales_notes','email_status','call_status'}
        if set(changes)-allowed: raise ValueError('Invalid record fields')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone()
            if not row or (user['role']!='admin' and row['owner']!=user['id']): raise PermissionError('Record access denied')
            payload=json.loads(row['payload'])
            changes = dict(changes)
            if 'next_follow_up_date' in changes:
                value = changes['next_follow_up_date']
                changes['next_follow_up_date'] = value.isoformat() if isinstance(value, date) else value
                if changes['next_follow_up_date']:
                    date.fromisoformat(changes['next_follow_up_date'])
            if changes.get('follow_up_frequency') == 'No follow-up':
                changes['next_follow_up_date'] = ''
            if changes.get('call_status') in {'Call completed', 'No answer', 'Rescheduled'} and not changes.get('sales_notes', '').strip():
                raise ValueError('Add the call outcome or update before saving')
            history = payload.get('call_history', [])
            history.append(dict(timestamp=datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(timespec='seconds'), sales_id=user['id'], executive=user['name'], status=changes.get('call_status','Follow-up scheduled / updated'), previous_follow_up=payload.get('next_follow_up_date',''), next_follow_up=changes.get('next_follow_up_date',payload.get('next_follow_up_date','')), notes=changes.get('sales_notes',''), lead_status=changes.get('lead_status',payload.get('lead_status',''))))
            payload.update(changes)
            payload['call_history'] = history
            db.execute('UPDATE records SET payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False,default=str),record_id))
    def reminders(self, token, today=None):
        today = today or datetime.now(ZoneInfo('Asia/Kolkata')).date()
        reminders = []
        for row in self.records(token):
            if not row.get('follow_up_frequency') or row.get('follow_up_frequency') == 'No follow-up':
                continue
            try:
                due = date.fromisoformat(str(row.get('next_follow_up_date', ''))[:10])
            except ValueError:
                continue
            if due <= today + timedelta(days=1):
                status = 'Overdue' if due < today else 'Today' if due == today else 'Tomorrow'
                reminders.append(dict(row, reminder_status=status))
        return sorted(reminders, key=lambda r: str(r['next_follow_up_date']))

    def assign(self, token, record_id, uid):
        self.require_staff(token,admin=True)
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM users WHERE id=? AND role='sales'",(uid,)).fetchone(): raise ValueError('Select a sales account')
            db.execute('UPDATE records SET owner=? WHERE id=?',(uid,record_id))
    def import_legacy(self, csv_path):
        import csv
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM settings WHERE key='legacy_import'").fetchone(): return
            if Path(csv_path).exists():
                with Path(csv_path).open(encoding='utf-8-sig',newline='') as handle:
                    for row in csv.DictReader(handle): db.execute('INSERT INTO records VALUES(?,?,?)',(secrets.token_urlsafe(24),None,json.dumps(row)))
            db.execute("INSERT INTO settings VALUES('legacy_import','done')")
