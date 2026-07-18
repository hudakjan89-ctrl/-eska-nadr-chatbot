import httpx
import os
import asyncio
import logging
import time

logger = logging.getLogger("ceska_nadrz.alerter")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "900"))

_last_alerts: dict[str, float] = {}


async def send_discord_alert(error_message: str):
    """Odošle upozornenie na Discord webhook, ak je nastavený."""
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


def _alert_key(error_message: str) -> str:
    text = (error_message or "").lower()
    if "llm api error 503" in text or "no upstream provider" in text:
        return "llm_upstream_unavailable"
    if "llm api error 502" in text or "llm api error 529" in text:
        return "llm_upstream_bad_gateway"
    if "llm api error 429" in text:
        return "llm_rate_limited"
    if "timeout" in text or "transport" in text:
        return "llm_network"
    return (error_message or "unknown")[:160]


def fire_alert(error_message: str, *, force: bool = False):
    """Bezpečne odpáli Discord alert s cooldownom proti spamu."""
    key = _alert_key(error_message)
    now = time.time()
    if not force and key in _last_alerts and now - _last_alerts[key] < ALERT_COOLDOWN_SECONDS:
        logger.warning("Discord alert suppressed (cooldown %ss): %s", ALERT_COOLDOWN_SECONDS, key)
        return

    _last_alerts[key] = now
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(send_discord_alert(error_message))
    except RuntimeError:
        asyncio.run(send_discord_alert(error_message))
