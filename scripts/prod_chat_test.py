#!/usr/bin/env python3
"""Production chatbot stress test — saves results to JSON report."""
import json
import re
import time
import uuid
import urllib.request
from datetime import datetime, timezone

BASE_URL = "https://nadrz.eniq.eu"
TOKEN = "nadrz-secure-2026"
REPORT_PATH = "data/chatbot_test_report.json"

# Each scenario: name, messages (multi-turn), checks
SCENARIOS = [
    {
        "id": "retencni_10m3",
        "name": "Retenční nádrž 10m3 (víkendový fail)",
        "messages": ["retenční nádrž deset kubíků"],
        "must_contain_any": ["10", "m³", "m3", "nádrž", "dešťov"],
        "must_not_contain": ["nemám v aktuální nabídce", "nemáme podzemní", "nepodařilo načíst"],
    },
    {
        "id": "retencni_10m_typo",
        "name": "Retenční nádrž 10m (chybí 3)",
        "messages": ["Retencni nadrz 10m?"],
        "must_contain_any": ["10", "m³", "m3", "nádrž"],
        "must_not_contain": ["nepodařilo načíst", "nemám v aktuální nabídce dostupných dat"],
    },
    {
        "id": "podzemni_10m3",
        "name": "10m3 podzemní — 3 varianty",
        "messages": ["10m3 podzemní nádrž"],
        "must_contain_any": ["samonos", "obetonov", "dvouplášť", "dvouplast"],
        "must_not_contain": ["nemáme podzemní", "jen nadzemní", "nepodařilo načíst"],
    },
    {
        "id": "podzemni_followup",
        "name": "Multi-turn: nádrž → podzemní",
        "messages": [
            "potřebuji nádrž na vodu 10 kubíků",
            "podzemní",
        ],
        "must_contain_any": ["samonos", "obetonov", "dvouplášť", "dvouplast", "podzem"],
        "must_not_contain": ["nemáme podzemní", "jen nadzemní volně stojící"],
    },
    {
        "id": "destovka_15m_jilovita",
        "name": "Dešťovka 15m3 jílovitá půda (frustrovaný zákazník)",
        "messages": [
            "hledam nadrz na vodu do castečne jilovite pudy minimalne 12m3",
            "destova voda 15m3 jílovitá půda",
        ],
        "must_contain_any": ["15", "m³", "m3", "nádrž", "samonos", "dešťov"],
        "must_not_contain": ["nemám nyní k dispozici konkrétní", "obchod@ceskanadrz.cz a kolegové vám obratem"],
    },
    {
        "id": "destovka_10_kubiku",
        "name": "Dešťovka 10 kubíků (mylil pitnou)",
        "messages": ["potřebuji nádrž na dešťovou vodu 10 kubíků"],
        "must_contain_any": ["10", "m³", "m3", "nádrž", "dešťov", "samonos"],
        "must_not_contain": ["nemám k dispozici konkrétní nádrž na dešťovou vodu", "pouze 10m3 samonosnou nádrž na pitnou"],
    },
    {
        "id": "hlasic_naplneni",
        "name": "Hlásič naplnění — technický dotaz",
        "messages": ["Hele ten hlásič naplnění jímky, nádrže či septiku je jaký, jak to hlásí zvukem?"],
        "must_contain_any": ["hlásič", "hlasic", "signaliz", "zvuk", "světl", "naplněn"],
        "must_not_contain": ["nemám v podkladech k dispozici", "nepodařilo načíst"],
    },
    {
        "id": "kalove_cerpadlo",
        "name": "Kalové čerpadlo s plovákem",
        "messages": ["Hledám kalové čerpadlo s vestavěným plovákem"],
        "must_contain_any": ["Blue Line", "PSP", "2965", "čerpadl"],
        "must_not_contain": ["nemám v nabízeném sortimentu", "nejsou hlavní sortiment"],
    },
    {
        "id": "septik_4osoby",
        "name": "Septik pro 4 osoby",
        "messages": ["potřebuji septik pro 4 osoby pod zem"],
        "must_contain_any": ["septik", "4", "osob", "m³", "m3", "samonos"],
        "must_not_contain": ["nemáme", "nepodařilo načíst"],
    },
    {
        "id": "jimka_10m3",
        "name": "Jímka 10m3",
        "messages": ["jímka 10 kubíků k obetonování"],
        "must_contain_any": ["jímk", "jimk", "10", "obetonov"],
        "must_not_contain": ["nemám", "nepodařilo načíst"],
    },
    {
        "id": "nadzemni_ne_preferovat",
        "name": "Explicitně podzemní — ne nadzemní",
        "messages": ["Potřebuji podzemní", "10m3"],
        "must_contain_any": ["samonos", "obetonov", "dvouplášť", "podzem"],
        "must_not_contain": ["nemáme podzemní", "jen nadzemní"],
    },
    {
        "id": "sachta_vrt",
        "name": "Šachta na vrt",
        "messages": ["potřebuji šachtu na vrt k obetonování"],
        "must_contain_any": ["šacht", "sacht", "vrt", "obetonov"],
        "must_not_contain": ["nepodařilo načíst"],
    },
    {
        "id": "dotace_destovka",
        "name": "Dotace dešťovka",
        "messages": ["jak získám dotaci na nádrž na dešťovou vodu?"],
        "must_contain_any": ["dotac", "kontakt", "specialista", "formulář"],
        "must_not_contain": ["nepodařilo načíst"],
    },
    {
        "id": "extreme_mixed",
        "name": "Extrémne zložitý dotaz",
        "messages": [
            "Dobrý den, stavím RD na jílovité půdě se spodní vodou, potřebuji podzemní nádrž na dešťovou vodu cca 10m, septik pro 5 osob a hlásič naplnění. Co doporučíte a jaké jsou ceny?",
        ],
        "must_contain_any": ["nádrž", "septik", "samonos", "dvouplášť", "obetonov", "10", "hlásič"],
        "must_not_contain": ["nemáme podzemní", "nepodařilo načíst", "nemám v podkladech"],
    },
    {
        "id": "greeting_then_product",
        "name": "Pozdrav → produkt (500 error scenár)",
        "messages": ["Ahoj", "Retencni nadrz 10m?"],
        "must_contain_any": ["10", "m³", "m3", "nádrž"],
        "must_not_contain": ["nepodařilo načíst"],
    },
    {
        "id": "pitna_vs_destovka",
        "name": "Pitná vs dešťovka — explicitne dešťovka",
        "messages": ["chci nádrž 8m3 na zalévání zahrady pod zem"],
        "must_contain_any": ["8", "m³", "m3", "nádrž", "samonos", "dešťov", "zalév"],
        "must_not_contain": ["pitnou vodu", "nemám k dispozici"],
    },
    {
        "id": "dvouplastova_spodni_voda",
        "name": "Spodní voda → dvouplášťová",
        "messages": ["10m3 nádrž na dešťovou vodu, mám vysokou spodní vodu"],
        "must_contain_any": ["dvouplášť", "dvouplast", "spodní", "10"],
        "must_not_contain": ["k obetonování je vhodná pro vysokou spodní vodu", "nemáme"],
    },
    {
        "id": "cena_doprava",
        "name": "Doprava a platba",
        "messages": ["kolik stojí doprava nádrže?"],
        "must_contain_any": ["doprav", "zdarma", "Kč", "objednáv"],
        "must_not_contain": ["nepodařilo načíst"],
    },
]


