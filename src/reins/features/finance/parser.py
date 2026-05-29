from __future__ import annotations

import re
from datetime import date, timedelta

from reins.features.finance.classifier import classify_finance_intent
from reins.features.finance.schema import (
    FinanceIntentName,
    ParsedFinanceIntent,
    TransactionInput,
    TransactionType,
)


CATEGORY_RULES: dict[str, list[str]] = {
    "餐饮": ["咖啡", "饭", "吃", "外卖", "奶茶", "早餐", "午餐", "晚餐", "餐厅", "饮料"],
    "交通": ["打车", "地铁", "公交", "高铁", "机票", "停车", "加油", "出租车"],
    "办公": ["办公用品", "打印纸", "文具", "软件", "订阅"],
    "住房": ["房租", "租金", "物业费"],
    "水电": ["水费", "电费", "燃气", "水电"],
    "工资": ["工资", "薪水"],
    "业务收入": ["客户", "项目款", "服务费", "转账"],
    "退款": ["退款", "退回"],
}

PAYMENT_METHOD_RULES: dict[str, list[str]] = {
    "微信": ["微信", "微信零钱"],
    "支付宝": ["支付宝", "花呗"],
    "银行卡": ["银行卡", "银行", "信用卡", "借记卡"],
    "现金": ["现金"],
}

AMOUNT_PATTERN = re.compile(
    r"(?:¥|￥|RMB\s*)?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:元|块|人民币)?",
    re.IGNORECASE,
)

ISO_DATE_PATTERN = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
CHINESE_DATE_PATTERN = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})[日号]?")
SLASH_DATE_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})\b")
RECENT_LIMIT_PATTERN = re.compile(r"最近\s*(\d+)\s*条")


def _normalize_text(text: str) -> str:
    return text.strip()


def _parse_amount(text: str) -> float | None:
    candidates: list[tuple[float, int]] = []

    for match in AMOUNT_PATTERN.finditer(text):
        raw_number = match.group(1).replace(",", "")
        start = match.start()
        end = match.end()
        before = text[max(0, start - 4):start]
        after = text[end:min(len(text), end + 4)]
        full = match.group(0)

        # Avoid obvious date fragments such as 5月22日.
        if after.startswith("月") or after.startswith("日") or after.startswith("号"):
            continue

        score = 0

        if any(token in full for token in ["¥", "￥", "RMB", "元", "块", "人民币"]):
            score += 5

        if any(token in before for token in ["花", "付", "消费", "支出", "收入", "收到", "转账", "工资", "奖金"]):
            score += 3

        if any(token in after for token in ["元", "块", "人民币"]):
            score += 3

        try:
            amount = float(raw_number)
        except ValueError:
            continue

        candidates.append((amount, score))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0][0]


def _parse_single_date(text: str, today: date) -> date | None:
    if "前天" in text:
        return today - timedelta(days=2)

    if "昨天" in text:
        return today - timedelta(days=1)

    if "今天" in text:
        return today

    if "明天" in text:
        return today + timedelta(days=1)

    iso_match = ISO_DATE_PATTERN.search(text)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        return date(year, month, day)

    chinese_match = CHINESE_DATE_PATTERN.search(text)
    if chinese_match:
        year_raw, month_raw, day_raw = chinese_match.groups()
        year = int(year_raw) if year_raw else today.year
        return date(year, int(month_raw), int(day_raw))

    slash_match = SLASH_DATE_PATTERN.search(text)
    if slash_match:
        month_raw, day_raw = slash_match.groups()
        return date(today.year, int(month_raw), int(day_raw))

    return None


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)

    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    return start, end


def _parse_period(text: str, today: date) -> tuple[date | None, date | None]:
    if "本月" in text or "这个月" in text:
        return _month_range(today.year, today.month)

    if "上个月" in text or "上月" in text:
        if today.month == 1:
            return _month_range(today.year - 1, 12)

        return _month_range(today.year, today.month - 1)

    if "今年" in text:
        return date(today.year, 1, 1), date(today.year, 12, 31)

    if "本周" in text or "这周" in text:
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return start, end

    if "上周" in text:
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        end = start + timedelta(days=6)
        return start, end

    single = _parse_single_date(text, today)
    if single:
        return single, single

    return None, None


