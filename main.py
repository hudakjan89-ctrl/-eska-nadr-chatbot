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
from logger import log_message, log_event, emit_event, build_user_hash
from alerter import fire_alert
from mailer import send_lead_email

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
recommended_urls = {}  # session_id -> list of already recommended product URLs

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
            logger.info(f"Nacitanych {len(products)} produktov, ukladám do DB...")
            upsert_products(products)
        else:
            logger.warning("Ziadne produkty stiahnute z XML (prazdny zoznam).")
        
        logger.info("Refreshujem knowledge base...")
        load_and_upsert_knowledge()
        logger.info("Uloha update_database_task dokoncena uspesne.")
    except Exception as e:
        logger.exception("Kriticka chyba v opakovanej ulohe update_database_task!")
        fire_alert(f"Zlyhal update_database_task feed!\nChyba: {str(e)}")

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
                json={"model": "anthropic/claude-opus-4.7", "messages":[{"role": "user", "content": prompt}], "temperature": 0.0, "max_tokens": 20}
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
    is_new_session = session_id not in sessions
    if is_new_session:
        sessions[session_id] = []
        
    if session_id not in recommended_urls:
        recommended_urls[session_id] = []
    user_id_hash = build_user_hash(session_id)
    user_message_id = str(uuid.uuid4())
    bot_message_id = str(uuid.uuid4())

    if is_new_session:
        emit_event(
            event_name="chat_started",
            session_id=session_id,
            user_id_hash=user_id_hash,
            language=chat_req.language,
            metadata={"source": "web_widget"}
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
        send_lead_email(chat_req.message, sessions[session_id])
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
        found_products = search_products(optimized_query, top_k=8)
        products_context = "NALEZENÉ PRODUKTY V E-SHOPU:\n"
        for p in found_products:
            products_context += f"- Název: {p['name']} | Cena: {p['price']} | Odkaz: {p['url']} | Kategorie: {p['category']}\n"
        if not found_products:
            products_context = "V databázi produktů nebylo nalezeno nic přesného."
            
    found_knowledge = search_knowledge(optimized_query, top_k=6)
    knowledge_context = "FIREMNÍ DATABÁZE A FAQ:\n"
    for k in found_knowledge:
        knowledge_context += f"--- TÉMA: {k['title']} ---\n{k['content']}\n\n"

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
        "4) RYCHLÁ A ODBORNÁ ANALÝZA POŽADAVKU: Nevyptávej se zbytečně dlouho. Zjisti jen to nejnutnější: účel (dešťovka / splašky / pitná), orientační objem, umístění (zelená plocha / pojezd / spodní voda). Jakmile toto víš, okamžitě nabídni nejvhodnější produkt ze sekce NALEZENÉ PRODUKTY.\n\n"
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
        "- Samonosné septiky NEVYŽADUJÍ obetonování — zvládají standardní podmínky v zemi bez betonu.\n"
        "- U septiků zákazníkům standardně doporučuj tříkomorové septiky. Nenabízej šesti-komorové ani zbytečně větší septiky, pokud si zákazník výslovně neřekne o velkou kapacitu nebo z dat jasně nevyplývá trvalé vysoké zatížení. U chat a víkendového provozu zohledni, že nejde o plné celoroční obsazení, a preferuj menší vhodné řešení.\n"
        "- K septikům spontánně nepřidávej zemní pískový filtr, vypouštění, povolení ani jiné legislativní doplňky, pokud se zákazník výslovně neptá na legislativu nebo vypouštění.\n"
        "- U vodoměrných šachet nenabízej konkrétní velikost, model ani cenu podle vlastního odhadu. Doporuč jen konstrukční typ podle podmínek (např. samonosná / k obetonování) a u velikosti vždy odkaž na požadavky místní vodárenské společnosti nebo správce vodovodu. Konkrétní produkt a URL dávej až tehdy, když zákazník uvede požadovaný rozměr nebo typ podle vodáren.\n"
        "- Výroba nebo svařování plastové nádrže přímo na místě u zákazníka může být obecně technicky možné, ale Česká nádrž tuto službu neposkytuje. Pokud se zákazník ptá na nádrž do sklepa nebo svaření na místě, řekni, že to neděláme, a nabídni posouzení zákazkového řešení podle rozměrů přístupové cesty, sklepa, požadovaného objemu a účelu.\n"
        "- Při orientačním výpočtu velikosti jímky používej 100 litrů odpadní vody na osobu a den, ne 150 litrů. Vždy připomeň, že skutečná velikost závisí i na frekvenci vývozu a reálné spotřebě domácnosti.\n"
        "- U dešťové vody a čerpání nedoporučuj čerpadla s plovákem. Preferuj automaty a ideálně hotové sety. Pokud zákazník řeší využití vody z nádrže, doporučuj spíše kompletní vhodný set než samostatně filtr a samostatné čerpadlo.\n"
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
                json={"model": "anthropic/claude-opus-4.7", "messages": messages, "temperature": 0.2, "max_tokens": 400}
            )
            
            if response.status_code != 200:
                raise Exception(f"OpenRouter Error {response.status_code}: {response.text}")
            
            data = response.json()
            assistant_message = data["choices"][0]["message"]["content"]
            
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
            
            # Necháme hvězdičky pro markdown formátování zpráv:
            # assistant_message = assistant_message.replace("**", "")

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
        error_msg = f"Error v endpointe /chat. Message: {chat_req.message}. Exception: {str(e)}"
        logger.exception(error_msg)
        fire_alert(error_msg)
        raise HTTPException(status_code=500, detail="Internal Server Error")
