# Deploy na Contabo — trvalá história chatov pre Eniq portál

## Problém

História chatov pre Eniq portál sa ukladá do súboru **SQLite `analytics.db`**. Pri redeployi sa kontajner prepisuje a súbor sa stratí, ak nie je na trvalom disku.

Chatbot **nemusí** pamätať konverzáciu po odchode zákazníka z webu. Dôležité je len, aby **portál** videl všetky minulé chaty.

## Čo treba spraviť na serveri

### 1. Nájsť starú databázu (obnova histórie)

Pred redeployom skús nájsť existujúci `analytics.db` na serveri:

```bash
# Hľadanie kdekoľvek na serveri
sudo find / -name "analytics.db" 2>/dev/null

# Typické miesta
ls -la /root/-eska-nadr-chatbot/analytics.db
ls -la /root/-eska-nadr-chatbot/data/analytics.db
ls -la /var/lib/docker/volumes/*/  2>/dev/null
docker ps -a
docker volume ls
```

Ak nájdeš neprázdny `analytics.db` (väčší ako pár KB), **zálohuj ho**:

```bash
sudo cp /cesta/k/analytics.db /root/analytics.db.backup
```

### 2. Trvalý priečinok pre dáta

```bash
sudo mkdir -p /var/lib/ceskanadrz-chatbot/data
sudo chown -R $(whoami):$(whoami) /var/lib/ceskanadrz-chatbot
```

Ak existuje záloha starej DB, obnov ju **pred** štartom aplikácie:

```bash
cp /root/analytics.db.backup /var/lib/ceskanadrz-chatbot/data/analytics.db
```

### 3. Deploy cez Docker Compose (odporúčané)

V priečinku projektu po `git pull`:

Uprav `docker-compose.yml` tak, aby mountoval trvalý priečinok na hoste:

```yaml
services:
  chatbot:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      DATA_DIR: /data
    volumes:
      - /var/lib/ceskanadrz-chatbot/data:/data
    restart: unless-stopped
```

Potom:

```bash
cd /cesta/k/-eska-nadr-chatbot
git pull origin main
docker compose down
docker compose up -d --build
```

### 4. Overenie po deployi

```bash
# Súbor musí existovať a rásť po nových chatoch
ls -lh /var/lib/ceskanadrz-chatbot/data/analytics.db

# Počet správ v DB
sqlite3 /var/lib/ceskanadrz-chatbot/data/analytics.db "SELECT COUNT(*) FROM messages;"

# Logy aplikácie — hľadaj riadok Analytics DB: /data/analytics.db
docker compose logs --tail=50
```

### 5. Ak beží bez Dockeru (priamo uvicorn)

V `.env` na serveri:

```
DATA_DIR=/var/lib/ceskanadrz-chatbot/data
```

Reštart služby po `git pull`.

## Dôležité

- **Bez volume/trvalého priečinka sa história pri každom redeployi stratí.**
- Ak sa starý `analytics.db` na serveri nenájde, história z minulých redeployov **sa nedá obnoviť** — dáta boli vymazané s kontajnerom.
- Od tohto deployu ďalej sa nové chaty už nemazú (ak je volume správne namontovaný).

## Env premenné (voliteľné)

| Premenná | Predvolená | Popis |
|----------|------------|-------|
| `DATA_DIR` | `data` (lokálne), `/data` (Docker) | Priečinok pre analytics.db a qdrant_db |
| `ANALYTICS_DB_PATH` | `{DATA_DIR}/analytics.db` | Priama cesta k SQLite súboru |
