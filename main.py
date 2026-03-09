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
        "1. NÁKUPNÍ ASISTENT: Ptej se zákazníka na Účel, Objem a Podloží. Můžeš doporučit kategorie: 'Nádrže k obetonování', 'Šachty na vrt', 'Přečerpávací jímky', 'Čistírny odpadních vod'. Systém pak uživateli automaticky nabídne odkaz, takže ty jen doplň slovní doporučení.\n"
        "2. FAQ: Odpovídej na dotazy k dopravě (zdarma nad určené produkty), platbě (nelze kartou u řidiče) a kontaktům.\n"
        "3. EMAIL HANDOFF: Při velmi složitých dotazech si vyžádej email/telefon a případ předej techniku Petrovi Nováčkovi.\n\n"
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
                json={"model": "openai/gpt-5.2-pro", "messages": messages, "temperature": 0.3, "max_tokens": 400}
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
