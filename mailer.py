import os
import smtplib
import ssl
from email.message import EmailMessage
import logging
import asyncio

logger = logging.getLogger("ceska_nadrz.mailer")

DEFAULT_TARGET_EMAILS = [
    "obchod@ceskanadrz.cz",
    "janhudak748@gmail.com",
]


def _smtp_settings():
    """Načíta SMTP nastavenia pri každom odoslaní (nie len pri importe modulu)."""
    host = os.getenv("SMTP_HOST", "").strip()
    port_raw = os.getenv("SMTP_PORT", "465").strip() or "465"
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASS", "").strip()
    from_email = os.getenv("FROM_EMAIL", user).strip() or user
    try:
        port = int(port_raw)
    except ValueError:
        logger.error("Neplatný SMTP_PORT=%r, používam 465", port_raw)
        port = 465
    targets_raw = os.getenv("LEAD_TARGET_EMAILS", "").strip()
    if targets_raw:
        targets = [e.strip() for e in targets_raw.split(",") if e.strip()]
    else:
        targets = list(DEFAULT_TARGET_EMAILS)
    return host, port, user, password, from_email, targets


def smtp_configured() -> bool:
    host, _, user, password, _, _ = _smtp_settings()
    return bool(host and user and password)


def format_history_to_text(chat_history: list) -> str:
    """Prevedie historiu konverzácie do čitateľného plain-text pre email."""
    if not chat_history:
        return "Historie konverzace je prázdná."

    lines = []
    for msg in chat_history:
        role = "Zákazník" if msg["role"] == "user" else "Asistent"
        content = msg["content"].replace("\n", " ")
        lines.append(f"[{role}]: {content}")

    return "\n".join(lines)


async def _send_smtp_email(subject: str, body: str, to_addresses: list):
    """Priame asynchrónne odoslanie emailu cez SMTP v executor thread."""
    smtp_host, smtp_port, smtp_user, smtp_pass, from_email, _ = _smtp_settings()
    if not smtp_host or not smtp_user or not smtp_pass:
        logger.warning(
            "SMTP údaje nie sú kompletne nastavené (SMTP_HOST/SMTP_USER/SMTP_PASS). "
            "Preskakujem odoslanie mailu: %s",
            subject,
        )
        return False

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = ", ".join(to_addresses)

    def send_sync():
        context = ssl.create_default_context()
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls(context=context)
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, send_sync)
        logger.info("E-mail [%s] bol úspešne odoslaný na: %s", subject, msg["To"])
        return True
    except Exception:
        logger.exception("Chyba pri odosielaní emailu cez SMTP (%s:%s)", smtp_host, smtp_port)
        return False


async def send_lead_email(lead_data: str, chat_history: list):
    """
    Odošle informáciu o novom leade spoločne s kompletnou históriou chatu.
    """
    _, _, _, _, _, target_emails = _smtp_settings()
    subject = "NOVÝ KONTAKT z Chatbota!"
    body = f"""Dobrý den,

chatbot na webu zaznamenal nový kontakt.

DETAILY KONTAKTU / POŽADAVEK:
-----------------------------------------
{lead_data}
-----------------------------------------

TRANSKRIPT CELÉ KONVERZACE:
-----------------------------------------
{format_history_to_text(chat_history)}
-----------------------------------------

(Tato zpráva je generována automaticky Česká Nádrž Botem.)
"""
    return await _send_smtp_email(subject, body, target_emails)
