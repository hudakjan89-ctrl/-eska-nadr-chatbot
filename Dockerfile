FROM python:3.11-slim

WORKDIR /app

# Inštalácia závislostí (CPU-only torch — bez 1.5 GB CUDA balíkov)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=300 \
      torch==2.3.1 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir --default-timeout=300 -r requirements.txt

# Stiahnutie AI modelu pre embedingy počas buildu (Ušetrí čas pri reštarte!)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# Kopírovanie celého projektu
COPY . .

EXPOSE 8000

# Spustenie aplikácie (S pridanou medzerou po CMD)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
