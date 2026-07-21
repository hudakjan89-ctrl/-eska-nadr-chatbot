import os
import base64
import logging
import httpx

logger = logging.getLogger("ceska_nadrz.knowledge_github")

KNOWLEDGE_FILE_NAME = "knowledge_base.md"
_default_data_dir = os.getenv("DATA_DIR", "").strip()
KNOWLEDGE_LOCAL_PATH = os.getenv(
    "KNOWLEDGE_LOCAL_PATH",
    os.path.join(_default_data_dir, KNOWLEDGE_FILE_NAME) if _default_data_dir else KNOWLEDGE_FILE_NAME,
)
KNOWLEDGE_SEED_PATH = os.getenv("KNOWLEDGE_SEED_PATH", "knowledge_seed.md")

MIN_KNOWLEDGE_BYTES = 200


def _github_settings() -> dict:
    return {
        "token": os.getenv("GITHUB_TOKEN", "").strip(),
        "owner": os.getenv("GITHUB_OWNER", "hudakjan89-ctrl").strip(),
        "repo": os.getenv("GITHUB_REPO", "ceskanadrz-knowledge").strip(),
        "branch": os.getenv("GITHUB_BRANCH", "main").strip() or "main",
    }


def is_github_configured() -> bool:
    cfg = _github_settings()
    return bool(cfg["token"] and cfg["owner"] and cfg["repo"])


def github_token_hint() -> str:
    token = _github_settings()["token"]
    if not token:
        return "GITHUB_TOKEN nie je nastavený"
    if len(token) < 10:
        return "GITHUB_TOKEN je príliš krátky (skontroluj env na serveri)"
    return f"GITHUB_TOKEN je nastavený ({token[:4]}...{token[-4:]})"


def _github_auth_headers(token: str) -> list[dict]:
    cleaned = token.strip()
    return [
        {
            "Authorization": f"Bearer {cleaned}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        {
            "Authorization": f"token {cleaned}",
            "Accept": "application/vnd.github.v3+json",
        },
    ]


def knowledge_cache_path() -> str:
    return KNOWLEDGE_LOCAL_PATH


def knowledge_cache_size() -> int:
    try:
        return os.path.getsize(KNOWLEDGE_LOCAL_PATH) if os.path.exists(KNOWLEDGE_LOCAL_PATH) else 0
    except OSError:
        return 0


def knowledge_cache_usable() -> bool:
    return knowledge_cache_size() >= MIN_KNOWLEDGE_BYTES


def fetch_knowledge_from_github() -> dict:
    cfg = _github_settings()
    token = cfg["token"]
    owner = cfg["owner"]
    repo = cfg["repo"]
    branch = cfg["branch"]

    if not is_github_configured():
        raise RuntimeError("GitHub knowledge sync is not configured (GITHUB_TOKEN/OWNER/REPO).")

    if not KNOWLEDGE_LOCAL_PATH.endswith(KNOWLEDGE_FILE_NAME) or ".." in KNOWLEDGE_LOCAL_PATH:
        raise RuntimeError(
            f"KNOWLEDGE_LOCAL_PATH must end with {KNOWLEDGE_FILE_NAME} and must not contain path traversal."
        )

    url = (
        f"https://api.github.com/repos/{owner}/{repo}/contents/"
        f"{KNOWLEDGE_FILE_NAME}?ref={branch}"
    )

    response = None
    try:
        with httpx.Client(timeout=60.0) as client:
            for headers in _github_auth_headers(token):
                response = client.get(url, headers=headers)
                if response.status_code != 401:
                    break
    except httpx.HTTPError as exc:
        raise RuntimeError(f"GitHub fetch failed: {exc}") from exc

    if response.status_code == 404:
        raise RuntimeError(
            f"{KNOWLEDGE_FILE_NAME} not found in {owner}/{repo}@{branch}."
        )
    if response.status_code == 401:
        raise RuntimeError(
            "GitHub API error (401): Bad credentials. "
            "Skontroluj GITHUB_TOKEN na serveri bota — musí byť platný read token "
            f"s prístupom k {owner}/{repo}."
        )
    if response.status_code != 200:
        raise RuntimeError(f"GitHub API error ({response.status_code}): {response.text[:300]}")

    payload = response.json()
    encoded = payload.get("content", "")
    if not encoded:
        raise RuntimeError("GitHub response did not include file content.")

    content = base64.b64decode(encoded).decode("utf-8")
    os.makedirs(os.path.dirname(KNOWLEDGE_LOCAL_PATH) or ".", exist_ok=True)
    with open(KNOWLEDGE_LOCAL_PATH, "w", encoding="utf-8") as handle:
        handle.write(content)

    byte_count = len(content.encode("utf-8"))
    logger.info(
        "Stiahnutý %s z %s/%s@%s (%d bajtov, sha=%s).",
        KNOWLEDGE_FILE_NAME,
        owner,
        repo,
        branch,
        byte_count,
        (payload.get("sha") or "")[:12],
    )

    return {
        "commit_sha": payload.get("sha"),
        "file_path": KNOWLEDGE_FILE_NAME,
        "branch": branch,
        "target": f"{owner}/{repo}",
        "bytes": byte_count,
    }


