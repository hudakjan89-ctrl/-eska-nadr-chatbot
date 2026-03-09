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

def remove_diacritics(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')

# ==========================================
# OPRAVENÉ MAPOVANIE URL ADRIES 
# (Produkty musia byť hore, kategórie dole!)
# ==========================================
URL_MAP = {
    # ---> PRIDANÝ BETA PRODUKT <---
    "https://www.ceskanadrz.cz/10m3-nadrz-na-vodu-set-zahrada-standard/":["10m3", "10 kubiku", "10000", "set zahrada", "zahrada standard", "na zahradu", "zalevani", "zalevat"],
    # 1. NAJPRV ŠPECIFICKÉ PRODUKTY (Ak zákazník uvedie presný detail)
    "https://www.ceskanadrz.cz/1m3-kruhova-nadrz-na-vodu-k-obetonovani/": ["1m3", "1 kubik", "mala nadrz"],
    "https://www.ceskanadrz.cz/sachta-na-vrt-mini-k-obetonovani-2/": ["mini sachta", "sachta mini", "mini sachtu"],
    "https://www.ceskanadrz.cz/cisticka-odpadnich-vod-pro-2-5-osob-at6/":["at6", "pro 2", "pro 5", "pro 4", "at 6"],
    
    # 2. AŽ POTOM VŠEOBECNÉ SEKCIE (Ak nezadal nič špecifické, pošleme ho do kategórie)
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
    return {"status": "Česká nádrž Bot is running", "version": "1.2"}

@app.get("/test", response_class=HTMLResponse)
async def test_page():
    return """
    <!DOCTYPE html>
    <html lang="cs">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Česká nádrž Bot Test</title>
        <style>body { margin: 0; padding: 0; height: 100vh; background: #e5e7eb; }</style>
    </head>
    <body>
        <script src="/static/js/chat.js"></script>
    </body>
    </html>
    """

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    if session_id not in sessions: sessions[session_id] =[]
    
    sessions[session_id].append({"role": "user", "content": request.message})
    
    lang_instruction = "Odpovídej česky."
    if request.language == "sk": lang_instruction = "VŽDY odpovídej slovensky!"
    elif request.language == "en": lang_instruction = "VŽDY odpovídej anglicky!"
    
    system_prompt = (
        f"Jsi AI nákupní asistent a zákaznická podpora pro e-shop Česká nádrž.\n\n"
        f"ZDE JSOU TVÉ ZNALOSTI (Databáze firmy):\n{CESKA_NADRZ_KNOWLEDGE}\n\n"
        "TVÉ HLAVNÍ ÚKOLY:\n"
        "1. DEMO SCÉNÁŘ 1 (PRODEJ): Pokud zákazník hledá nádrž na dešťovou vodu, na zalévání zahrady, nebo neví co vybrat na zahradu, VŽDY mu jako první nadšeně doporuč '10m3 nádrž na vodu + set ZAHRADA STANDARD'. Vypiš mu 2-3 hlavní parametry (objem 10000 l, záruka 2 roky, vnější průměr 2600 mm) a zeptej se ho, zda se na tento set chce podívat.\n"
        "2. DEMO SCÉNÁŘ 2 (EMAIL HANDOFF): Pokud se zákazník následně zeptá 'můžete mi o tom říct více?', 'můžete mi nějak poradit?', nebo chce detaily k instalaci, IHNED ukonči prodejní fázi. Řekni, že s detailním technickým poradenstvím a specifiky mu nejlépe pomůže přímo majitel a hlavní technik Petr Nováček. VŽDY mu napiš, ať se ozve na e-mail info@ceskanadrz.cz nebo zavolá na 723 045 274.\n"
        "3. NÁKUPNÍ ASISTENT A FAQ: U jiných dotazů se ptej na Účel, Objem a Podloží a odpovídej na dopravu/platbu.\n\n"
        "PRAVIDLA:\n"
        "- NIKDY nepoužívej hvězdičky (**) ani formátování.\n"
        f"- DŮLEŽITÉ: {lang_instruction}\n"
    )
    
    messages =[{"role": "system", "content": system_prompt}] + sessions[session_id][-10:]
    
    try:
        if not OPENROUTER_API_KEY:
            raise Exception("API Key is missing.")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://nadrz.eniq.eu",
                    "X-Title": "Ceska Nadrz Bot"
                },
                json={"model": "openai/o4-mini", "messages": messages, "temperature": 0.3, "max_tokens": 400}
            )
            
            if response.status_code != 200:
                print(f"OpenRouter Error: {response.text}")
                raise Exception("OpenRouter API Error")
            
            data = response.json()
            assistant_message = data["choices"][0]["message"]["content"]
            
            sessions[session_id].append({"role": "assistant", "content": assistant_message})
            detected_url = detect_page_section(request.message)
            
            return ChatResponse(response=assistant_message, session_id=session_id, page_section=detected_url)
            
    except Exception as e:
        print(f"Error in /chat: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
