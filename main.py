import os
import sys
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import uuid
import httpx
import asyncio
import unicodedata
import re
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from xml_parser import fetch_and_parse_xml
from database import (
    upsert_products, search_products, search_knowledge, expand_search_query,
    is_product_index_ready, product_count,
)
from knowledge_github import load_knowledge_on_startup, is_github_configured, github_token_hint, sync_knowledge_base
from admin import router as admin_router, refresh_dashboard_cache
from logger import (
    log_message, log_event, emit_event, build_user_hash,
    DB_PATH, session_has_messages, session_has_event, load_session_messages, load_recommended_urls,
)
from alerter import fire_alert
from mailer import send_lead_email, resend_configured, smtp_configured, discord_configured

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ceska_nadrz.main")

LLM_API_BASE_URL = os.getenv("LLM_API_BASE_URL", "https://api.eurouter.ai/api/v1").rstrip("/")
LLM_API_KEY = os.getenv("EUROUTER_API_KEY") or os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL", "claude-opus-4-7")
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "").strip()
LLM_CHAT_URL = f"{LLM_API_BASE_URL}/chat/completions"
LLM_RETRY_ATTEMPTS = int(os.getenv("LLM_RETRY_ATTEMPTS", "4"))
LLM_RETRYABLE_STATUS_CODES = {429, 502, 503, 529}
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

WIDGET_VERSION = "9.4.16"
STATIC_DIR = Path(__file__).resolve().parent / "static"
WIDGET_PUBLIC_BASE = os.getenv("WIDGET_PUBLIC_BASE", "https://nadrz.eniq.eu").rstrip("/")
WIDGET_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "CDN-Cache-Control": "no-store",
    "Surrogate-Control": "no-store",
}


def _widget_asset_headers(extra: Optional[dict] = None) -> dict:
    headers = dict(WIDGET_NO_CACHE_HEADERS)
    headers["X-Widget-Version"] = WIDGET_VERSION
    if extra:
        headers.update(extra)
    return headers


def _read_widget_asset(path: Path) -> bytes:
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Widget asset missing: {path.name}")
    return path.read_bytes()


app = FastAPI()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(admin_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/chat-widget.js", include_in_schema=False)
async def widget_embed_js():
    """Hlavná embed URL — servuje celý widget priamo (nie loader)."""
    return Response(
        content=_read_widget_asset(STATIC_DIR / "js" / "chat.js"),
        media_type="application/javascript",
        headers=_widget_asset_headers(),
    )


@app.get("/static/js/chat.js", include_in_schema=False)
async def widget_chat_legacy():
    return Response(
        content=_read_widget_asset(STATIC_DIR / "js" / "chat.js"),
        media_type="application/javascript",
        headers=_widget_asset_headers(),
    )


@app.get("/widget/style.css", include_in_schema=False)
async def widget_style_current():
    return Response(
        content=_read_widget_asset(STATIC_DIR / "css" / "style.css"),
        media_type="text/css",
        headers=_widget_asset_headers(),
    )


@app.get("/widget/{version}/chat.js", include_in_schema=False)
async def widget_core_js(version: str):
    """Akákoľvek verzia — vždy servuje aktuálny widget (spätná kompatibilita s cache)."""
    return Response(
        content=_read_widget_asset(STATIC_DIR / "js" / "chat.js"),
        media_type="application/javascript",
        headers=_widget_asset_headers({"X-Widget-Requested-Version": version}),
    )


@app.get("/widget/{version}/style.css", include_in_schema=False)
async def widget_core_css(version: str):
    return Response(
        content=_read_widget_asset(STATIC_DIR / "css" / "style.css"),
        media_type="text/css",
        headers=_widget_asset_headers({"X-Widget-Requested-Version": version}),
    )


BOT_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<circle cx="32" cy="32" r="30" fill="#ffffff"/>'
    '<path fill="#005b9f" d="M32 14c8 12 16 20 16 28a16 16 0 0 1-32 0c0-8 8-16 16-28z"/>'
    "</svg>"
)


@app.get("/static/img/bot.svg", include_in_schema=False)
async def widget_bot_svg():
    icon_path = STATIC_DIR / "img" / "bot.svg"
    if icon_path.is_file():
        return FileResponse(icon_path, media_type="image/svg+xml", headers=_widget_asset_headers())
    return Response(
        content=BOT_ICON_SVG.encode("utf-8"),
        media_type="image/svg+xml",
        headers=_widget_asset_headers(),
    )


@app.get("/static/img/bot.png", include_in_schema=False)
async def widget_bot_icon():
    icon_path = STATIC_DIR / "img" / "bot.png"
    if icon_path.is_file():
        return FileResponse(icon_path, media_type="image/png", headers=_widget_asset_headers())
    return Response(
        content=BOT_ICON_SVG.encode("utf-8"),
        media_type="image/svg+xml",
        headers=_widget_asset_headers(),
    )


@app.get("/static/css/style.css", include_in_schema=False)
async def widget_style_css_legacy():
    return Response(
        content=_read_widget_asset(STATIC_DIR / "css" / "style.css"),
        media_type="text/css",
        headers=_widget_asset_headers(),
    )


@app.get("/widget/manifest.json", include_in_schema=False)
async def widget_manifest():
    return JSONResponse(
        {
            "version": WIDGET_VERSION,
            "css": f"/widget/style.css",
            "js": f"/chat-widget.js",
            "bootstrap": "/chat-widget.js",
        "embed_recommended": f"{WIDGET_PUBLIC_BASE}/chat-widget.js",
        },
        headers=WIDGET_NO_CACHE_HEADERS,
    )