def _request(method: str, url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[int, str]:
    import subprocess
    cmd = ["curl", "-s", "-w", "\n__HTTP_CODE__:%{http_code}", "-X", method, url]
    hdrs = headers or {}
    for k, v in hdrs.items():
        cmd.extend(["-H", f"{k}: {v}"])
    if data is not None:
        cmd.extend(["-d", data.decode("utf-8")])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    output = proc.stdout
    if "__HTTP_CODE__:" in output:
        body, _, code_part = output.rpartition("\n__HTTP_CODE__:")
        code = int(code_part.strip())
        return code, body
    return proc.returncode, output


def chat(session_id: str, message: str) -> dict:
    payload = json.dumps({
        "message": message,
        "session_id": session_id,
        "language": "cs",
    }).encode("utf-8")
    code, body = _request(
        "POST",
        f"{BASE_URL}/chat",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-nadrz-token": TOKEN,
            "User-Agent": "CeskaNadrzChatTest/1.0",
        },
    )
    if code != 200:
        raise RuntimeError(f"HTTP {code}: {body[:300]}")
    return json.loads(body)


DENIAL_PHRASES = [
    "nemám v aktuální nabídce",
    "nemáme podzemní",
    "nemám v podkladech",
    "nepodařilo načíst",
    "nemám v nabízeném sortimentu",
    "v nabídce, kterou vidím, konkrétní model",
    "kalová čerpadla nejsou hlavní sortiment",
    "nemám nyní k dispozici konkrétní",
]


