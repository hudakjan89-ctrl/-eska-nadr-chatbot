import os
import base64
import logging
import httpx

logger = logging.getLogger("ceska_nadrz.knowledge_github")

KNOWLEDGE_FILE_NAME = "knowledge_base.md"
KNOWLEDGE_LOCAL_PATH = os.getenv("KNOWLEDGE_LOCAL_PATH", KNOWLEDGE_FILE_NAME)
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = os.getenv("GITHUB_OWNER", "hudakjan89-ctrl").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "ceskanadrz-knowledge").strip()
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main").strip() or "main"


def is_github_configured() -> bool:
    return bool(GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO)


def fetch_knowledge_from_github() -> dict:
    if not is_github_configured():
        raise RuntimeError("GitHub knowledge sync is not configured (GITHUB_TOKEN/OWNER/REPO).")

    if not KNOWLEDGE_LOCAL_PATH.endswith(KNOWLEDGE_FILE_NAME) or ".." in KNOWLEDGE_LOCAL_PATH:
        raise RuntimeError(
            f"KNOWLEDGE_LOCAL_PATH must end with {KNOWLEDGE_FILE_NAME} and must not contain path traversal."
        )

    url = (
        f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/"
        f"{KNOWLEDGE_FILE_NAME}?ref={GITHUB_BRANCH}"
    )
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"GitHub fetch failed: {exc}") from exc

    if response.status_code == 404:
        raise RuntimeError(
            f"{KNOWLEDGE_FILE_NAME} not found in {GITHUB_OWNER}/{GITHUB_REPO}@{GITHUB_BRANCH}."
        )
    if response.status_code != 200:
        raise RuntimeError(f"GitHub API error ({response.status_code}): {response.text[:300]}")

    payload = response.json()
    encoded = payload.get("content", "")
    if not encoded:
        raise RuntimeError("GitHub response did not include file content.")

    content = base64.b64decode(encoded).decode("utf-8")
    with open(KNOWLEDGE_LOCAL_PATH, "w", encoding="utf-8") as handle:
        handle.write(content)

    byte_count = len(content.encode("utf-8"))
    logger.info(
        "Stiahnutý %s z %s/%s@%s (%d bajtov, sha=%s).",
        KNOWLEDGE_FILE_NAME,
        GITHUB_OWNER,
        GITHUB_REPO,
        GITHUB_BRANCH,
        byte_count,
        (payload.get("sha") or "")[:12],
    )

    return {
        "commit_sha": payload.get("sha"),
        "file_path": KNOWLEDGE_FILE_NAME,
        "branch": GITHUB_BRANCH,
        "target": f"{GITHUB_OWNER}/{GITHUB_REPO}",
        "bytes": byte_count,
    }


def sync_knowledge_base(fetch_remote: bool = True) -> int:
    from database import load_and_upsert_knowledge

    if fetch_remote and is_github_configured():
        fetch_knowledge_from_github()
    elif not os.path.exists(KNOWLEDGE_LOCAL_PATH):
        logger.warning(
            "GitHub nie je nakonfigurovaný a lokálny %s neexistuje — knowledge base sa nenačíta.",
            KNOWLEDGE_LOCAL_PATH,
        )
        return 0

    return load_and_upsert_knowledge(KNOWLEDGE_LOCAL_PATH)


def load_knowledge_on_startup() -> int:
    """Pri štarte len z cache. GitHub sa ťahá až po webhooku z portálu (alebo prvý boot)."""
    from database import load_and_upsert_knowledge

    if os.path.exists(KNOWLEDGE_LOCAL_PATH):
        logger.info("Načítavam knowledge base z lokálnej cache (bez GitHub dotazu).")
        return load_and_upsert_knowledge(KNOWLEDGE_LOCAL_PATH)

    if is_github_configured():
        logger.info("Lokálna cache chýba — prvotné stiahnutie z GitHubu.")
        return sync_knowledge_base(fetch_remote=True)

    logger.warning(
        "Knowledge base nie je dostupná — čaká sa na prvý sync z portálu."
    )
    return 0