@app.get("/widget/debug", include_in_schema=False)
async def widget_debug():
    chat_bytes = _read_widget_asset(STATIC_DIR / "js" / "chat.js")
    css_bytes = _read_widget_asset(STATIC_DIR / "css" / "style.css")
    return {
        "widget_version": WIDGET_VERSION,
        "chat_js_bytes": len(chat_bytes),
        "css_bytes": len(css_bytes),
        "chat_js_preview": chat_bytes[:120].decode("utf-8", errors="replace"),
        "css_preview": css_bytes[:120].decode("utf-8", errors="replace"),
        "premium_css": b"Premium edition" in css_bytes,
        "premium_js": b"invitePopup" in chat_bytes,
        "embed_use_this": f"{WIDGET_PUBLIC_BASE}/chat-widget.js",
        "embed_ok_if_premium": (b"Premium edition" in css_bytes and b"invitePopup" in chat_bytes),
    }


img_dir = STATIC_DIR / "img"
if img_dir.is_dir():
    app.mount("/static/img", StaticFiles(directory=str(img_dir)), name="static-img")

sessions = {}
recommended_urls = {}  # session_id -> list of already recommended product URLs


def ensure_session_loaded(session_id: str) -> None:
    """Po redeployi obnoví konverzáciu a odporúčané URL zo SQLite."""
    if session_id not in sessions:
        sessions[session_id] = load_session_messages(session_id)
    if session_id not in recommended_urls:
        recommended_urls[session_id] = load_recommended_urls(session_id)

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=500)
    session_id: Optional[str] = None
    language: Optional[str] = "cs"
    page_url: Optional[str] = None
    page_path: Optional[str] = None
    page_title: Optional[str] = None
    referrer: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    session_id: str
    page_section: Optional[str] = None
    image_url: Optional[str] = None
    show_contact_form: bool = False

