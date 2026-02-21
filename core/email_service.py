from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage


def send_email_smtp(subject: str, body_text: str) -> None:
    host = os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("GMAIL_SMTP_PORT", "587"))
    user = os.getenv("GMAIL_SMTP_USER", "")
    app_password = os.getenv("GMAIL_SMTP_APP_PASSWORD", "")
    to_email = os.getenv("ALERTS_TO_EMAIL", user)

    if not user or not app_password or not to_email:
        raise RuntimeError("Credenciais/ALERTS_TO_EMAIL não configurados no .env")

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(user, app_password)
        smtp.send_message(msg)
