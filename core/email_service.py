from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    app_password: str
    to_emails: List[str]
    timeout: int = 30
    use_starttls: bool = True
    reply_to: Optional[str] = None


def _split_emails(value: str) -> List[str]:
    """
    Aceita lista de emails no formato:
    - "a@x.com,b@y.com"
    - "a@x.com; b@y.com"
    """
    if not value:
        return []
    parts = value.replace(";", ",").split(",")
    return [p.strip() for p in parts if p.strip()]


def load_smtp_config_from_env() -> SmtpConfig:
    host = os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com").strip()
    port_str = os.getenv("GMAIL_SMTP_PORT", "587").strip()
    user = os.getenv("GMAIL_SMTP_USER", "").strip()
    app_password = os.getenv("GMAIL_SMTP_APP_PASSWORD", "").strip()

    # Destinatário: pode ser o mesmo do user ou lista separada por ; ou ,
    to_raw = os.getenv("ALERTS_TO_EMAIL", user).strip()
    to_emails = _split_emails(to_raw)

    # Opcionais
    timeout = int(os.getenv("GMAIL_SMTP_TIMEOUT", "30").strip())
    use_starttls = os.getenv("GMAIL_SMTP_STARTTLS", "1").strip() == "1"
    reply_to = os.getenv("GMAIL_SMTP_REPLY_TO", "").strip() or None

    # Validações
    errors = []
    if not host:
        errors.append("GMAIL_SMTP_HOST")
    if not port_str.isdigit():
        errors.append("GMAIL_SMTP_PORT inválido")
    if not user:
        errors.append("GMAIL_SMTP_USER")
    if not app_password:
        errors.append("GMAIL_SMTP_APP_PASSWORD")
    if not to_emails:
        errors.append("ALERTS_TO_EMAIL")

    if errors:
        raise RuntimeError(
            "Config SMTP incompleta/ inválida no .env. Verifique: " + ", ".join(errors)
        )

    return SmtpConfig(
        host=host,
        port=int(port_str),
        user=user,
        app_password=app_password,
        to_emails=to_emails,
        timeout=timeout,
        use_starttls=use_starttls,
        reply_to=reply_to,
    )


def build_email_message(
    subject: str,
    body_text: str,
    *,
    from_email: str,
    to_emails: Iterable[str],
    reply_to: Optional[str] = None,
    body_html: Optional[str] = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = ", ".join(list(to_emails))
    msg["Subject"] = subject

    if reply_to:
        msg["Reply-To"] = reply_to

    # Texto simples sempre
    msg.set_content(body_text)

    # HTML opcional
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    return msg


def send_email_smtp(subject: str, body_text: str) -> None:
    """
    Mantém compatibilidade com seu uso atual:
      send_email_smtp(subject, body)

    Internamente carrega configuração do .env e envia.
    """
    cfg = load_smtp_config_from_env()
    msg = build_email_message(
        subject=subject,
        body_text=body_text,
        from_email=cfg.user,
        to_emails=cfg.to_emails,
        reply_to=cfg.reply_to,
    )
    _send_message(cfg, msg)


def _send_message(cfg: SmtpConfig, msg: EmailMessage) -> None:
    try:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=cfg.timeout) as smtp:
            smtp.ehlo()

            if cfg.use_starttls:
                smtp.starttls()
                smtp.ehlo()

            smtp.login(cfg.user, cfg.app_password)
            smtp.send_message(msg)

    except smtplib.SMTPAuthenticationError as e:
        # não expor senha; só indicar que falhou autenticação
        raise RuntimeError(
            "Falha de autenticação SMTP. Verifique GMAIL_SMTP_USER e GMAIL_SMTP_APP_PASSWORD "
            "(senha de app)."
        ) from e

    except (
        smtplib.SMTPConnectError,
        smtplib.SMTPServerDisconnected,
        TimeoutError,
    ) as e:
        raise RuntimeError(
            f"Falha de conexão SMTP ({cfg.host}:{cfg.port}). Verifique rede/porta/firewall."
        ) from e

    except smtplib.SMTPException as e:
        raise RuntimeError(f"Erro SMTP ao enviar e-mail: {type(e).__name__}") from e