def _infer_transaction_type(intent: FinanceIntentName) -> TransactionType | None:
    if intent == "record_income":
        return "income"

    if intent == "record_expense":
        return "expense"

    return None


def _infer_category(text: str, tx_type: TransactionType | None) -> str:
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in text for keyword in keywords):
            return category

    if tx_type == "income":
        return "其他收入"

    if tx_type == "expense":
        return "其他支出"

    return "其他"


def _infer_payment_method(text: str) -> str | None:
    for method, keywords in PAYMENT_METHOD_RULES.items():
        if any(keyword in text for keyword in keywords):
            return method

    return None


def _clean_description(text: str, amount: float | None) -> str:
    description = text.strip()

    for token in ["今天", "昨天", "前天", "明天", "本月", "这个月", "上个月", "上月", "本周", "这周", "上周"]:
        description = description.replace(token, "")

    description = ISO_DATE_PATTERN.sub("", description)
    description = CHINESE_DATE_PATTERN.sub("", description)
    description = SLASH_DATE_PATTERN.sub("", description)

    if amount is not None:
        amount_int = int(amount)

        amount_patterns = [
            f"¥{amount:g}",
            f"￥{amount:g}",
            f"RMB {amount:g}",
            f"RMB{amount:g}",
            f"{amount:g}元",
            f"{amount:g}块",
            f"{amount:g}人民币",
            f"{amount:g}",
        ]

        if amount.is_integer():
            amount_patterns.extend(
                [
                    f"¥{amount_int}",
                    f"￥{amount_int}",
                    f"RMB {amount_int}",
                    f"RMB{amount_int}",
                    f"{amount_int}元",
                    f"{amount_int}块",
                    f"{amount_int}人民币",
                    f"{amount_int}",
                ]
            )

        for pattern in amount_patterns:
            description = description.replace(pattern, "")

    for token in ["我", "了", "一下"]:
        description = description.replace(token, "")

    description = re.sub(r"\s+", " ", description).strip()
    description = description.strip("，,。.")

    if not description:
        return text.strip()

    return description


def _parse_limit(text: str) -> int | None:
    match = RECENT_LIMIT_PATTERN.search(text)

    if not match:
        return None

    return int(match.group(1))


def parse_finance_text(text: str, today: date | None = None) -> ParsedFinanceIntent:
    if today is None:
        today = date.today()

    normalized = _normalize_text(text)
    classified = classify_finance_intent(normalized)
    intent = classified.intent

    if intent in {"query_transactions", "query_summary"}:
        start_date, end_date = _parse_period(normalized, today)

        if start_date is None or end_date is None:
            start_date, end_date = _month_range(today.year, today.month)

        return ParsedFinanceIntent(
            intent=intent,
            confidence=classified.confidence,
            raw_text=text,
            missing_fields=[],
            transaction=None,
            start_date=start_date,
            end_date=end_date,
            limit=_parse_limit(normalized),
        )

    if intent not in {"record_expense", "record_income"}:
        return ParsedFinanceIntent(
            intent="unknown",
            confidence=classified.confidence,
            raw_text=text,
            missing_fields=[],
        )

    tx_type = _infer_transaction_type(intent)
    amount = _parse_amount(normalized)
    occurred_at = _parse_single_date(normalized, today) or today
    category = _infer_category(normalized, tx_type)
    payment_method = _infer_payment_method(normalized)

    missing_fields: list[str] = []

    if tx_type is None:
        missing_fields.append("type")

    if amount is None:
        missing_fields.append("amount")

    description = _clean_description(normalized, amount)

    if not description:
        missing_fields.append("description")

    transaction = None

    if tx_type is not None and amount is not None and description:
        transaction = TransactionInput(
            type=tx_type,
            amount=amount,
            currency="CNY",
            category=category,
            description=description,
            occurred_at=occurred_at,
            payment_method=payment_method,
            raw_text=text,
            source="natural_language",
        )

    return ParsedFinanceIntent(
        intent=intent,
        confidence=classified.confidence,
        raw_text=text,
        missing_fields=missing_fields,
        transaction=transaction,
    )