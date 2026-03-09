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

KEYWORDS = {
    "doprava":["doprava", "dovoz", "rozvoz", "zadarmo", "zdarma", "dodavka", "ridic", "skladani"],
    "kontakt":["kontakt", "telefon", "email", "adresa", "kde vas najdem", "kde vas najdu", "spojeni"],
    "eshop":["eshop", "koupit", "objednat", "cena", "cenik", "produkty", "katalog"],
    "poradce":["vyber", "jakou nadrz", "samonosn", "obetonovan", "dvouplast", "podlozi", "spodni voda"]
}

def detect_page_section(message: str) -> Optional[str]:
    msg_clean = remove_diacritics(message.lower())
    for section, terms in KEYWORDS.items():
        if any(term in msg_clean for term in terms):
            return section
    return None

@app.get("/")
async def health_check():
    return {"status": "Česká nádrž Bot is running", "version": "1.0.beta"}

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
    
    if session_id not in sessions:
        sessions[session_id] = []
    
    sessions[session_id].append({"role": "user", "content": request.message})
    
    lang_instruction = "Odpovídej česky."
    if request.language == "sk": lang_instruction = "VŽDY odpovídej slovensky!"
    elif request.language == "en": lang_instruction = "VŽDY odpovídej anglicky!"
    
    system_prompt = (
        f"Jsi AI nákupní asistent a zákaznická podpora pro e-shop Česká nádrž.\n\n"
        f"ZDE JSOU TVÉ ZNALOSTI:\n{CESKA_NADRZ_KNOWLEDGE}\n\n"
        "TVÉ HLAVNÍ ÚKOLY:\n"
        "1. FAQ: Odpovídat na dotazy ohledně dopravy, platby a kvality.\n"
        "2. NÁKUPNÍ ASISTENT: Ptej se zákazníka na Účel, Objem a Podloží (max 1 otázka naráz).\n"
        "3. EMAIL HANDOFF: Při složitých dotazech si vyžádej email/telefon pro technika Petra.\n\n"
        "PRAVIDLA:\n"
        "- NIKDY nepoužívej hvězdičky (**) ani formátování.\n"
        f"- DŮLEŽITÉ: Zákazník si v menu vybral jazyk. {lang_instruction}\n"
    )
    
    messages =[{"role": "system", "content": system_prompt}] + sessions[session_id][-10:]
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://www.ceskanadrz.cz",
                    "X-Title": "Ceska Nadrz Bot"
                },
                json={
                    "model": "openai/gpt-5-mini", 
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 400
                }
            )
            
            data = response.json()
            assistant_message = data["choices"][0]["message"]["content"]
            
            sessions[session_id].append({"role": "assistant", "content": assistant_message})
            detected_section = detect_page_section(request.message)
            
            return ChatResponse(
                response=assistant_message,
                session_id=session_id,
                page_section=detected_section
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal Server Error")