def sync_knowledge_base(fetch_remote: bool = True) -> int:
    from database import load_and_upsert_knowledge

    if fetch_remote and is_github_configured():
        fetch_knowledge_from_github()
    elif not knowledge_cache_usable():
        logger.warning(
            "GitHub nie je nakonfigurovaný a lokálny %s neexistuje alebo je prázdny — knowledge base sa nenačíta.",
            KNOWLEDGE_LOCAL_PATH,
        )
        return 0

    sections = load_and_upsert_knowledge(KNOWLEDGE_LOCAL_PATH)
    if sections == 0:
        logger.error(
            "Knowledge súbor %s (%d B) sa nepodarilo rozparsovať na sekcie.",
            KNOWLEDGE_LOCAL_PATH,
            knowledge_cache_size(),
        )
    return sections


def load_seed_knowledge() -> int:
    from database import load_and_upsert_knowledge

    if not os.path.exists(KNOWLEDGE_SEED_PATH):
        logger.warning("Seed knowledge súbor neexistuje: %s", KNOWLEDGE_SEED_PATH)
        return 0
    logger.info("Načítavam záložnú knowledge base zo seed súboru: %s", KNOWLEDGE_SEED_PATH)
    return load_and_upsert_knowledge(KNOWLEDGE_SEED_PATH)


def load_knowledge_on_startup() -> int:
    """Načíta knowledge z cache; ak je prázdna/neplatná, stiahne z GitHubu; inak seed."""
    from database import load_and_upsert_knowledge, refresh_knowledge_section_count

    if knowledge_cache_usable():
        logger.info(
            "Načítavam knowledge base z lokálnej cache: %s (%d B)",
            KNOWLEDGE_LOCAL_PATH,
            knowledge_cache_size(),
        )
        sections = load_and_upsert_knowledge(KNOWLEDGE_LOCAL_PATH)
        if sections > 0:
            return sections
        logger.warning(
            "Lokálna knowledge cache existuje, ale neobsahuje platné sekcie (formát ### Nadpis)."
        )

    if is_github_configured():
        logger.info("Knowledge cache chýba alebo je neplatná — sťahujem z GitHubu.")
        try:
            sections = sync_knowledge_base(fetch_remote=True)
            if sections > 0:
                return sections
        except RuntimeError as exc:
            logger.error("GitHub knowledge sync zlyhal: %s", exc)

    sections = load_seed_knowledge()
    if sections > 0:
        return sections

    qdrant_sections = refresh_knowledge_section_count()
    if qdrant_sections > 0:
        logger.info("Knowledge base načítaná z existujúceho Qdrant indexu (%d sekcií).", qdrant_sections)
        return qdrant_sections

    logger.error(
        "Knowledge base nie je dostupná — skontrolujte GITHUB_TOKEN, %s alebo seed %s.",
        KNOWLEDGE_LOCAL_PATH,
        KNOWLEDGE_SEED_PATH,
    )
    return 0
