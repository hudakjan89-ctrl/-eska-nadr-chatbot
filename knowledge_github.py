import os
import base64
import logging
import httpx

logger = logging.getLogger("ceska_nadrz.knowledge_github")

KNOWLEDGE_FILE_NAME = "knowledge_base.md"
KNOWLEDGE_LOCAL_PATH = os.getenv("KNOWLEDGE_LOCAL_PATH", KNOWLEDGE_FILE_NAME)


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
        try:
            return sync_knowledge_base(fetch_remote=True)
        except RuntimeError as exc:
            logger.error(
                "%s Bot štartuje bez knowledge base — oprav GITHUB_TOKEN alebo "
                "počkaj na webhook z portálu.",
                exc,
            )
            return 0

    logger.warning(
        "Knowledge base nie je dostupná — čaká sa na prvý sync z portálu."
    )
    return 0
