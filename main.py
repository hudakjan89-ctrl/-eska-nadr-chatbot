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

URL_MAP = {
    "https://www.ceskanadrz.cz/10m3-nadrz-na-vodu-set-zahrada-standard/":["10m3", "10 kubiku", "10000", "set zahrada", "zahrada standard", "na zahradu", "zalevani", "zalevat"],
    "https://www.ceskanadrz.cz/1m3-kruhova-nadrz-na-vodu-k-obetonovani/":["1m3", "1 kubik", "mala nadrz"],
    "https://www.ceskanadrz.cz/sachta-na-vrt-mini-k-obetonovani-2/":["mini sachta", "sachta mini", "mini sachtu"],
    "https://www.ceskanadrz.cz/cisticka-odpadnich-vod-pro-2-5-osob-at6/":["at6", "pro 2", "pro 5", "pro 4", "at 6"],
    "https://www.ceskanadrz.cz/nadrze-na-vodu-k-obetonovani/":["nadrze k obetonovani", "nadrz k obetonovani", "obetonovani"],
    "https://www.ceskanadrz.cz/sachta-na-vrt-k-obetonovani/":["sachta na vrt", "sachtu na vrt", "sachty na vrt"],
    "https://www.ceskanadrz.cz/precerpavaci-jimky-k-obetonovani/":["precerpavaci", "precerpavack"],
    "https://www.ceskanadrz.cz/cistirny-odpadnich-vod/": ["cistirn", "cistick", "cov", "odpadnich vod"]
}

def detect_page_section(message: str) -> Optional[str]:
    msg_clean = remove_diacritics(message.lower())
    for url, terms in URL_MAP.items():
        if any(term in msg_clean for term in terms):
            return url
    return None

@app.get("/")
async def health_check():
    return {"status": "Česká nádrž Bot is running", "version": "1.4"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions: sessions[session_id] =[]
    
    sessions[session_id].append({"role": "user", "content": request.message})
    
    lang_instruction = "Odpovídej česky."
    if request.language == "sk": lang_instruction = "VŽDY odpovídej slovensky!"
    elif request.language == "en": lang_instruction = "VŽDY odpovídej anglicky!"
    
    system_prompt = (
        f"Jsi AI nákupní asistent pro e-shop Česká nádrž.\n\n"
        f"ZDE JSOU TVÉ ZNALOSTI:\n{CESKA_NADRZ_KNOWLEDGE}\n\n"
        "TVÉ HLAVNÍ ÚKOLY:\n"
        "1. DEMO SCÉNÁŘ 1 (PRODEJ): Pokud zákazník hledá nádrž na zalévání zahrady, VŽDY mu doporuč '10m3 nádrž na vodu + set ZAHRADA STANDARD'. Vypiš parametry a zeptej se, zda se chce podívat.\n"
        "2. DEMO SCÉNÁŘ 2 (100% FORMULÁŘ): Jakmile má zákazník technický dotaz (např. 'můžete mi poradit', 'říct více', 'jak to nainstalovat', 'usazení'), IHNED ukonči prodej. Řekni PŘESNĚ toto: 'Tohle je specifičtější dotaz, se kterým vám nejlépe poradí náš majitel a technik Petr Nováček. Vyplňte prosím tento krátký formulář a Petr se vám ozve.' a NA ÚPLNÝ KONEC ZPRÁVY PŘIDEJ TAG: [SHOW_CONTACT_FORM]\n"
        "3. POKRAČOVÁNÍ CHATU: Pokud ti systém pošle zprávu, že zákazník odeslal kontaktní údaje, poděkuj mu, řekni, že to Petrovi předáváš a zeptej se, zda mu můžeš pomoci s něčím dalším.\n"
        "4. BĚŽNÝ REŽIM: U jiných dotazů se ptej na Účel, Objem a Podloží a odpovídej na dopravu/platbu.\n\n"
        "PRAVIDLA:\n"
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
                # Temperature znížená na 0.2 = Bot prestane byť kreatívny a presne dodrží inštrukciu
                json={"model": "openai/gpt-4o-mini", "messages": messages, "temperature": 0.2, "max_tokens": 400}
            )
            
            data = response.json()
            assistant_message = data["choices"][0]["message"]["content"]
            
            # --- 100% BEZPEČNOSTNÁ POISTKA PRE FORMULÁR ---
            show_form = False
            msg_lower = assistant_message.lower()
            
            # Ak bot pridal tag, ALEBO spomenul formulár, ALEBO spomenul Petra = VŽDY ukážeme formulár!
            if "[SHOW_CONTACT_FORM]" in assistant_message or "formulář" in msg_lower or "petr" in msg_lower:
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
