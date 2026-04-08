import os
import sys
import logging
import uuid
import httpx
import asyncio
import unicodedata
import re
from typing import Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from xml_parser import fetch_and_parse_xml
from database import upsert_products, search_products, load_and_upsert_knowledge, search_knowledge
from admin import router as admin_router
from logger import log_message, log_event

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ceska_nadrz.main")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

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

app.mount("/static", StaticFiles(directory="static"), name="static")

sessions = {}

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=500)
    session_id: Optional[str] = None
    language: Optional[str] = "cs"

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
    "https://www.ceskanadrz.cz/nadrze-na-destovou-vodu/":["destovou vodu", "na destovku", "nadrze na destovku", "na zalevani"],
    "https://www.ceskanadrz.cz/nadrze-na-vodu-k-obetonovani/":["nadrze k obetonovani", "nadrz k obetonovani", "obetonovani"],
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

async def update_database_task():
    try:
        logger.info("Vykonavam planovanu ulohu update_database_task...")
        products = await fetch_and_parse_xml()
        if products:
            logger.info(f"Nacitanych {len(products)} produktov, ukladám do DB...")
            upsert_products(products)
        else:
            logger.warning("Ziadne produkty stiahnute z XML (prazdny zoznam).")
        
        logger.info("Refreshujem knowledge base...")
        load_and_upsert_knowledge()
        logger.info("Uloha update_database_task dokoncena uspesne.")
    except Exception as e:
        logger.exception("Kriticka chyba v opakovanej ulohe update_database_task!")

@app.on_event("startup")
async def startup_event():
    logger.info("Aplikacia startuje. Vykonava sa load_and_upsert_knowledge...")
    load_and_upsert_knowledge()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_database_task, 'interval', hours=6)
    scheduler.start()
    logger.info("Naplanovana uloha update_database_task (kazdych 6 hodin).")
    asyncio.create_task(update_database_task())

@app.get("/")
async def health_check():
    return {"status": "Česká nádrž RAG Bot is running", "version": "9.2 (Strict Destovka Rules)"}

