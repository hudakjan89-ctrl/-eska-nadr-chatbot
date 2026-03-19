FROM python:3.11-slim

WORKDIR /app

# Inštalácia závislostí
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stiahnutie AI modelu pre embedingy počas buildu (Ušetrí čas pri reštarte!)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# Kopírovanie celého projektu
COPY . .

EXPOSE 8000

# Spustenie aplikácie (S pridanou medzerou po CMD)
CMD["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
