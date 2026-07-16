from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any
from uuid import uuid4

from reins.features.wecom.store import (
    add_record,
    add_reply,
    export_records_xlsx,
    get_faq_path,
    list_records,
)


DEFAULT_MATCH_THRESHOLD = 0.72

COMPLAINT_RE = re.compile(
    r"投诉|抱怨|不满意|差评|生气|愤怒|赔偿|"
    r"坏了|出错|错误|失败|无法|不能|没收到|不到账|太慢|崩溃|"
    r"退款.{0,12}(一直|超过|失败|不给|不退|没到账|不到账)|"
    r"退钱.{0,12}(一直|超过|失败|不给|不退|没到账|不到账)|"
    r"\bcomplain(?:t|ed|ing)?\b|\bcompensation\b|"
    r"\bangry\b|\bupset\b|\bterrible\b|\bbad service\b|"
    r"\bnot working\b|\bdoesn'?t work\b|\bfailed\b|\btoo slow\b|"
    r"\brefund\b.{0,40}\b(?:not received|failed|still waiting|never arrived)\b",
    re.IGNORECASE,
)

PUNCTUATION_RE = re.compile(r"[\s,，.。!！?？:：;；'\"“”‘’()\[\]{}<>《》、/\\|_-]+")


@dataclass(frozen=True)
class FixedAnswerMatch:
    entry: dict[str, Any]
    score: float
    reason: str


def normalize_text(value: str) -> str:
    return PUNCTUATION_RE.sub("", value.strip().lower())


def load_faq_entries() -> list[dict[str, Any]]:
    path = get_faq_path()
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        entries = data.get("entries", [])
    else:
        entries = data

    if not isinstance(entries, list):
        return []

    return [entry for entry in entries if isinstance(entry, dict)]