def remove_diacritics(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

URL_MAP = {
    "https://www.ceskanadrz.cz/10m3-nadrz-na-vodu-set-zahrada-standard/":["10m3", "10 kubiku", "10 kubikov", "deset kubiku", "10000", "set zahrada", "zahrada standard"],
    "https://www.ceskanadrz.cz/1m3-kruhova-nadrz-na-vodu-k-obetonovani/":["1m3", "1 kubik", "mala nadrz", "kruhova nadrz 1m3"],
    "https://www.ceskanadrz.cz/sachta-na-vrt-mini-k-obetonovani-2/":["mini sachta", "sachta mini", "mini sachtu"],
    "https://www.ceskanadrz.cz/cisticka-odpadnich-vod-pro-2-5-osob-at6/":["at6", "pro 2", "pro 5", "pro 4", "cisticka at6"],
    "https://www.ceskanadrz.cz/nadrze-na-pitnou-vodu-k-obetonovani/":["pitnou vodu k obetonovani", "pitna voda k obetonovani"],
    "https://www.ceskanadrz.cz/dvouplastove-nadrze-na-pitnou-vodu/":["dvouplastove na pitnou", "dvouplastova na pitnou"],
    "https://www.ceskanadrz.cz/odlucovace-tuku-k-obetonovani/":["odlucovace k obetonovani", "odlucovac tuku k obetonovani"],
    "https://www.ceskanadrz.cz/dvouplastove-odlucovace-tuku/":["dvouplastove odlucovace", "dvouplastovy odlucovac"],
    "https://www.ceskanadrz.cz/samonosne-odlucovace-tuku/":["samonosne odlucovace", "samonosny odlucovac"],
    "https://www.ceskanadrz.cz/pozarni-a-retencni-nadrze-k-obetonovani/":["pozarni k obetonovani", "retencni k obetonovani"],
    "https://www.ceskanadrz.cz/dvouplastove-pozarni-a-retencni-nadrze/":["dvouplastove pozarni", "dvouplastove retencni"],
    "https://www.ceskanadrz.cz/samonosne-pozarni-a-retencni-nadrze/":["samonosne pozarni", "samonosne retencni"],
    "https://www.ceskanadrz.cz/nadrze-na-destovou-vodu/":["destovou vodu", "na destovku", "nadrze na destovku", "na zalevani", "podzemni destovka", "podzemni nadrz na destovku"],
    "https://www.ceskanadrz.cz/nadrze-na-vodu-k-obetonovani/":["nadrze k obetonovani", "nadrz k obetonovani", "obetonovani", "podzemni", "pod zem", "do zeme", "podzemni nadrz", "samonosna nadrz"],
    "https://www.ceskanadrz.cz/sachty-na-vrt/":["sachty na vrt", "sachtu na vrt", "na vrt"],
    "https://www.ceskanadrz.cz/precerpavaci-jimky-k-obetonovani/":["precerpavaci jimka k obetonovani"],
    "https://www.ceskanadrz.cz/precerpavaci-jimky/":["precerpavaci", "precerpavack"],
    "https://www.ceskanadrz.cz/cistirny-odpadnich-vod/":["cistirn", "cistick", "cov", "odpadnich vod", "odpadni vody"],
    "https://www.ceskanadrz.cz/jimky/":["jimky", "jimka", "zumpa", "zumpu"],
    "https://www.ceskanadrz.cz/septiky/":["septiky", "septik", "septik"],
    "https://www.ceskanadrz.cz/vodomerne-sachty/":["vodomerne sachty", "vodomerna sachta", "na vodomer"],
    "https://www.ceskanadrz.cz/prislusenstvi-k-nadrzim/":["prislusenstvi", "doplnky", "poklop", "poklopy"],
    "https://www.ceskanadrz.cz/vsakovani/":["vsakovani", "vsakovaci", "vsak"],
    "https://www.ceskanadrz.cz/dotace-destovka/":["dotace", "destovka dotace", "vyrizeni dotace"],
    "https://www.ceskanadrz.cz/zemni-piskove-filtry/":["piskove filtry", "zemni piskove", "piskovy filtr"],
    "https://www.ceskanadrz.cz/nadrze-na-pitnou-vodu/":["na pitnou vodu", "pitna voda"],
    "https://www.ceskanadrz.cz/kanalizacni-revizni-odberna-sachta/":["kanalizacni sachta", "revizni sachta", "odberna sachta"],
    "https://www.ceskanadrz.cz/technologicke-sachty/":["technologicke sachty", "technologicka sachta"],
    "https://www.ceskanadrz.cz/ukapove-vany/":["ukapove vany", "ukapova vana"],
    "https://www.ceskanadrz.cz/vyrobky-na-miru/":["na miru", "zakazkov", "atyp"],
    "https://www.ceskanadrz.cz/doprava-platba/":["doprava", "platba", "jak platit", "cena dopravy", "rozvoz", "dobirkou"],
    "https://www.ceskanadrz.cz/obchodni-podminky/":["obchodni podminky", "reklamace", "smlouva"],
    "https://www.ceskanadrz.cz/podminky-ochrany-osobnich-udaju/":["gdpr", "osobni udaje", "ochrana"],
    "https://www.ceskanadrz.cz/poradna-nadrze--jimky--sachty-/":["poradna", "jak vybrat", "rady"],
    "https://www.ceskanadrz.cz/casto-kladene-otazky-faq/":["faq", "casto kladene otazky", "caste dotazy"],
    "https://www.ceskanadrz.cz/o-nas/":["o nas", "kdo jste", "informace o firme", "historie", "zkusenosti", "spolecnost"]
}

def detect_page_section(message: str) -> Optional[str]:
    msg_clean = remove_diacritics(message.lower())
    for url, terms in URL_MAP.items():
        if any(term in msg_clean for term in terms):
            return url
    return None

URL_TAG_RE = re.compile(r'\[\s*URL\s*:\s*(https?://[^\s\]]+)\s*\]?', re.IGNORECASE)
PRODUCT_MATCH_STOPWORDS = {
    "pro", "bez", "pod", "nad", "k", "ke", "na", "do", "od", "a", "i", "s", "se", "ve", "v",
    "the", "and", "for", "with"
}

def extract_hidden_url_tag(message: str):
    match = URL_TAG_RE.search(message)
    if not match:
        cleaned = re.sub(r'\[\s*URL\s*:[^\]]*\]?', '', message, flags=re.IGNORECASE).strip()
        return None, cleaned

    url = match.group(1).rstrip('.,;')
    cleaned = URL_TAG_RE.sub('', message).strip()
    return url, cleaned

def normalize_product_match_text(text: str) -> str:
    text = remove_diacritics((text or "").lower())
    text = text.replace("m³", "m3")
    text = re.sub(r'(\d+)\s*m\s*3', r'\1 m3', text)
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return " ".join(text.split())

def product_match_score(product: dict, assistant_message: str) -> int:
    product_text = normalize_product_match_text(product.get("name", ""))
    message_text = normalize_product_match_text(assistant_message)
    if not product_text or not message_text:
        return 0

    product_numbers = set(re.findall(r'\d+', product_text))
    message_numbers = set(re.findall(r'\d+', message_text))
    if product_numbers and not product_numbers.intersection(message_numbers):
        return 0

    product_stems = {
        word[:4]
        for word in product_text.split()
        if len(word) > 2 and word not in PRODUCT_MATCH_STOPWORDS and not word.isdigit()
    }
    message_stems = {
        word[:4]
        for word in message_text.split()
        if len(word) > 2 and word not in PRODUCT_MATCH_STOPWORDS and not word.isdigit()
    }

    score = len(product_stems.intersection(message_stems))
    score += 3 * len(product_numbers.intersection(message_numbers))
    if "m3" in product_text and "m3" in message_text:
        score += 1
    return score

def find_product_by_url(products: list, url: str):
    return next((p for p in products if p.get("url") == url), None)

def resolve_mentioned_product(products: list, assistant_message: str, detected_url: Optional[str]):
    if not products:
        return None

    best_product = None
    best_score = 0
    for product in products:
        score = product_match_score(product, assistant_message)
        if score > best_score:
            best_product = product
            best_score = score

    current_product = find_product_by_url(products, detected_url) if detected_url else None
    current_score = product_match_score(current_product, assistant_message) if current_product else 0

    if best_product and best_score >= 5 and best_score > current_score:
        return best_product
    return current_product

async def update_database_task():
    try:
        logger.info("Vykonavam planovanu ulohu update_database_task...")
        products = await fetch_and_parse_xml()
        if products:
            logger.info(f"Nacitanych {len(products)} produktov, ukladám do DB (v samostatnom vlákne)...")
            await asyncio.to_thread(upsert_products, products)
            logger.info("Produktový index pripravený (%d položiek).", product_count())
        else:
            logger.warning("Ziadne produkty stiahnute z XML (prazdny zoznam).")

        logger.info("Uloha update_database_task dokoncena uspesne.")
    except Exception as e:
        logger.exception("Kriticka chyba v opakovanej ulohe update_database_task!")
        fire_alert(f"Zlyhal update_database_task feed!\nChyba: {str(e)}")


async def sync_knowledge_task():
    try:
        sections = await asyncio.to_thread(sync_knowledge_base, is_github_configured())
        logger.info("Knowledge sync dokončený (%d sekcí).", sections)
    except Exception as e:
        logger.exception("Knowledge sync zlyhal: %s", e)
        fire_alert(f"Zlyhal sync knowledge base!\nChyba: {str(e)}")


async def purge_cloudflare_widget_cache():
    """Po redeployi vymaže Cloudflare cache widgetu — zákazník nemusí nič meniť."""
    zone_id = os.getenv("CLOUDFLARE_ZONE_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    if not zone_id or not api_token:
        logger.info(
            "Cloudflare purge preskočený (CLOUDFLARE_ZONE_ID / CLOUDFLARE_API_TOKEN nie sú nastavené)."
        )
        return

    files = [
        f"{WIDGET_PUBLIC_BASE}/chat-widget.js",
        f"{WIDGET_PUBLIC_BASE}/widget/style.css",
        f"{WIDGET_PUBLIC_BASE}/static/js/chat.js",
        f"{WIDGET_PUBLIC_BASE}/static/css/style.css",
        f"{WIDGET_PUBLIC_BASE}/widget/manifest.json",
        f"{WIDGET_PUBLIC_BASE}/widget/{WIDGET_VERSION}/chat.js",
        f"{WIDGET_PUBLIC_BASE}/widget/{WIDGET_VERSION}/style.css",
        f"{WIDGET_PUBLIC_BASE}/static/img/bot.png",
    ]
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache",
                headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
                json={"files": files},
            )
        if response.status_code == 200 and response.json().get("success"):
            logger.info("Cloudflare cache widgetu vymazaná: %s", ", ".join(files))
        else:
            logger.warning("Cloudflare purge zlyhal (%s): %s", response.status_code, response.text[:300])
    except Exception as exc:
        logger.warning("Cloudflare purge exception: %s", exc)


@app.on_event("startup")
async def startup_event():
    logger.info("LLM provider: %s | model: %s", LLM_API_BASE_URL, LLM_MODEL)
    if not LLM_API_KEY:
        logger.warning("EUROUTER_API_KEY / OPENROUTER_API_KEY nie je nastavený — chat nebude fungovať.")
    if resend_configured():
        logger.info("Lead notifikácie: Resend API (HTTPS) — odporúčané pre Docker hosting.")
    elif smtp_configured():
        logger.info("Lead notifikácie: SMTP (môže byť zablokované z kontajnera).")
    elif discord_configured():
        logger.info("Lead notifikácie: Discord webhook (záloha bez emailu).")
    else:
        logger.warning(
            "Lead notifikácie nie sú nakonfigurované — nastavte RESEND_API_KEY "
            "alebo DISCORD_WEBHOOK_URL (SMTP z Dockeru často nefunguje)."
        )
    if is_github_configured():
        logger.info(
            "Knowledge base: GitHub %s/%s@%s (aktualizácia len cez portál webhook)",
            os.getenv("GITHUB_OWNER", "hudakjan89-ctrl"),
            os.getenv("GITHUB_REPO", "ceskanadrz-knowledge"),
            os.getenv("GITHUB_BRANCH", "main"),
        )
        logger.info(github_token_hint())
    else:
        logger.warning(
            "GITHUB_TOKEN nie je nastavený — knowledge base sa načíta len z lokálnej cache."
        )
    logger.info("Analytics DB: %s", DB_PATH)
    logger.info("Aplikacia startuje. Nacitavam knowledge base...")
    sections = load_knowledge_on_startup()
    logger.info("Knowledge base pripravena (%d sekcii).", sections)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_database_task, 'interval', hours=6)
    scheduler.add_job(sync_knowledge_task, 'interval', hours=6)
    scheduler.add_job(refresh_dashboard_cache, 'interval', hours=2)
    scheduler.start()
    logger.info("Naplanovana uloha update_database_task - produkty z XML (kazdych 6 hodin).")
    logger.info("Naplanovana uloha sync_knowledge_task (kazdych 6 hodin).")
    logger.info("Naplanovana uloha refresh_dashboard_cache (kazde 2 hodiny).")
    refresh_dashboard_cache()
    await update_database_task()
    if not is_product_index_ready():
        logger.error("Produktový index nie je pripravený po štarte — chat môže vracať nepresné odpovede.")
    asyncio.create_task(purge_cloudflare_widget_cache())
    logger.info("Widget verzia: %s", WIDGET_VERSION)

