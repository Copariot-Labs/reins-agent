from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from reins.features.workmode.workers.browser.engine import (
    BrowserSession,
    close_browser_session,
    get_browser_dir,
    open_browser_session,
)


MAX_ERROR_CHARS = 700
MAX_SOURCE_TEXT_CHARS = 12000
DEFAULT_MAX_SOURCES = 3

BLOCKED_HOST_PARTS = {
    "bing.com",
    "google.com",
    "microsoft.com/search",
    "duckduckgo.com",
    "baidu.com",
    "yahoo.com/search",
}

LOW_VALUE_HOST_PARTS = {
    "facebook.com",
    "instagram.com",
    "pinterest.",
    "reddit.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "youtube.com",
}

PREFERRED_HOST_PARTS = {
    ".edu",
    ".gov",
    ".gov.",
    ".org",
    "gov.cn",
    "people.com.cn",
    "xinhuanet.com",
    "who.int",
    "un.org",
}

STOPWORDS = {
    "about",
    "and",
    "browser",
    "find",
    "for",
    "from",
    "google",
    "latest",
    "lookup",
    "online",
    "please",
    "research",
    "search",
    "the",
    "web",
    "what",
}

CANDIDATE_SCRIPT = """
() => Array.from(document.querySelectorAll('a')).map((anchor) => {
  const href = anchor.href || '';
  const title = (anchor.innerText || anchor.textContent || '').trim();
  const container = anchor.closest('li, article, section, div');
  const snippet = container ? (container.innerText || '').trim() : title;
  return { url: href, title, snippet };
})
"""


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _error_text(exc: Exception) -> str:
    text = str(exc).strip()
    if len(text) <= MAX_ERROR_CHARS:
        return text
    return f"{text[:MAX_ERROR_CHARS].rstrip()}... [truncated]"


