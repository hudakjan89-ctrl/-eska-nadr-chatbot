FROM python:3.11-slim

# Nastavenie pracovného adresára
WORKDIR /app

# Kopírovanie a inštalácia závislostí
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopírovanie celého projektu (vrátane zložky static)
COPY . .

# Port pre Coolify
EXPOSE 8000

# Spustenie aplikácie
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