@app.get("/")
async def health_check():
    return {
        "status": "Česká nádrž RAG Bot is running",
        "version": WIDGET_VERSION,
        "widget_version": WIDGET_VERSION,
        "products_indexed": product_count(),
        "product_index_ready": is_product_index_ready(),
    }

def _llm_headers() -> dict:
    return {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": WIDGET_PUBLIC_BASE,
        "X-EUrouter-Title": "Ceska Nadrz Bot",
    }


def _extract_llm_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("LLM returned no choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if content is None:
        raise ValueError("LLM returned empty content")
    return str(content).strip()


def _is_transient_llm_error(exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    message = str(exc).lower()
    return (
        "no upstream provider" in message
        or "llm api error 429" in message
        or "llm api error 502" in message
        or "llm api error 503" in message
        or "llm api error 529" in message
        or "rate limit" in message
        or "llm returned empty content" in message
        or "llm returned no choices" in message
    )


def _llm_models_to_try() -> list[str]:
    models = [LLM_MODEL]
    if LLM_FALLBACK_MODEL and LLM_FALLBACK_MODEL not in models:
        models.append(LLM_FALLBACK_MODEL)
    return models


async def _request_llm(messages: list, model: str, max_tokens: int, temperature: float) -> str:
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            LLM_CHAT_URL,
            headers=_llm_headers(),
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        if response.status_code != 200:
            raise ValueError(f"LLM API Error {response.status_code}: {response.text[:500]}")
        return _extract_llm_content(response.json())


async def _call_llm(messages: list, max_tokens: int = 600, temperature: float = 0.2) -> str:
    if not LLM_API_KEY:
        raise ValueError("API Key is missing.")

    last_error = None
    for model in _llm_models_to_try():
        for attempt in range(LLM_RETRY_ATTEMPTS):
            try:
                return await _request_llm(messages, model, max_tokens, temperature)
            except (httpx.TimeoutException, httpx.TransportError, ValueError) as exc:
                last_error = exc
                if isinstance(exc, ValueError) and not _is_transient_llm_error(exc):
                    raise exc

            if attempt < LLM_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(min(2 ** attempt, 8))

    raise last_error or ValueError("LLM call failed")


CONSTRUCTION_LABELS = {
    "samonosna": "samonosná",
    "obetonovani": "k obetonování",
    "dvouplastova": "dvouplášťová",
    "nadzemni": "nadzemní",
}

def _build_products_context(found_products: list) -> str:
    if not found_products:
        return "V databázi produktů nebylo nalezeno nic přesného."

    lines = ["NALEZENÉ PRODUKTY V E-SHOPU:"]
    for product in found_products:
        placement = product.get("placement", "")
        construction = product.get("construction_type", "")
        placement_label = {
            "podzemni": "podzemní",
            "nadzemni": "nadzemní",
        }.get(placement, "")
        construction_label = CONSTRUCTION_LABELS.get(construction, "")
        meta_parts = []
        if placement_label:
            meta_parts.append(f"Umístění: {placement_label}")
        if construction_label:
            meta_parts.append(f"Provedení: {construction_label}")
        meta_suffix = f" | {' | '.join(meta_parts)}" if meta_parts else ""
        lines.append(
            f"- Název: {product.get('name', 'Neznámý produkt')} | "
            f"Cena: {product.get('price', '—')} | "
            f"Odkaz: {product.get('url', '—')} | "
            f"Kategorie: {product.get('category', '—')}{meta_suffix}"
        )
    return "\n".join(lines) + "\n"


def _build_knowledge_context(found_knowledge: list) -> str:
    if not found_knowledge:
        return "FIREMNÍ DATABÁZE A FAQ:\n"

    lines = ["FIREMNÍ DATABÁZE A FAQ:"]
    for chunk in found_knowledge:
        title = chunk.get("title") or chunk.get("name") or "FAQ"
        content = chunk.get("content") or chunk.get("body") or ""
        lines.append(f"--- TÉMA: {title} ---\n{content}\n")
    return "\n".join(lines) + "\n"


async def generate_optimized_search_query(chat_history: list, new_message: str) -> str:
    if len(chat_history) < 2: return new_message
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-4:]])
    prompt = f"""Jsi interní vyhledávací systém e-shopu Česká nádrž. Přečti si historii konverzace a poslední zprávu.
Tvojím JEDINÝM úkolem je vytvořit z toho jednu přesnou vyhledávací frázi (3-8 slov) pro vyhledávání v databázi produktů.

Historie konverzace:
{history_text}
Poslední zpráva: {new_message}

PRAVIDLA:
- Napiš POUZE samotnou vyhledávací frázi bez uvozovek.
- Vždy zachovej účel (dešťovka/pitná/splašky/retenční) a objem (např. 10m3) z historie.
- Pokud zákazník řekne „podzemní“, „pod zem“ nebo „do země“, NEPOUŽÍVEJ jen slovo podzemní. Místo toho hledej „samonosná nádrž“ nebo „nádrž k obetonování“ a zachovej účel a objem.
- Pokud zákazník řekne „nadzemní“, hledej „nadzemní volně stojící nádrž“.
- Nikdy nevracej jen jedno slovo typu „podzemní“, „nadzemní“ nebo samotný objem „5 m3“.
- Pokud jde o pozdrav nebo věc mimo e-shop, napiš NONE."""
    try:
        result = await _call_llm(
            [{"role": "user", "content": prompt}],
            max_tokens=40,
            temperature=0.0,
        )
        return result.replace('"', '').strip()
    except Exception:
        return new_message