def evaluate(response_text: str, checks: dict) -> dict:
    text_lower = response_text.lower()
    failures = []

    for phrase in checks.get("must_not_contain", []):
        if phrase.lower() in text_lower:
            failures.append(f"MUST_NOT contain '{phrase}'")

    for phrase in DENIAL_PHRASES:
        if phrase.lower() in text_lower:
            failures.append(f"DENIAL detected: '{phrase}'")

    must_any = checks.get("must_contain_any", [])
    if must_any and not any(p.lower() in text_lower for p in must_any):
        failures.append(f"MUST contain any of: {must_any}")

    must_all = checks.get("must_contain_all", [])
    for phrase in must_all:
        if phrase.lower() not in text_lower:
            failures.append(f"MUST contain '{phrase}'")

    truncated = bool(re.search(r'\b(kon|zelen|vod|řeš|doporuč|vhodného)\s*$', response_text.strip(), re.I))
    if truncated:
        failures.append("Response appears TRUNCATED (ends mid-word)")

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "response_length": len(response_text),
    }


def run_scenario(scenario: dict) -> dict:
    session_id = str(uuid.uuid4())
    turns = []
    last_response = ""

    for msg in scenario["messages"]:
        t0 = time.time()
        try:
            result = chat(session_id, msg)
            elapsed = round(time.time() - t0, 2)
            last_response = result.get("response", "")
            turns.append({
                "user": msg,
                "bot": last_response,
                "page_section": result.get("page_section"),
                "image_url": result.get("image_url"),
                "show_contact_form": result.get("show_contact_form"),
                "elapsed_s": elapsed,
                "error": None,
            })
        except Exception as exc:
            turns.append({
                "user": msg,
                "bot": "",
                "error": str(exc),
                "elapsed_s": round(time.time() - t0, 2),
            })
            last_response = ""
            break
        time.sleep(1.5)

    evaluation = evaluate(last_response, scenario) if last_response else {
        "passed": False,
        "failures": ["No bot response (error or empty)"],
        "response_length": 0,
    }

    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "session_id": session_id,
        "turns": turns,
        "evaluation": evaluation,
        "passed": evaluation["passed"],
    }


def main():
    print(f"=== Production chatbot test: {BASE_URL} ===\n")
    code, body = _request("GET", f"{BASE_URL}/", headers={"User-Agent": "CeskaNadrzChatTest/1.0"})
    health = json.loads(body) if code == 200 else {"error": body, "http_code": code}
    print(f"Health: {json.dumps(health, ensure_ascii=False)}\n")

    results = []
    passed = 0
    failed = 0

    for i, scenario in enumerate(SCENARIOS, 1):
        print(f"[{i}/{len(SCENARIOS)}] {scenario['name']}...")
        result = run_scenario(scenario)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        if result["passed"]:
            passed += 1
        else:
            failed += 1
        print(f"  -> {status}")
        if not result["passed"]:
            for f in result["evaluation"]["failures"]:
                print(f"     ! {f}")
            if result["turns"]:
                last = result["turns"][-1]
                preview = (last.get("bot") or last.get("error", ""))[:200]
                print(f"     Response: {preview}...")
        print()

    report = {
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "health": health,
        "summary": {
            "total": len(SCENARIOS),
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{100 * passed / len(SCENARIOS):.1f}%",
        },
        "scenarios": results,
    }

    import os
    os.makedirs("data", exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=" * 60)
    print(f"SUMMARY: {passed}/{len(SCENARIOS)} passed ({report['summary']['pass_rate']})")
    print(f"Report saved: {REPORT_PATH}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
