"""URL normalization for official source discovery."""

from __future__ import annotations

import re
from urllib.parse import urlparse

_REDIRECT_HOSTS = frozenset(
    {
        "sogou.com",
        "www.sogou.com",
        "m.sogou.com",
        "baidu.com",
        "www.baidu.com",
        "m.baidu.com",
        "bing.com",
        "www.bing.com",
    }
)

_REDIRECT_PATH_HINTS = ("/link?", "/link?url=", "/baidu.php?url=")

_URL_IN_TEXT_RE = re.compile(r"https?://[^\s\])>\"']+", re.I)
_DOMAIN_IN_TEXT_RE = re.compile(
    r"([a-z0-9][-a-z0-9]*\.(?:gov\.cn|org\.cn|com\.cn|museum|cn))(?:/[^\s\])>\"']*)?",
    re.I,
)


def extract_domain(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").lower()
        if host.startswith("www."):
            return host[4:]
        return host
    except Exception:
        return ""


def is_redirect_wrapper_url(url: str) -> bool:
    if not url:
        return True
    lower = url.lower().strip()
    if not lower.startswith("http"):
        return True
    domain = extract_domain(lower)
    if domain in _REDIRECT_HOSTS:
        return True
    return any(hint in lower for hint in _REDIRECT_PATH_HINTS)


def is_fetchable_url(url: str) -> bool:
    if not url or not url.strip().lower().startswith("http"):
        return False
    return not is_redirect_wrapper_url(url)


def is_search_task_metadata(hit: dict) -> bool:
    if not isinstance(hit, dict):
        return False
    if hit.get("task_id") and not (hit.get("url") or hit.get("link")):
        return True
    if hit.get("evidence_count") is not None and not (hit.get("url") or hit.get("link")):
        return True
    return False


def parse_title_from_claim_text(text: str) -> str | None:
    if not text:
        return None
    text = text.strip()
    if ":" in text or "：" in text:
        sep = ":" if ":" in text else "："
        head = text.split(sep, 1)[0].strip()
        if 2 <= len(head) <= 80:
            return head
    if " - " in text:
        head = text.split(" - ", 1)[0].strip()
        if 2 <= len(head) <= 80:
            return head
    return None


def extract_urls_from_text(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for match in _URL_IN_TEXT_RE.findall(text):
        url = match.rstrip(".,;)")
        if url not in seen:
            seen.add(url)
            found.append(url)
    for match in _DOMAIN_IN_TEXT_RE.findall(text):
        domain = match.lower()
        if domain in seen:
            continue
        url = f"https://{domain}" if not domain.startswith("http") else domain
        seen.add(domain)
        found.append(url)
    return found


def normalize_search_hit(hit: dict) -> dict | None:
    if not isinstance(hit, dict):
        return None
    if is_search_task_metadata(hit):
        return None
    url = str(hit.get("url") or hit.get("link") or "").strip()
    title = str(hit.get("title") or hit.get("name") or "").strip() or None
    snippet = str(
        hit.get("snippet") or hit.get("description") or hit.get("content") or ""
    ).strip() or None
    if not title and snippet:
        title = parse_title_from_claim_text(snippet)
    if not url and snippet:
        for candidate in extract_urls_from_text(snippet):
            if is_fetchable_url(candidate):
                url = candidate
                break
    if not url and not title and not snippet:
        return None
    return {"url": url, "title": title, "snippet": snippet}


def dedupe_hits(hits: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for hit in hits:
        normalized = normalize_search_hit(hit) if not hit.get("_normalized") else hit
        if not normalized:
            continue
        url = normalized.get("url") or ""
        title = normalized.get("title") or ""
        key = url if url else f"title:{title[:60]}"
        if key in seen:
            continue
        seen.add(key)
        normalized["_normalized"] = True
        out.append({k: v for k, v in normalized.items() if k != "_normalized"})
    return out


def hits_from_evidence_list(evidence_list: list) -> list[dict]:
    """Extract search hits from open-webSearch Evidence items."""
    hits: list[dict] = []
    for ev in evidence_list or []:
        source_name = (getattr(ev, "source_name", None) or "").lower()
        st = ""
        if getattr(ev, "source_type", None):
            st = ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type)
        is_search = "websearch" in source_name or source_name == "open-websearch"
        is_web = st == "web"
        if not is_search and not is_web:
            continue
        if "official source discovery" in source_name:
            continue

        url = (getattr(ev, "source_url", None) or "").strip()
        title = None
        snippet = None
        for claim in getattr(ev, "claims", []) or []:
            raw = str(getattr(claim, "raw_text", "") or getattr(claim, "value", "") or "")
            if not snippet and raw:
                snippet = raw[:800]
            if not title:
                title = parse_title_from_claim_text(raw)
            nv = getattr(claim, "normalized_value", None)
            if isinstance(nv, str) and nv.startswith("http") and not url:
                url = nv
            if isinstance(nv, dict) and not url:
                for v in nv.values():
                    if isinstance(v, str) and v.startswith("http"):
                        url = v
                        break
        if snippet and not title:
            title = parse_title_from_claim_text(snippet)
        if snippet:
            for candidate in extract_urls_from_text(snippet):
                if is_fetchable_url(candidate):
                    if is_redirect_wrapper_url(url or ""):
                        url = candidate
                    break
        if not url and not title and not snippet:
            continue
        hits.append({"url": url, "title": title, "snippet": snippet})
    return dedupe_hits(hits)


def place_name_in_text(place_name: str, *texts: str | None) -> bool:
    if not place_name:
        return False
    blob = " ".join(t for t in texts if t)
    if not blob:
        return False
    core = place_name.strip()
    if core in blob:
        return True
    short = re.sub(r"(古镇|风景区|景区|公园|博物馆|博物院)$", "", core)
    return bool(short and short in blob)
