import httpx
import os
import asyncio
import logging

logger = logging.getLogger("ceska_nadrz.alerter")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

async def send_discord_alert(error_message: str):
    """
    Odošle upozornenie na Discord webhook, ak je nastavený.
    """
    if not DISCORD_WEBHOOK_URL:
        return
        
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                DISCORD_WEBHOOK_URL,
                json={
                    "content": f"🚨 **Kritická chyba (Česká Nádrž Bot)** 🚨\n```\n{error_message}\n```"
                },
                timeout=10.0
            )
    except Exception as e:
        logger.error(f"Nepodarilo sa odoslať Discord alert: {e}")

def fire_alert(error_message: str):
    """
    Pomocná funkcia na bezpečné odpálenie alertu z bežného (aj synchrónneho) kódu.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(send_discord_alert(error_message))
    except RuntimeError: # Ak nebeží loop
        asyncio.run(send_discord_alert(error_message))