def _squash_text(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _safe_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower())
    label = label.strip("-._")
    return label[:48] or "source"


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _decode_bing_u(value: str) -> str:
    raw = unquote(value.strip())
    if raw.startswith(("http://", "https://")):
        return raw

    if raw.startswith("a1"):
        raw = raw[2:]

    try:
        padded = raw + ("=" * (-len(raw) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8", "ignore")
        if decoded.startswith(("http://", "https://")):
            return decoded
    except Exception:
        return value

    return value


def _unwrap_search_redirect(url: str) -> str:
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    host = parsed.netloc.lower()
    query = parse_qs(parsed.query)

    if "google." in host and parsed.path == "/url" and query.get("q"):
        return unquote(query["q"][0])

    if "bing.com" in host and query.get("u"):
        return _decode_bing_u(query["u"][0])

    return url


def _is_blocked_url(url: str) -> bool:
    lowered = url.lower()
    if not lowered.startswith(("http://", "https://")):
        return True
    return any(part in lowered for part in BLOCKED_HOST_PARTS)


def _query_tokens(query: str) -> list[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,}", query):
        lowered = token.lower()
        if lowered not in STOPWORDS:
            tokens.add(lowered)

    for segment in re.findall(r"[\u4e00-\u9fff]{3,}", query):
        for length in range(2, min(5, len(segment)) + 1):
            for index in range(0, len(segment) - length + 1):
                tokens.add(segment[index:index + length])

    return sorted(tokens, key=lambda item: (-len(item), item))[:30]


def build_research_search_url(query: str, search_engine: str | None = None) -> str:
    engine = (search_engine or os.getenv("WORKMODE_SEARCH_ENGINE") or "bing").strip().lower()
    encoded = quote_plus(query.strip())
    if engine == "google":
        return f"https://www.google.com/search?q={encoded}"
    if engine == "duckduckgo":
        return f"https://duckduckgo.com/?q={encoded}"
    return f"https://www.bing.com/search?q={encoded}"


def rank_candidates(query: str, candidates: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    tokens = _query_tokens(query)
    ranked: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for raw in candidates:
        url = _unwrap_search_redirect(_squash_text(raw.get("url"), 2000).rstrip(".,"))
        if not url or _is_blocked_url(url) or url in seen_urls:
            continue

        title = _squash_text(raw.get("title") or raw.get("text") or raw.get("url"), 220)
        snippet = _squash_text(raw.get("snippet") or raw.get("summary"), 700)
        if not title or len(title) < 4:
            continue

        seen_urls.add(url)
        haystack_title = title.lower()
        haystack_all = f"{title} {snippet} {url}".lower()
        host = _host(url)
        score = 10

        for token in tokens:
            lowered = token.lower()
            if lowered in haystack_title:
                score += 14
            elif lowered in haystack_all:
                score += 6

        if any(part in host for part in PREFERRED_HOST_PARTS):
            score += 18
        if any(part in host for part in LOW_VALUE_HOST_PARTS):
            score -= 18
        if url.lower().endswith(".pdf"):
            score += 5

        ranked.append({
            "title": title,
            "url": url,
            "summary": snippet,
            "host": host,
            "score": max(0, min(100, score)),
        })

    ranked.sort(key=lambda item: (item["score"], len(item.get("summary", ""))), reverse=True)
    for index, item in enumerate(ranked, start=1):
        item["rank"] = index
    return ranked[:limit]


def analyze_source_text(query: str, source: dict[str, Any], source_text: str) -> dict[str, Any]:
    text = _squash_text(source_text, MAX_SOURCE_TEXT_CHARS)
    tokens = _query_tokens(query)
    sentences = [
        _squash_text(sentence, 260)
        for sentence in re.split(r"(?<=[.!?。！？])\s+|[\n\r]+", text)
        if sentence.strip()
    ]

    matched = [
        sentence
        for sentence in sentences
        if any(token.lower() in sentence.lower() for token in tokens)
    ]
    key_facts = (matched or sentences)[:3]

    score = int(source.get("score") or 0)
    for token in tokens:
        if token.lower() in text.lower():
            score += 5
    if any(part in _host(str(source.get("url") or "")) for part in PREFERRED_HOST_PARTS):
        score += 10
    score = max(0, min(100, score))

    summary = " ".join(key_facts[:2]) or source.get("summary") or source.get("title") or "No readable page text found."
    published = ""
    date_match = re.search(r"\b(20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2})", text)
    if date_match:
        published = date_match.group(1).replace("年", "-").replace("月", "-").replace("/", "-").rstrip("日")

    return {
        "relevant": score >= 45 or bool(matched),
        "relevance_score": score,
        "summary": _squash_text(summary, 320),
        "key_facts": key_facts,
        "evidence": key_facts[:2],
        "published": published,
        "reason": "Deterministic page-text relevance based on query terms and source type.",
    }


def _render_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# Browser Research Report",
        "",
        f"- Query: {payload.get('query') or ''}",
        f"- Search URL: {payload.get('search_url') or ''}",
        f"- Status: {payload.get('status') or ''}",
        f"- Source count: {len(payload.get('sources') or [])}",
        "",
        "## Summary",
        "",
        str(payload.get("briefing") or "No directly relevant source summary was produced."),
        "",
        "## Sources",
        "",
    ]

    for source in payload.get("sources") or []:
        lines.extend([
            f"### {source.get('rank')}. {source.get('title') or source.get('url')}",
            "",
            f"- URL: {source.get('url') or ''}",
            f"- Score: {source.get('relevance_score') or source.get('score') or 0}",
            f"- Published: {source.get('published') or 'unknown'}",
            f"- Screenshot: {source.get('screenshot') or ''}",
            f"- HTML: {source.get('html') or ''}",
            "",
            str(source.get("summary") or ""),
            "",
        ])

        facts = [str(item) for item in source.get("key_facts") or [] if str(item).strip()]
        if facts:
            lines.append("Key facts:")
            for fact in facts:
                lines.append(f"- {fact}")
            lines.append("")

    excluded = payload.get("excluded_sources") or []
    if excluded:
        lines.extend(["## Excluded Or Failed Sources", ""])
        for item in excluded:
            lines.append(f"- {item.get('title') or item.get('url')}: {item.get('error') or item.get('reason') or 'excluded'}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_research_artifacts(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    output_dir = get_browser_dir(case_id)
    ts = _timestamp()
    json_path = output_dir / f"research-{ts}.json"
    md_path = output_dir / f"research-{ts}.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown_report(payload), encoding="utf-8")

    return {
        "kind": "research_report",
        "type": "markdown",
        "title": "Browser research report",
        "path": str(md_path),
        "summary": payload.get("briefing") or "Browser research report saved.",
        "metadata": {
            "query": payload.get("query"),
            "json_path": str(json_path),
            "source_count": len(payload.get("sources") or []),
            "search_url": payload.get("search_url"),
        },
    }


async def _page_text(page: Any) -> str:
    try:
        text = await page.locator("body").inner_text(timeout=8000)
    except Exception:
        try:
            text = await page.content()
        except Exception:
            text = ""
    return _squash_text(text, MAX_SOURCE_TEXT_CHARS)


async def _save_page_proof(page: Any, output_dir: Any, label: str) -> dict[str, str]:
    safe = _safe_label(label)
    ts = _timestamp()
    screenshot_path = output_dir / f"{safe}-{ts}.png"
    html_path = output_dir / f"{safe}-{ts}.html"
    html_path.write_text(await page.content(), encoding="utf-8")
    await page.screenshot(path=str(screenshot_path), full_page=True)
    return {
        "screenshot": str(screenshot_path),
        "html": str(html_path),
    }


async def run_browser_research(
    query: str,
    case_id: str,
    *,
    visible: bool = False,
    max_sources: int = DEFAULT_MAX_SOURCES,
    hold_ms: int = 1500,
) -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": f"Playwright unavailable: {exc}",
            "query": query,
        }

    output_dir = get_browser_dir(case_id)
    search_url = build_research_search_url(query)
    screenshots: list[str] = []
    excluded_sources: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    search_page: dict[str, Any] | None = None

    try:
        async with async_playwright() as p:
            session: BrowserSession | None = None
            try:
                session = await open_browser_session(
                    p,
                    visible=visible,
                    viewport={"width": 1366, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0 Safari/537.36"
                    ),
                )
                context = session.context
                page = await context.new_page()

                await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(max(hold_ms, 500))
                if visible:
                    await page.mouse.wheel(0, 650)
                    await page.wait_for_timeout(350)

                search_proof = await _save_page_proof(page, output_dir, "search-results")
                screenshots.append(search_proof["screenshot"])
                search_title = await page.title()
                search_page = {
                    "ok": True,
                    "kind": "browser_research_search",
                    "url": search_url,
                    "title": search_title,
                    "screenshot": search_proof["screenshot"],
                    "html": search_proof["html"],
                    "visible": visible,
                    "browser_config": session.config.to_dict(),
                }

                raw_candidates = await page.evaluate(CANDIDATE_SCRIPT)
                candidates = rank_candidates(
                    query,
                    raw_candidates if isinstance(raw_candidates, list) else [],
                    limit=max(max_sources * 3, 8),
                )

                for candidate in candidates[:max(1, max_sources)]:
                    source_page = await context.new_page()
                    try:
                        await source_page.goto(candidate["url"], wait_until="domcontentloaded", timeout=30000)
                        await source_page.wait_for_timeout(max(hold_ms // 2, 500))
                        if visible:
                            await source_page.mouse.wheel(0, 700)
                            await source_page.wait_for_timeout(300)

                        proof = await _save_page_proof(source_page, output_dir, f"source-{candidate['rank']}")
                        screenshots.append(proof["screenshot"])
                        text = await _page_text(source_page)
                        title = _squash_text(await source_page.title() or candidate["title"], 220)
                        analysis = analyze_source_text(query, {**candidate, "title": title}, text)
                        sources.append({
                            **candidate,
                            **analysis,
                            "title": title or candidate["title"],
                            "type": "browser_research",
                            "screenshot": proof["screenshot"],
                            "html": proof["html"],
                            "text_preview": _squash_text(text, 900),
                        })
                    except Exception as exc:
                        excluded_sources.append({
                            **candidate,
                            "error": _error_text(exc),
                        })
                    finally:
                        await source_page.close()
            finally:
                if session is not None:
                    await close_browser_session(session)

        status = "completed" if sources else "insufficient_sources"
        briefing = _build_briefing(query, sources)
        payload = {
            "ok": True,
            "kind": "browser_research",
            "status": status,
            "query": query,
            "search_url": search_url,
            "search_page": search_page,
            "sources": sources,
            "excluded_sources": excluded_sources,
            "briefing": briefing,
            "source_count": len(sources),
            "visible": visible,
            "screenshots": screenshots,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        artifact = write_research_artifacts(case_id, payload)
        payload["artifact"] = artifact
        return payload

    except Exception as exc:
        return {
            "ok": False,
            "kind": "browser_research",
            "error_type": type(exc).__name__,
            "error": _error_text(exc),
            "query": query,
            "search_url": search_url,
            "screenshots": screenshots,
            "sources": sources,
            "excluded_sources": excluded_sources,
            "search_page": search_page,
        }


def _build_briefing(query: str, sources: list[dict[str, Any]]) -> str:
    if not sources:
        return f"No directly readable sources were found for: {query}"

    strongest = sorted(
        sources,
        key=lambda item: int(item.get("relevance_score") or item.get("score") or 0),
        reverse=True,
    )[:3]
    parts = []
    for source in strongest:
        summary = str(source.get("summary") or source.get("title") or "").strip()
        if summary:
            parts.append(summary)
    return " ".join(parts)[:900] or f"Browser research completed for: {query}"