def enrich_search_query(optimized_query: str, chat_history: list, new_message: str) -> str:
    if not optimized_query or optimized_query in ("NONE", "CONTACT_CAPTURE"):
        return optimized_query

    combined = f"{optimized_query} {new_message}".strip()
    normalized = remove_diacritics(combined.lower())
    placement_only_terms = {
        "podzemni", "nadzemni", "pod", "nad", "pod zem", "nad zem", "do zeme",
    }
    words = normalized.split()
    if normalized in placement_only_terms or (len(words) <= 2 and any(term in normalized for term in placement_only_terms)):
        user_context = " ".join(
            msg["content"] for msg in chat_history[-6:] if msg.get("role") == "user"
        )
        combined = f"{user_context} {new_message}".strip()

    return expand_search_query(combined)


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(request: Request, chat_req: ChatRequest):
    x_nadrz_token = request.headers.get("x-nadrz-token")
    if x_nadrz_token != "nadrz-secure-2026":
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Token")

    session_id = chat_req.session_id or str(uuid.uuid4())
    ensure_session_loaded(session_id)
    is_new_session = not session_has_messages(session_id)
    user_id_hash = build_user_hash(session_id)
    user_message_id = str(uuid.uuid4())
    bot_message_id = str(uuid.uuid4())

    if is_new_session and not session_has_event(session_id, "chat_started"):
        page_metadata = {"source": "web_widget"}
        if chat_req.page_url:
            page_metadata["page_url"] = chat_req.page_url
        if chat_req.page_path:
            page_metadata["page_path"] = chat_req.page_path
        if chat_req.page_title:
            page_metadata["page_title"] = chat_req.page_title
        if chat_req.referrer:
            page_metadata["referrer"] = chat_req.referrer
        emit_event(
            event_name="chat_started",
            session_id=session_id,
            user_id_hash=user_id_hash,
            language=chat_req.language,
            metadata=page_metadata
        )
    
    is_contact_capture = "[KONTAKTNÍ FORMULÁŘ]" in chat_req.message or "[PASIVNÍ ZÁCHYT KONTAKTU]" in chat_req.message
    optimized_query = "CONTACT_CAPTURE" if is_contact_capture else await generate_optimized_search_query(sessions[session_id], chat_req.message)
    log_message(session_id, "user", chat_req.message)
    emit_event(
        event_name="message_user",
        session_id=session_id,
        message_id=user_message_id,
        user_id_hash=user_id_hash,
        language=chat_req.language,
        metadata={
            "length": len(chat_req.message),
            "query_text": chat_req.message,
            "optimized_query": optimized_query
        }
    )

    # Detekce leadu (odeslaný aktivně nebo pasivně zachycený)
    if is_contact_capture:
        history = list(sessions[session_id]) + [{"role": "user", "content": chat_req.message}]
        await send_lead_email(chat_req.message, history)
        if "[KONTAKTNÍ FORMULÁŘ]" in chat_req.message:
            emit_event(
                event_name="contact_submitted",
                session_id=session_id,
                message_id=user_message_id,
                user_id_hash=user_id_hash,
                language=chat_req.language,
                metadata={"channel": "chat"}
            )
        if "[PASIVNÍ ZÁCHYT KONTAKTU]" in chat_req.message:
            emit_event(
                event_name="contact_captured_passive",
                session_id=session_id,
                message_id=user_message_id,
                user_id_hash=user_id_hash,
                language=chat_req.language,
                metadata={"channel": "chat"}
            )
        return ChatResponse(response="", session_id=session_id)
    
    sessions[session_id].append({"role": "user", "content": chat_req.message})
    
    products_context = ""
    found_products = []
    if optimized_query != "NONE":
        search_query = enrich_search_query(optimized_query, sessions[session_id], chat_req.message)
        found_products = await asyncio.to_thread(search_products, search_query, 8)
        products_context = _build_products_context(found_products)

    if optimized_query != "NONE":
        knowledge_query = enrich_search_query(optimized_query, sessions[session_id], chat_req.message)
    else:
        knowledge_query = expand_search_query(chat_req.message)
    found_knowledge = await asyncio.to_thread(search_knowledge, knowledge_query, 6)
    knowledge_context = _build_knowledge_context(found_knowledge)

    lang_instruction = "MUSÍŠ odpovídat striktně ČESKY."
    if chat_req.language == "sk": lang_instruction = "MUSÍŠ odpovedať striktne SLOVENSKY!"
    elif chat_req.language == "en": lang_instruction = "You MUST answer strictly in ENGLISH!"
    elif chat_req.language == "uk": lang_instruction = "Ти ПОВИНЕН відповідати строго УКРАЇНСЬКОЮ мовою!"

    already_recommended_context = ""
    if recommended_urls[session_id]:
        already_recommended_context = "V TÉTO KONVERZACI JSI JIŽ DOPORUČIL TYTO PRODUKTY (nikdy neříkej, že je nemáme):\n"
        for u in recommended_urls[session_id][-5:]:
            already_recommended_context += f"- {u}\n"
        already_recommended_context += "\n"

    system_prompt = (
        f"Jsi technický poradce e-shopu Česká nádrž. Tvojí specializací jsou plastové podzemní a nadzemní nádrže na vodu, jímky, septiky, čistírny odpadních vod, vodoměrné šachty a související příslušenství.\n"
        f"ZAPAMATUJ SI: Pojem 'nádrž' v tomto kontextu VŽDY znamená plastovou nádrž na vodu, dešťovku nebo splašky. Nikdy neodkazuj na vojenské tanky, plynové nádrže ani cokoliv mimo sortiment vodohospodářských systémů.\n\n"
        f"ZDROJE INFORMACÍ (čerpej POUZE z nich, nikdy z vlastních znalostí o legislativě, normách ani z internetu):\n"
        f"{knowledge_context}\n"
        f"---------------------\n"
        f"{products_context}\n"
        f"---------------------\n\n"
        f"{already_recommended_context}"
        "ZÁKLADNÍ PRAVIDLA CHOVÁNÍ (přísně dodržuj):\n\n"
        "1) STRUČNOST A RELEVANCE: Odpovídej stručně a k věci. Dlouhé odpovědi piš jen tehdy, když si o to zákazník výslovně řekne. Nepřidávej irelevantní kontext ani 'pro úplnost' další informace, na které se neptal.\n\n"
        "2) LEGISLATIVA A NORMY — PŘÍSNÝ ZÁKAZ SPONTÁNNÍCH RAD: Neodpovídej na legislativní, vodoprávní ani normativní otázky (ČSN, NV 401/2015, povolení, vypouštění, vsakování vs. vodoteče, kolaudace atd.), POKUD se zákazník výslovně NEZEPTÁ. Když se ptá na velikost, typ nebo doporučení produktu, nepřidávej věty o tom, 'kam se smí vypouštět' ani 'co vyžaduje úřad'. Pokud zákazník legislativu výslovně zmíní, řekni obecně, že podmínky určuje místní vodoprávní úřad a doporuč ověření u něj — nevymýšlej si paragrafy ani konkrétní limity.\n\n"
        "3) KONZISTENCE S VLASTNÍMI PŘEDCHOZÍMI ODPOVĚDMI: Pokud jsi v této konverzaci již doporučil konkrétní produkt nebo typ řešení, v dalších zprávách tento fakt neodvolávej. Nikdy neříkej 'nemáme nádrže na vodu', pokud jsi o kus výš nějakou nádrž doporučil. Když si nejsi jistý, odkaž zákazníka na svou předchozí odpověď místo popření.\n\n"
        "4) RYCHLÁ A ODBORNÁ ANALÝZA POŽADAVKU: Nevyptávej se zbytečně dlouho. Zjisti jen to nejnutnější: účel (dešťovka / splašky / pitná / požární-retenční), orientační objem, případně zatížení (zelená plocha / pojezd / spodní voda). Pokud zákazník řekne podzemní, okamžitě nabídni relevantní varianty ze sekce NALEZENÉ PRODUKTY — neptej se znovu na nadzemní vs. podzemní.\n\n"
        "5) ZÁKAZ VYMÝŠLENÍ: Čerpej VÝHRADNĚ ze sekcí 'NALEZENÉ PRODUKTY' a 'FIREMNÍ DATABÁZE'. Pokud tam informace není, řekni, že ji nemáš, a nabídni kontakt na obchod@ceskanadrz.cz. Nevymýšlej si parametry, ceny ani vlastnosti, které nejsou v datech.\n\n"
        "6) ATYPICKÉ POŽADAVKY: Pokud zákazník chce něco, co v produktech není (atypický objem, speciální provedení), odkaž ho na výrobu na míru podle dodaných rozměrů: 'Napište svůj přesný požadavek, rozměry a účel na obchod@ceskanadrz.cz a kolegové posoudí vhodné řešení.' Nikdy netvrď, že nádrž vyrobíme nebo svaříme přímo na místě u zákazníka.\n\n"
        "7) ODKAZ NA PRODUKT: Když doporučíš konkrétní produkt z e-shopu, VŽDY přidej na úplný konec zprávy skrytý tag přesně ve formátu [URL: https://www.ceskanadrz.cz/konkretni-produkt/]. Tag musí mít hranaté závorky, nesmí být v markdown odkazu a nesmí být volně v textu.\n\n"
        "8) DOTACE (Dešťovka / Nová zelená úsporám): Pokud téma dotací zazní, odpověz: 'Podmínky dotací se průběžně mění, zanechte mi prosím kontakt (e-mail, telefon) a náš dotační specialista se vám ozve.' Na konec zprávy přidej tag: [SHOW_CONTACT_FORM].\n\n"
        "FORMÁT ODPOVĚDÍ:\n"
        "- Piš plynulým textem v odstavcích. Nepoužívej nadpisy typu ### nebo ####. Nepoužívej markdown tabulky. Nepoužívej emoji (✔️, ❌, 👉, 💡 atd.) ani horizontální oddělovače (---).\n"
        "- Tučně (pomocí **text**) formátuj POUZE klíčové kontakty (e-mail, telefon) a kritické parametry, nic jiného.\n"
        "- Nedávej odrážkové seznamy, pokud to zákazník neočekává (např. výčet parametrů). Preferuj souvislý text.\n"
        "- Drž se 2–5 vět na odpověď, pokud si zákazník nevyžádá detail.\n\n"
        "KONTAKT A FORMULÁŘ:\n"
        "- Nikdy netvrď, že už máme kontakt na zákazníka, pokud v běžné viditelné historii není jasně řečeno, že formulář odeslal. Samotné zobrazení formuláře nebo výzva k zanechání kontaktu neznamená, že kontakt máme.\n"
        "- Když se zákazník ptá, s kým to může probrat, odpověz kontaktem na obchodní oddělení: obchod@ceskanadrz.cz a telefon 737 234 461. Nepiš, že se mu ozveme, pokud ještě nezanechal e-mail nebo telefon.\n\n"
        "- Když se zákazník ptá na objednávku, objednání v chatu, dokončení objednávky nebo chce poradit s objednáním konkrétního produktu, řekni stručně, že objednávku v chatu přímo nevytvoří, ale může zanechat kontakt; zavoláme mu a objednávku společně uděláme telefonicky. Na konec zprávy vždy přidej tag [SHOW_CONTACT_FORM].\n\n"
        "TECHNICKÁ FAKTA (často chybovaná):\n"
        "- Podzemní nádrže jsou náš hlavní sortiment (cca 99 % prodejů). Vyrábíme je ve 3 variantách: SAMONOSNÁ, K OBETONOVÁNÍ a DVOUPLÁŠŤOVÁ. Když zákazník řekne podzemní a v NALEZENÝCH PRODUKTECH jsou varianty, vždy uveď všechny relevantní (ne jen 2 ze 3). Nikdy neříkej, že podzemní nádrže nemáme.\n"
        "- Varianta K OBETONOVÁNÍ není vhodná do míst s vysokou spodní vodou — tam doporuč DVOUPLÁŠŤOVOU variantu. Samonosná zvládá standardní podmínky bez betonu.\n"
        "- Pojem 'retenční nádrž' zákazníci často myslí jako nádrž na dešťovou vodu nebo požární/retenční nádrž. Samostatná 10 m³ retenční SKU v katalogu nemusí existovat — nejbližší jsou nádrže na dešťovou vodu 10 m³ nebo požární nádrže 20 m³ (2×10 m³). Nikdy netvrď, že 10 m³ nádrže vůbec nemáme.\n"
        "- Pokud zákazník napíše objem bez '3' (např. '10m' nebo 'deset kubíků'), chápej to jako m³.\n"
        "- Samonosné septiky NEVYŽADUJÍ obetonování — zvládají standardní podmínky v zemi bez betonu.\n"
        "- U septiků zákazníkům standardně doporučuj tříkomorové septiky. Nenabízej šesti-komorové ani zbytečně větší septiky, pokud si zákazník výslovně neřekne o velkou kapacitu nebo z dat jasně nevyplývá trvalé vysoké zatížení. U chat a víkendového provozu zohledni, že nejde o plné celoroční obsazení, a preferuj menší vhodné řešení.\n"
        "- K septikům spontánně nepřidávej zemní pískový filtr, vypouštění, povolení ani jiné legislativní doplňky, pokud se zákazník výslovně neptá na legislativu nebo vypouštění.\n"
        "- U vodoměrných šachet nenabízej konkrétní velikost, model ani cenu podle vlastního odhadu. Doporuč jen konstrukční typ podle podmínek (např. samonosná / k obetonování) a u velikosti vždy odkaž na požadavky místní vodárenské společnosti nebo správce vodovodu. Konkrétní produkt a URL dávej až tehdy, když zákazník uvede požadovaný rozměr nebo typ podle vodáren.\n"
        "- Výroba nebo svařování plastové nádrže přímo na místě u zákazníka může být obecně technicky možné, ale Česká nádrž tuto službu neposkytuje. Pokud se zákazník ptá na nádrž do sklepa nebo svaření na místě, řekni, že to neděláme, a nabídni posouzení zákazkového řešení podle rozměrů přístupové cesty, sklepa, požadovaného objemu a účelu.\n"
        "- Při orientačním výpočtu velikosti jímky používej 100 litrů odpadní vody na osobu a den, ne 150 litrů. Vždy připomeň, že skutečná velikost závisí i na frekvenci vývozu a reálné spotřebě domácnosti.\n"
        "- Kalová čerpadla s vestavěným plovákem (do jímek/septiků) máme v sortimentu — pokud jsou v NALEZENÝCH PRODUKTECH, doporuč je. U čerpání dešťové vody z nádrže ale preferuj automatické čerpadlo nebo hotový set, ne plovákové řešení.\n"
        "- Hlásiče naplnění jímky/nádrže/septiku máme v sortimentu — pokud jsou v NALEZENÝCH PRODUKTECH, popiš je podle dostupných parametrů v popisu produktu.\n"
        "- Plastové nádrže do 5 m³ lze usadit ručně, nevyžadují bagr ani speciální techniku.\n"
        "- Nikdy zákazníkovi neříkej, že 'od 5 m³ potřebuje speciální techniku' — není to pravda.\n"
        "- Nenabízej dělení objemu na více nádrží, pokud zákazník explicitně nechce objem nad 20 m³ a sám se na to nezeptá.\n\n"
        "SLOVOSLED A JAZYK:\n"
        f"- {lang_instruction}\n"
        "- Dbej na správné české skloňování (septik, jímka, nádrž). Žádné nesmyslné tvary.\n"
        "- Udržuj profesionální, klidný a věcný tón. Ne přehnaně nadšený, ne marketingový.\n"
    )
    
    messages = [{"role": "system", "content": system_prompt}] + sessions[session_id][-10:]
    
    try:
        assistant_message = await _call_llm(messages)

        # Post-processing: vyčisti zbytky tagů, nadměrné newlines a markdown artefakty
        assistant_message = re.sub(r'\n{3,}', '\n\n', assistant_message)
        assistant_message = re.sub(r'^#{2,6}\s+', '', assistant_message, flags=re.MULTILINE)
        assistant_message = re.sub(r'\n\s*---+\s*\n', '\n\n', assistant_message)
        assistant_message = assistant_message.strip()

        detected_url = detect_page_section(chat_req.message)
        detected_image = None
        hidden_url, assistant_message = extract_hidden_url_tag(assistant_message)

        if hidden_url:
            log_event("product_recommendation")
            detected_url = hidden_url
            corrected_from_url = None
            mentioned_product = resolve_mentioned_product(found_products, assistant_message, detected_url)
            if mentioned_product and mentioned_product.get("url") != detected_url:
                corrected_from_url = detected_url
                detected_url = mentioned_product.get("url")

            if detected_url not in recommended_urls[session_id]:
                recommended_urls[session_id].append(detected_url)

            detected_product = mentioned_product or find_product_by_url(found_products, detected_url)
            if detected_product:
                detected_image = detected_product.get('image_url')
            emit_event(
                event_name="product_recommended",
                session_id=session_id,
                message_id=bot_message_id,
                user_id_hash=user_id_hash,
                language=chat_req.language,
                metadata={
                    "url": detected_url,
                    "image_url": detected_image,
                    "corrected_from_url": corrected_from_url,
                    "optimized_query": optimized_query
                }
            )

        show_form = False
        msg_lower = assistant_message.lower()
        if "[SHOW_CONTACT_FORM]" in assistant_message or "zanechte mi" in msg_lower or "formulář" in msg_lower:
            show_form = True
            assistant_message = assistant_message.replace("[SHOW_CONTACT_FORM]", "").strip()
            emit_event(
                event_name="contact_form_shown",
                session_id=session_id,
                message_id=bot_message_id,
                user_id_hash=user_id_hash,
                language=chat_req.language,
                metadata={"trigger": "assistant_response"}
            )

        # Odstraň osamělé tagy, které nejsou určené k zobrazení zákazníkovi.
        assistant_message = re.sub(r'\[(?!\s*SHOW_CONTACT_FORM\s*\])[^\]]*\]', '', assistant_message, flags=re.IGNORECASE).strip()

        sessions[session_id].append({"role": "assistant", "content": assistant_message})
        conversation_message_count = len(sessions[session_id])
        if conversation_message_count <= 2:
            length_bucket = "short"
        elif conversation_message_count <= 6:
            length_bucket = "medium"
        else:
            length_bucket = "long"

        log_message(session_id, "bot", assistant_message)
        emit_event(
            event_name="message_bot",
            session_id=session_id,
            message_id=bot_message_id,
            user_id_hash=user_id_hash,
            language=chat_req.language,
            metadata={
                "length": len(assistant_message),
                "has_product_url": bool(detected_url),
                "show_contact_form": show_form,
                "conversation_message_count": conversation_message_count,
                "conversation_length_bucket": length_bucket
            }
        )

        return ChatResponse(
            response=assistant_message,
            session_id=session_id,
            page_section=detected_url,
            image_url=detected_image,
            show_contact_form=show_form
        )
            
    except Exception as e:
        transient = _is_transient_llm_error(e)
        error_msg = f"Error v endpointe /chat. Message: {chat_req.message}. Exception: {str(e)}"
        if transient:
            logger.warning(error_msg)
        else:
            logger.exception(error_msg)
        fire_alert(error_msg)
        emit_event(
            event_name="chat_error",
            session_id=session_id,
            message_id=bot_message_id,
            user_id_hash=user_id_hash,
            language=chat_req.language,
            metadata={
                "error": str(e),
                "query_text": chat_req.message,
                "optimized_query": optimized_query,
                "transient": transient,
            },
        )
        fallback = (
            "Omlouváme se, odpověď se momentálně nepodařilo načíst. Zkuste dotaz prosím poslat znovu za chvíli "
            "nebo nás kontaktujte na obchod@ceskanadrz.cz."
        )
        sessions[session_id].append({"role": "assistant", "content": fallback})
        log_message(session_id, "bot", fallback)
        return ChatResponse(response=fallback, session_id=session_id)
