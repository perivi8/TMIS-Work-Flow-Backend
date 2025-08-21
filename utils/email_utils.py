import smtplib
from email.mime.text import MIMEText
from config import Config
from pymongo import MongoClient
from datetime import datetime
from typing import Optional, Dict, Any

# Reuse a single client
_client = MongoClient(Config.MONGO_URI)
_db = _client.EmployeeManagement
_email_collection = _db.email_notifications

def send_email(subject: str, recipient: str, body: str, meta: Optional[Dict[str, Any]] = None):
    # 1) Send via SMTP
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = Config.SMTP_USER
    msg['To'] = recipient

    server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
    server.ehlo()
    server.starttls()
    server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
    server.sendmail(Config.SMTP_USER, recipient, msg.as_string())
    server.quit()

    # 2) Log into Mongo for in-app display (with optional metadata)
    doc = {
        "from": Config.SMTP_USER,
        "recipient": recipient,
        "subject": subject,
        "message": body,
        "read": False,
        "timestamp": datetime.utcnow().isoformat()
    }
    if meta and isinstance(meta, dict):
        # flatten a few common meta keys at top-level for easy UI binding
        doc.update({
            "status": meta.get("status"),        # e.g., "In Progress" or "Done"
            "task_id": meta.get("task_id"),
            "title": meta.get("title"),
            "employee_id": meta.get("employee_id"),
            "username": meta.get("username"),
        })
        # also keep all meta in a nested field
        doc["meta"] = meta

    _email_collection.insert_one(doc)
