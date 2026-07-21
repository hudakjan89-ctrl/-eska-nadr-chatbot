# Testovanie chatbota — produkčný report

Automatizované testy proti `https://nadrz.eniq.eu/chat`.

## Spustenie testov

```bash
python3 scripts/prod_chat_test.py
```

Výstup: `data/chatbot_test_report.json`

## Posledný beh (pred merge search fix na main)

**Dátum:** 2026-07-21  
**Výsledok:** 17/18 scenárov (94.4%) + 8/8 extra scenárov

### ✅ Funguje správne

| Scenár | Výsledok |
|--------|----------|
| Retenční nádrž deset kubíků | Ponúka 10m³ nádrž |
| Retencni nadrz 10m? (typo) | Interpretuje ako 10m³ |
| 10m3 podzemní nádrž | Samonosná + obetonování s cenami |
| Multi-turn: nádrž → podzemní | Podzemné varianty |
| Dešťovka 15m3 jílovitá půda | 15m³ samonosná + rada o dvouplášťové |
| Dešťovka 10 kubíků | 10m³ nádrž (nie „nemáme") |
| Hlásič naplnění | Zvukový + optický signál, varianty káblov |
| Jímka 10m3 k obetonování | Produkt + cena 42 338 Kč |
| Extrémne zložitý dotaz | Nádrž + septik + hlásič |
| Pozdrav → Retencni nadrz 10m | Žiadny 500 error |
| Dotace dešťovka | Kontaktný formulár |
| Doprava | Odpoveď o doprave |

### ⚠️ Čiastočné / kvalitatívne problémy (aj pri PASS)

| Problém | Príklad |
|---------|---------|
| Chýba 3. variant (dvouplášťová) | „10m3 podzemní" — len 2 varianty |
| Zlá rada o spodnej vode | Obetonování označené ako vhodné pri vysokej spodnej vode |
| Pitná vs dešťovka | URL často smeruje na pitnou vodu aj pri dešťovke |
| Kalové čerpadlo | Bot tvrdí „nemáme" hoci PSP9-7.5 je v feede |

### ❌ Zlyhanie

| Scenár | Dôvod |
|--------|-------|
| „Potřebuji podzemní" → „10m3" | Bot sa pýta na účel namiesto ponuky produktov |

## Scenáre na manuálne overenie po redeploy

Po nasadení merge `4a79110` + prompt fixov overiť:

1. `Hledám kalové čerpadlo s vestavěným plovákem` → Blue Line PSP9-7.5
2. `10m3 podzemní nádrž` → všetky 3 varianty (samonosná, obetonování, dvouplášťová)
3. `Potřebuji podzemní` + `10m3` → ponúkne modely bez ďalšieho vyptávania
4. Health `GET /` → `products_indexed` ≈ 1020

## Riešenie problémov zo štartu

### `Knowledge base pripravena (0 sekcii)`

Príčina: súbor `/data/knowledge_base.md` existuje, ale je prázdny alebo nemá formát `### Nadpis`.

Riešenie (od commit fix-qdrant-knowledge-startup):
- Pri štarte sa automaticky stiahne z GitHubu ak cache nie je platná
- Health endpoint ukáže `knowledge_sections` a `knowledge_index_ready`

Manuálne:
```bash
curl -X POST https://nadrz.eniq.eu/admin/reindex-knowledge \
  -H "x-dashboard-api-key: VÁŠ_KĽÚČ"
```

### `Qdrant DB is already accessed by another instance`

Príčina: dva procesy/kontajnery pristupujú k `/data/qdrant_db` naraz (typicky pri redeployi).

Riešenie:
- Uvicorn beží s `--workers 1`
- Qdrant klient sa inicializuje lazy s retry (až 8 pokusov)
- Pri deployi počkajte kým starý kontajner skončí pred spustením nového
