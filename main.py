import os
import uuid
import httpx
import unicodedata
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from knowledge import CESKA_NADRZ_KNOWLEDGE

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app = FastAPI()

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
    message: str
    session_id: Optional[str] = None
    language: Optional[str] = "cs"

class ChatResponse(BaseModel):
    response: str
    session_id: str
    page_section: Optional[str] = None
    show_contact_form: bool = False

def remove_diacritics(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

# --- MASÍVNA URL MAPA ROZDELENÁ DO LOGICKÝCH BLOKOV ---
URL_MAP = {
    # 1. ŠPECIFICKÉ PRODUKTY A SETY (Majú najvyššiu prioritu)
    "https://www.ceskanadrz.cz/10m3-nadrz-na-vodu-set-zahrada-standard/":["10m3", "10 kubiku", "10 kubikov", "deset kubiku", "desat kubikov", "10000", "set zahrada", "zahrada standard"],
    "https://www.ceskanadrz.cz/1m3-kruhova-nadrz-na-vodu-k-obetonovani/":["1m3", "1 kubik", "mala nadrz", "kruhova nadrz 1m3"],
    "https://www.ceskanadrz.cz/sachta-na-vrt-mini-k-obetonovani-2/":["mini sachta", "sachta mini", "mini sachtu"],
    "https://www.ceskanadrz.cz/cisticka-odpadnich-vod-pro-2-5-osob-at6/":["at6", "pro 2", "pro 5", "pro 4", "at 6", "cisticka at6"],

    # 2. PODKATEGÓRIE (Špecifické sekcie)
    "https://www.ceskanadrz.cz/nadrze-na-pitnou-vodu-k-obetonovani/":["pitnou vodu k obetonovani", "pitna voda k obetonovani"],
    "https://www.ceskanadrz.cz/dvouplastove-nadrze-na-pitnou-vodu/":["dvouplastove na pitnou", "dvouplastova na pitnou"],
    "https://www.ceskanadrz.cz/odlucovace-tuku-k-obetonovani/":["odlucovace k obetonovani", "odlucovac tuku k obetonovani"],
    "https://www.ceskanadrz.cz/dvouplastove-odlucovace-tuku/":["dvouplastove odlucovace", "dvouplastovy odlucovac"],
    "https://www.ceskanadrz.cz/samonosne-odlucovace-tuku/":["samonosne odlucovace", "samonosny odlucovac"],
    "https://www.ceskanadrz.cz/pozarni-a-retencni-nadrze-k-obetonovani/":["pozarni k obetonovani", "retencni k obetonovani"],
    "https://www.ceskanadrz.cz/dvouplastove-pozarni-a-retencni-nadrze/":["dvouplastove pozarni", "dvouplastove retencni"],
    "https://www.ceskanadrz.cz/samonosne-pozarni-a-retencni-nadrze/":["samonosne pozarni", "samonosne retencni"],

    # 3. ZÁKLADNÉ KATEGÓRIE (Všeobecné hľadanie)
    "https://www.ceskanadrz.cz/nadrze-na-destovou-vodu/":["destovou vodu", "na destovku", "nadrze na destovku", "na zalevani"],
    "https://www.ceskanadrz.cz/nadrze-na-vodu-k-obetonovani/":["nadrze k obetonovani", "nadrz k obetonovani", "obetonovani"],
    "https://www.ceskanadrz.cz/sachty-na-vrt/":["sachty na vrt", "sachtu na vrt", "na vrt"],
    "https://www.ceskanadrz.cz/precerpavaci-jimky-k-obetonovani/":["precerpavaci jimka k obetonovani"],
    "https://www.ceskanadrz.cz/precerpavaci-jimky/":["precerpavaci", "precerpavack"],
    "https://www.ceskanadrz.cz/cistirny-odpadnich-vod/":["cistirn", "cistick", "cov", "odpadnich vod", "odpadni vody"],
    "https://www.ceskanadrz.cz/jimky/":["jimky", "jimka", "zumpa", "zumpu"],
    "https://www.ceskanadrz.cz/septiky/":["septiky", "septik", "septik"],
    "https://www.ceskanadrz.cz/vodomerne-sachty/":["vodomerne sachty", "vodomerna sachta", "na vodomer"],
    "https://www.ceskanadrz.cz/prislusenstvi-k-nadrzim/":["prislusenstvi", "doplnky"],
    "https://www.ceskanadrz.cz/vsakovani/":["vsakovani", "vsakovaci", "vsak"],
    "https://www.ceskanadrz.cz/dotace-destovka/":["dotace", "destovka dotace", "vyrizeni dotace"],
    "https://www.ceskanadrz.cz/zemni-piskove-filtry/":["piskove filtry", "zemni piskove", "piskovy filtr"],
    "https://www.ceskanadrz.cz/nadrze-na-pitnou-vodu/":["na pitnou vodu", "pitna voda"],
    "https://www.ceskanadrz.cz/kanalizacni-revizni-odberna-sachta/":["kanalizacni sachta", "revizni sachta", "odberna sachta"],
    "https://www.ceskanadrz.cz/technologicke-sachty/":["technologicke sachty", "technologicka sachta"],
    "https://www.ceskanadrz.cz/ukapove-vany/":["ukapove vany", "ukapova vana"],
    "https://www.ceskanadrz.cz/vyrobky-na-miru/":["na miru", "zakazkov", "atyp"],
    
    # 4. INFORMAČNÉ PODSTRÁNKY
    "https://www.ceskanadrz.cz/doprava-platba/":["doprava", "platba", "jak platit", "cena dopravy", "rozvoz", "dobirkou"],
    "https://www.ceskanadrz.cz/obchodni-podminky/":["obchodni podminky", "reklamace", "smlouva"],
    "https://www.ceskanadrz.cz/podminky-ochrany-osobnich-udaju/":["gdpr", "osobni udaje", "ochrana"],
    "https://www.ceskanadrz.cz/poradna-nadrze--jimky--sachty-/":["poradna", "jak vybrat", "rady"],
    "https://www.ceskanadrz.cz/casto-kladene-otazky-faq/":["faq", "casto kladene otazky", "caste dotazy"],
    "https://www.ceskanadrz.cz/o-nas/":["o nas", "kdo jste", "informace o firme", "historie", "zkusenosti", "spolecnost", "ceska nadrz"]
}

def detect_page_section(message: str) -> Optional[str]:
    msg_clean = remove_diacritics(message.lower())
    for url, terms in URL_MAP.items():
        if any(term in msg_clean for term in terms):
            return url
    return None

@app.get("/")
async def health_check():
    return {"status": "Česká nádrž Bot is running", "version": "1.8 (Claude Sonnet)"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions: sessions[session_id] =[]
    
    sessions[session_id].append({"role": "user", "content": request.message})
    
    # --- STRIKTNÉ JAZYKOVÉ INŠTRUKCIE ---
    lang_instruction = "MUSÍŠ odpovídat striktně ČESKY. I kdyby uživatel psal jiným jazykem, ty odpovídej ČESKY."
    if request.language == "sk": lang_instruction = "MUSÍŠ odpovedať striktne SLOVENSKY! Ignoruj jazyk užívateľa a odpovedaj výhradne po slovensky."
    elif request.language == "en": lang_instruction = "You MUST answer strictly in ENGLISH! Ignore the user's language and reply in English only."
    elif request.language == "uk": lang_instruction = "Ти ПОВИНЕН відповідати строго УКРАЇНСЬКОЮ мовою! Ігноруй мову користувача і відповідай лише українською."
    
    system_prompt = (
        f"Jsi zákaznický asistent pro e-shop Česká nádrž.\n\n"
        f"ZDE JSOU TVÉ ZNALOSTI:\n{CESKA_NADRZ_KNOWLEDGE}\n\n"
        "TVÉ HLAVNÍ ÚKOLY A SCÉNÁŘ:\n"
        "1. KROK 1 (DOPTAZOVÁNÍ): Pokud zákazník hledá produkt (např. na zalévání) a neřekne parametry, zeptej se ho (např. 'Jak velkou nádrž zhruba hledáte?').\n"
        "2. KROK 2 (DOPORUČENÍ): Jakmile upřesní požadavek (např. 10m3 na zalévání), nadšeně doporuč '10m3 nádrž na vodu + set ZAHRADA STANDARD'. Vypiš parametry. POZOR: Po doporučení produktu se PŘESTAŇ vyptávat na další detaily!\n"
        "3. KROK 3 (FORMULÁŘ PRO TECHNIKU): Jakmile má zákazník technický dotaz (např. 'jak usadit', 'potřebuji poradit', 'technické detaily'), IHNED ukonči prodej. Řekni PŘESNĚ: 'Tohle je už velmi specifický technický dotaz. Nejlépe vám poradí náš hlavní technik Petr Nováček. Vyplňte prosím tento krátký formulář a Petr se vám ozve.' a NA ÚPLNÝ KONEC PŘIDEJ TAG:[SHOW_CONTACT_FORM]\n"
        "4. KROK 4 (FALLBACK - NENALEZENÝ PRODUKT): Pokud zákazník hledá produkt, rozměr nebo parametr, který NEMÁŠ V DATABÁZI, NESMÍŠ si ho vymýšlet! Řekni přesně toto: 'Bohužel, v mé databázi se mi aktuálně nepodařilo najít tento konkrétní produkt. Můžete ale zkusit vyhledat přímo v příslušné sekci na našem webu, kde určitě najdete to správné řešení.' (Systém uživateli nabídne tlačítko s odkazem do dané sekce).\n\n"
        "PRAVIDLA:\n"
        "- NIKDY nezmiňuj, že jsi AI, bot nebo umělá inteligence. Vystupuj jako skutečný asistent e-shopu.\n"
        "- NIKDY nepoužívej hvězdičky (**) ani formátování.\n"
        f"- {lang_instruction}\n"
    )
    
    messages =[{"role": "system", "content": system_prompt}] + sessions[session_id][-10:]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json"
                },
                # Používame excelentný Anthropic Claude 3.5 Sonnet
                json={"model": "anthropic/claude-3.5-sonnet", "messages": messages, "temperature": 0.2, "max_tokens": 500}
            )
            
            data = response.json()
            assistant_message = data["choices"][0]["message"]["content"]
            
            show_form = False
            msg_lower = assistant_message.lower()
            
            # Bezpečnostná poistka pre formulár
            if "[SHOW_CONTACT_FORM]" in assistant_message or "formulář" in msg_lower or "petr" in msg_lower or "формуляр" in msg_lower or "form" in msg_lower:
                show_form = True
                assistant_message = assistant_message.replace("[SHOW_CONTACT_FORM]", "").strip()
            
            sessions[session_id].append({"role": "assistant", "content": assistant_message})
            detected_url = detect_page_section(request.message)
            
            return ChatResponse(
                response=assistant_message, 
                session_id=session_id, 
                page_section=detected_url,
                show_contact_form=show_form
            )
            
    except Exception as e:
        print(f"Error in /chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
