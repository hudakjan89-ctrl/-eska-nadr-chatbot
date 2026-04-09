import os
import smtplib
import ssl
from email.message import EmailMessage
import logging
import asyncio

logger = logging.getLogger("ceska_nadrz.mailer")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

# E-mailová adresa, z ktorej sa budú odosielať správy
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

# Primárne cieľové maily, kam sa leads doručia (oddelme ich v texte alebo kódom)
TARGET_EMAILS = [
    "obchod@ceskanadrz.cz",
    # Sem si neskôr doplňte ten váš testovací mail napr: "moj-testovaci@email.cz"
]

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
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        logger.warning(f"SMTP údaje nie sú kompletne nastavené v ENVs. Preskakujem odoslanie mailu: {subject}")
        return

    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = FROM_EMAIL
    msg["To"] = ", ".join(to_addresses)

    def send_sync():
        context = ssl.create_default_context()
        try:
            if SMTP_PORT == 465:
                # SSL
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
                    server.login(SMTP_USER, SMTP_PASS)
                    server.send_message(msg)
            else:
                # TLS
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                    server.starttls(context=context)
                    server.login(SMTP_USER, SMTP_PASS)
                    server.send_message(msg)
            logger.info(f"E-mail [{subject}] bol úspešne odoslaný na: {msg['To']}")
        except Exception as e:
            logger.exception(f"Chyba pri odosielaní emailu cez SMTP: {e}")

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, send_sync)


def send_lead_email(lead_data: str, chat_history: list):
    """
    Odošle informáciu o novom leade spoločne s kompletnou históriou chatu.
    """
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
    
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send_smtp_email(subject, body, TARGET_EMAILS))
    except RuntimeError:
        asyncio.run(_send_smtp_email(subject, body, TARGET_EMAILS))
