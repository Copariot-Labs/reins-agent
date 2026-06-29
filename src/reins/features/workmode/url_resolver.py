from __future__ import annotations

import re
from urllib.parse import quote_plus


BROWSER_CONTEXT_WORDS = {
    "browser",
    "github",
    "google",
    "internet",
    "link",
    "online",
    "page",
    "portal",
    "site",
    "source",
    "url",
    "web",
    "webpage",
    "website",
    "网页",
    "浏览器",
    "链接",
    "网站",
}

BROWSER_ACTION_WORDS = {
    "browse",
    "go to",
    "navigate",
    "visit",
    "访问",
}

WEB_SEARCH_WORDS = {
    "find online",
    "google",
    "look up",
    "lookup",
    "research",
    "search",
    "web search",
    "搜索",
    "查询",
}

LOCAL_SEARCH_MARKERS = {
    "case",
    "code",
    "database",
    "db",
    "file",
    "folder",
    "history",
    "local",
    "repo",
    "repository",
    "sqlite",
    "workspace",
}

FILE_EXTENSION_TLDS = {
    "backend",
    "browser",
    "css",
    "csv",
    "desktop",
    "doc",
    "docx",
    "html",
    "js",
    "json",
    "md",
    "office",
    "pdf",
    "policy",
    "presenter",
    "py",
    "ts",
    "tsx",
    "txt",
    "vue",
    "wechat",
    "worker",
    "workmode",
    "xls",
    "xlsx",
    "xml",
    "yaml",
    "yml",
}

SEARCH_QUERY_STOPWORDS = {
    "browser",
    "for",
    "google",
    "internet",
    "look up",
    "lookup",
    "online",
    "please",
    "research",
    "search",
    "the web",
    "web",
    "web search",
}

LEGACY_BROWSER_WORDS = {
    "open",
    "view",
    "打开",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "browser",
    "for",
    "go",
    "github",
    "google",
    "in",
    "internet",
    "navigate",
    "of",
    "on",
    "open",
    "page",
    "profile",
    "research",
    "search",
    "the",
    "to",
    "user",
    "view",
    "visit",
}


def _has_phrase(text: str, phrases: set[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _find_domain(text: str) -> re.Match[str] | None:
    for match in re.finditer(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,63}(?:/[^\s)>\]]*)?)", text, flags=re.IGNORECASE):
        host = match.group(1).split("/", 1)[0]
        tld = host.rsplit(".", 1)[-1].lower()
        if tld not in FILE_EXTENSION_TLDS:
            return match
    return None


def is_web_search_intent(message: str) -> bool:
    text = message.lower()
    if not _has_phrase(text, WEB_SEARCH_WORDS):
        return False

    if _has_phrase(text, LOCAL_SEARCH_MARKERS) and not _has_phrase(text, BROWSER_CONTEXT_WORDS):
        return False

    return True


def is_browser_intent(message: str) -> bool:
    text = message.lower()
    if re.search(r"https?://|www\.", text) or _find_domain(text):
        return True

    if _has_phrase(text, BROWSER_CONTEXT_WORDS):
        return True

    if _has_phrase(text, BROWSER_ACTION_WORDS):
        return True

    if is_web_search_intent(message):
        return True

    return any(word in text for word in LEGACY_BROWSER_WORDS) and _has_phrase(text, BROWSER_CONTEXT_WORDS)


def infer_url_from_message(message: str) -> str | None:
    text = message.strip()

    explicit = re.search(r"https?://[^\s)>\]]+", text)
    if explicit:
        return explicit.group(0).rstrip(".,")

    www = re.search(r"\bwww\.[^\s)>\]]+", text, flags=re.IGNORECASE)
    if www:
        return f"https://{www.group(0).rstrip('.,')}"

    domain = _find_domain(text)
    if domain:
        return f"https://{domain.group(1).rstrip('.,')}"

    github = _infer_github_url(text)
    if github:
        return github

    if is_web_search_intent(message):
        return build_search_url(_infer_search_query(text))

    return None


def build_search_url(query: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(query.strip())}"


def infer_search_query_from_message(message: str) -> str:
    return _infer_search_query(message.strip())


def _infer_search_query(text: str) -> str:
    patterns = [
        r"\b(?:search|look up|lookup|research|google|find online)\s+(?:for\s+)?(.+)$",
        r"\b(?:搜索|查询)\s*(.+)$",
    ]

    query = text.strip()
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            query = match.group(1).strip()
            break

    for stopword in SEARCH_QUERY_STOPWORDS:
        query = re.sub(rf"\b{re.escape(stopword)}\b", " ", query, flags=re.IGNORECASE)

    query = re.sub(r"\s+", " ", query).strip(" .,")
    return query or text.strip()


def _infer_github_url(text: str) -> str | None:
    tokens = re.findall(r"[A-Za-z0-9-]+", text)
    lowered = [token.lower() for token in tokens]

    if "github" not in lowered:
        return None

    github_index = lowered.index("github")
    for token in [*tokens[github_index + 1:], *reversed(tokens[:github_index])]:
        candidate = token.strip("-")
        if not candidate:
            continue
        if candidate.lower() in STOPWORDS:
            continue
        if re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", candidate):
            return f"https://github.com/{candidate}"

    return "https://github.com"