async def generate_optimized_search_query(chat_history: list, new_message: str) -> str:
    if len(chat_history) < 2: return new_message
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in chat_history[-4:]])
    prompt = f"""Jsi interní vyhledávací systém e-shopu. Přečti si historii konverzace a poslední zprávu. 
Tvojím JEDINÝM úkolem je vytvořit z toho jednu přesnou vyhledávací frázi (3-6 slov) pro fulltextové vyhledávání v databázi produktů.
Historie konverzace:
{history_text}
Poslední zpráva: {new_message}
PRAVIDLA: Napiš POUZE samotnou vyhledávací frázi bez uvozovek. Pokud jde o pozdrav nebo věc mimo e-shop, napiš NONE."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                json={"model": "anthropic/claude-sonnet-4.6", "messages":[{"role": "user", "content": prompt}], "temperature": 0.0, "max_tokens": 20}
            )
            data = response.json()
            return data["choices"][0]["message"]["content"].strip().replace('"', '')
    except Exception:
        return new_message


@app.post("/chat", response_model=ChatResponse)
@limiter.limit("10/minute")
async def chat(request: Request, chat_req: ChatRequest):
    x_nadrz_token = request.headers.get("x-nadrz-token")
    if x_nadrz_token != "nadrz-secure-2026":
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Token")

    session_id = chat_req.session_id or str(uuid.uuid4())
    if session_id not in sessions: sessions[session_id] = []
    
    log_message(session_id, "user", chat_req.message)
    
    optimized_query = await generate_optimized_search_query(sessions[session_id], chat_req.message)
    sessions[session_id].append({"role": "user", "content": chat_req.message})
    
    products_context = ""
    found_products = []
    if optimized_query != "NONE":
        found_products = search_products(optimized_query, top_k=8)
        products_context = "NALEZENÉ PRODUKTY V E-SHOPU:\n"
        for p in found_products:
            products_context += f"- Název: {p['name']} | Cena: {p['price']} | Odkaz: {p['url']} | Kategorie: {p['category']}\n"
        if not found_products:
            products_context = "V databázi produktů nebylo nalezeno nic přesného."
            
    found_knowledge = search_knowledge(optimized_query, top_k=3)
    knowledge_context = "FIREMNÍ DATABÁZE A FAQ:\n"
    for k in found_knowledge:
        knowledge_context += f"--- TÉMA: {k['title']} ---\n{k['content']}\n\n"

    lang_instruction = "MUSÍŠ odpovídat striktně ČESKY."
    if chat_req.language == "sk": lang_instruction = "MUSÍŠ odpovedať striktne SLOVENSKY!"
    elif chat_req.language == "en": lang_instruction = "You MUST answer strictly in ENGLISH!"
    elif chat_req.language == "uk": lang_instruction = "Ти ПОВИНЕН відповідати строго УКРАЇНСЬКОЮ мовою!"

    system_prompt = (
        f"Jsi technický poradce a asistent e-shopu Česká nádrž. Tvůj tón je přátelský a vysoce odborný.\n\n"
        f"{knowledge_context}\n"
        f"---------------------\n"
        f"{products_context}\n"
        f"---------------------\n"
        "TVÉ HLAVNÍ ÚKOLY A PRAVIDLA (ČTI POZORNĚ!):\n"
        "1. KROK 1 (DOPTAZOVÁNÍ): Zjisti parametry (účel, objem, rozměry). NIKDY nenabízej produkt naslepo bez parametrů.\n"
        "2. KROK 2 (DOPORUČENÍ): Vyber nejvhodnější produkt z 'NALEZENÉ PRODUKTY V E-SHOPU'. Popiš ho a uveď cenu. ZÁKAZ: NIKDY nepiš odkaz do věty jako text! Vždy na úplný konec zprávy přidej skrytý tag: [URL: zde_vloz_odkaz_z_databaze]\n"
        "3. KROK 3 (PRODEJ ALTERNATIVY): Pokud nenajdeš přesný produkt, ale najdeš podobnou alternativu, NEOMOUVEJ SE! Aktivně nabídni tuto alternativu a přidej tag s odkazem [URL:...].\n"
        
        "4. KROK 4 (ZMĚNA CHOVÁNÍ - DOTACE DEŠŤOVKA): \n"
        "   - Jakmile se zákazník zeptá na dotaci Dešťovka nebo Nová zelená úsporám:\n"
        "     ❌ NEODPOVÍDEJ KLASICKY a nedávej mu žádné informace o dotaci z naší firemní databáze (informace na webu nejsou aktuální, zůstávají tam jen kvůli SEO).\n"
        "     ✅ OKAMŽITĚ sbírej kontakt (lead).\n"
        "   - Řekni PŘESNĚ toto: 'V podmínkách dotace došlo k důležitým změnám. Protože aktuální informace je potřeba řešit vždy individuálně, zanechte mi prosím své Jméno, E-mail a Telefon. Náš specialista se vám brzy ozve, aby s vámi probral všechny aktuální možnosti dotace.' -> NA ÚPLNÝ KONEC PŘIDEJ TAG: [SHOW_CONTACT_FORM]\n"
        
        "5. KROK 5 (TECHNICKÝ DOTAZ): Pokud má zákazník technický dotaz (např. usazení), na který neznáš odpověď, řekni: 'S tímto technickým detailem vám nejlépe poradí náš specialista Petr Nováček. Zanechte mi prosím své Jméno, E-mail a Telefonní číslo a on se vám ozve.' -> NA ÚPLNÝ KONEC PŘIDEJ TAG: [SHOW_CONTACT_FORM]\n\n"
        
        "ZÁKAZY A SLOVNÍK:\n"
        "- ❌ ZMĚNIT WORDING: Nepoužívat slovo 'Dešťovka' jako nabídku produktu/služby. Místo toho všude profesionálně používat termín 'Nádrže na dešťovou vodu'.\n"
        "- Vystupuj jako asistent e-shopu. Nezmiňuj umělou inteligenci.\n"
        "- Nepoužívej hvězdičky (**) k formátování.\n"
        "- ZÁKAZ: Odkazy vkládej výhradně do tagu [URL: ...], nikdy jako prostý text.\n"
        f"- {lang_instruction}\n"
    )
    
    messages = [{"role": "system", "content": system_prompt}] + sessions[session_id][-10:]
    
    try:
        if not OPENROUTER_API_KEY: raise Exception("API Key is missing.")

        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://nadrz.eniq.eu",
                    "X-Title": "Ceska Nadrz Bot"
                },
                json={"model": "anthropic/claude-sonnet-4.6", "messages": messages, "temperature": 0.2, "max_tokens": 600}
            )
            
            if response.status_code != 200:
                raise Exception(f"OpenRouter Error {response.status_code}: {response.text}")
            
            data = response.json()
            assistant_message = data["choices"][0]["message"]["content"]
            
            detected_url = detect_page_section(chat_req.message) 
            detected_image = None
            url_match = re.search(r'\[URL:\s*(https?://[^\s\]]+)\s*\]', assistant_message, re.IGNORECASE)
            
            if url_match:
                log_event("product_recommendation")
                
                detected_url = url_match.group(1)
                assistant_message = re.sub(r'\[URL:\s*https?://[^\s\]]+\s*\]', '', assistant_message, flags=re.IGNORECASE).strip()
                
                for p in found_products:
                    if p.get('url') == detected_url:
                        detected_image = p.get('image_url')
                        break

            show_form = False
            msg_lower = assistant_message.lower()
            if "[SHOW_CONTACT_FORM]" in assistant_message or "zanechte mi" in msg_lower or "formulář" in msg_lower:
                show_form = True
                assistant_message = assistant_message.replace("[SHOW_CONTACT_FORM]", "").strip()
            
            assistant_message = assistant_message.replace("**", "")

            sessions[session_id].append({"role": "assistant", "content": assistant_message})
            
            log_message(session_id, "bot", assistant_message)
            
            return ChatResponse(
                response=assistant_message, 
                session_id=session_id, 
                page_section=detected_url,
                image_url=detected_image,  
                show_contact_form=show_form
            )
            
    except Exception as e:
        logger.exception(f"Error v endpointe /chat. Message: {chat_req.message}. Exception: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