def save_faq_entries(entries: list[dict[str, Any]]) -> None:
    path = get_faq_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "entries": entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def add_faq_entry(
    *,
    meaning: str,
    approved_answer: str,
    questions: list[str] | None = None,
    keywords: list[str] | None = None,
    patterns: list[str] | None = None,
    entry_id: str | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    entries = load_faq_entries()
    entry = {
        "id": entry_id or f"faq_{uuid4().hex[:12]}",
        "enabled": enabled,
        "meaning": meaning.strip(),
        "approved_answer": approved_answer.strip(),
        "questions": [item.strip() for item in questions or [] if item.strip()],
        "keywords": [item.strip() for item in keywords or [] if item.strip()],
        "patterns": [item.strip() for item in patterns or [] if item.strip()],
    }

    if not entry["meaning"]:
        raise ValueError("FAQ meaning is required.")
    if not entry["approved_answer"]:
        raise ValueError("FAQ approved answer is required.")
    if not entry["questions"] and not entry["keywords"] and not entry["patterns"]:
        raise ValueError("Add at least one question, keyword, or pattern.")

    entries = [existing for existing in entries if existing.get("id") != entry["id"]]
    entries.append(entry)
    save_faq_entries(entries)
    return entry


def _question_score(message_norm: str, question: str) -> tuple[float, str]:
    question_norm = normalize_text(question)
    if not question_norm:
        return 0.0, ""
    if message_norm == question_norm:
        return 1.0, "exact_question"
    if question_norm in message_norm or message_norm in question_norm:
        return 0.88, "contained_question"
    ratio = SequenceMatcher(None, message_norm, question_norm).ratio()
    return ratio, "fuzzy_question"


def _pattern_score(message: str, pattern: str) -> tuple[float, str]:
    if not pattern:
        return 0.0, ""
    try:
        if re.search(pattern, message, flags=re.IGNORECASE):
            return 0.93, "regex_pattern"
    except re.error:
        return 0.0, ""
    return 0.0, ""


def _keyword_score(message_norm: str, keywords: list[str]) -> tuple[float, str]:
    normalized_keywords = [normalize_text(keyword) for keyword in keywords if normalize_text(keyword)]
    if not normalized_keywords:
        return 0.0, ""
    hits = [keyword for keyword in normalized_keywords if keyword in message_norm]
    if not hits:
        return 0.0, ""
    if len(hits) == len(normalized_keywords):
        return min(0.95, 0.82 + 0.02 * len(hits)), "all_keywords"
    if len(hits) >= 2:
        return min(0.8, 0.62 + 0.04 * len(hits)), "partial_keywords"
    return 0.0, ""


def match_fixed_answer(message: str, threshold: float = DEFAULT_MATCH_THRESHOLD) -> FixedAnswerMatch | None:
    message_norm = normalize_text(message)
    if not message_norm:
        return None

    best: FixedAnswerMatch | None = None
    for entry in load_faq_entries():
        if entry.get("enabled") is False:
            continue

        candidates: list[tuple[float, str]] = []
        for question in entry.get("questions") or []:
            candidates.append(_question_score(message_norm, str(question)))
        for pattern in entry.get("patterns") or []:
            candidates.append(_pattern_score(message, str(pattern)))
        candidates.append(_keyword_score(message_norm, [str(item) for item in entry.get("keywords") or []]))

        score, reason = max(candidates or [(0.0, "")], key=lambda item: item[0])
        if score >= threshold and (best is None or score > best.score):
            best = FixedAnswerMatch(entry=entry, score=score, reason=reason)

    return best


def is_complaint(message: str) -> bool:
    return bool(COMPLAINT_RE.search(message or ""))


def humanize_reply(approved_answer: str, *, message: str) -> str:
    answer = approved_answer.strip()
    if not answer:
        return ""

    lower = answer.lower()
    if lower.startswith(("sorry", "抱歉", "对不起", "您好", "hello", "hi")):
        return answer

    prefixes = [
        "好的，",
        "明白了，",
        "可以的，",
        "我帮你确认一下：",
    ]
    digest = hashlib.sha1(message.encode("utf-8")).hexdigest()
    prefix = prefixes[int(digest[:2], 16) % len(prefixes)]
    return f"{prefix}{answer}"


def build_ai_fallback_prompt(message: str, *, complaint_saved: bool, records_xlsx_path: str = "") -> str:
    lines = [
        "Handle this WeCom user message naturally and concisely.",
        "Use the normal Hermes AI agent because no approved fixed answer matched.",
    ]
    if complaint_saved:
        lines.append("This message was classified as a complaint and has already been stored by Reins.")
        if records_xlsx_path:
            lines.append(f"Complaint records file: {records_xlsx_path}")
    lines.append("")
    lines.append(f"User message: {message}")
    return "\n".join(lines)


def process_message(
    message: str,
    *,
    sender_id: str = "",
    sender_name: str = "",
    chat_id: str = "",
    chat_type: str = "",
    platform: str = "wecom",
    metadata: dict[str, Any] | None = None,
    record_kind: str | None = None,
    match_threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> dict[str, Any]:
    clean_message = str(message or "").strip()
    metadata = dict(metadata or {})
    metadata.setdefault("platform", platform)

    if not clean_message:
        return {
            "handled": False,
            "route": "ignored",
            "reply": "",
            "ai_fallback": False,
            "error": "empty_message",
        }

    match = match_fixed_answer(clean_message, threshold=match_threshold)
    complaint = is_complaint(clean_message)
    kind_to_record = (record_kind or ("complaint" if complaint else "")).strip()
    route = "fixed_answer" if match else "hermes_ai"
    reply = ""
    reply_record = None
    selected_meaning = ""
    matched_faq_id = ""
    match_score = 0.0
    match_reason = ""

    if match:
        matched_faq_id = str(match.entry.get("id") or "")
        selected_meaning = str(match.entry.get("meaning") or "")
        match_score = match.score
        match_reason = match.reason
        reply = humanize_reply(str(match.entry.get("approved_answer") or ""), message=clean_message)
        reply_record = add_reply(
            sender_id=sender_id,
            sender_name=sender_name,
            chat_id=chat_id,
            chat_type=chat_type,
            inbound_message=clean_message,
            reply=reply,
            matched_faq_id=matched_faq_id,
            selected_meaning=selected_meaning,
            route=route,
            metadata=metadata,
        )

    record = None
    records_xlsx_path = ""
    if kind_to_record:
        record = add_record(
            kind=kind_to_record,
            sender_id=sender_id,
            sender_name=sender_name,
            chat_id=chat_id,
            chat_type=chat_type,
            message=clean_message,
            selected_meaning=selected_meaning,
            matched_faq_id=matched_faq_id,
            reply=reply,
            ai_fallback=not bool(match),
            metadata=metadata,
        )
        records_xlsx_path = str(export_records_xlsx())

    ai_fallback = match is None
    return {
        "handled": bool(match),
        "route": route,
        "reply": reply,
        "reply_record": reply_record,
        "ai_fallback": ai_fallback,
        "ai_fallback_prompt": build_ai_fallback_prompt(
            clean_message,
            complaint_saved=bool(record and kind_to_record == "complaint"),
            records_xlsx_path=records_xlsx_path,
        ) if ai_fallback else "",
        "selected_meaning": selected_meaning,
        "matched_faq_id": matched_faq_id,
        "match_score": match_score,
        "match_reason": match_reason,
        "complaint": complaint,
        "record_saved": bool(record),
        "record_kind": kind_to_record,
        "record": record,
        "records_xlsx_path": records_xlsx_path,
    }


def export_records() -> dict[str, Any]:
    path = export_records_xlsx()
    return {
        "ok": True,
        "path": str(path),
        "records": list_records(limit=500),
    }
