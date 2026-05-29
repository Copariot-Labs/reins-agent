from __future__ import annotations

from reins.features.finance.schema import FinanceIntent


EXPENSE_KEYWORDS = {
    "买",
    "花",
    "付",
    "支出",
    "消费",
    "打车",
    "吃",
    "喝",
    "外卖",
    "订阅",
    "采购",
    "房租",
    "水电",
    "停车",
    "加油",
    "咖啡",
    "奶茶",
    "早餐",
    "午餐",
    "晚餐",
    "转给",
}

INCOME_KEYWORDS = {
    "收到",
    "收入",
    "进账",
    "工资",
    "奖金",
    "退款",
    "客户转账",
    "客户付款",
    "报销到账",
    "收款",
    "转账给我",
}

QUERY_TRANSACTION_KEYWORDS = {
    "查",
    "查询",
    "流水",
    "记录",
    "明细",
    "最近",
    "列表",
    "list",
}

SUMMARY_KEYWORDS = {
    "报表",
    "总结",
    "汇总",
    "统计",
    "收入合计",
    "支出合计",
    "净收入",
    "这个月支出",
    "本月支出",
    "这个月收入",
    "本月收入",
}


def _contains_any(text: str, keywords: set[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def classify_finance_intent(text: str) -> FinanceIntent:
    normalized = text.strip()

    if not normalized:
        return FinanceIntent(
            intent="unknown",
            confidence=0.0,
            raw_text=text,
            missing_fields=[],
        )

    if _contains_any(normalized, SUMMARY_KEYWORDS):
        return FinanceIntent(
            intent="query_summary",
            confidence=0.86,
            raw_text=text,
            missing_fields=[],
        )

    if _contains_any(normalized, QUERY_TRANSACTION_KEYWORDS):
        return FinanceIntent(
            intent="query_transactions",
            confidence=0.82,
            raw_text=text,
            missing_fields=[],
        )

    # Explicit income exceptions first.
    if "退款" in normalized or "报销到账" in normalized or "转账给我" in normalized:
        return FinanceIntent(
            intent="record_income",
            confidence=0.9,
            raw_text=text,
            missing_fields=[],
        )

    if _contains_any(normalized, INCOME_KEYWORDS):
        return FinanceIntent(
            intent="record_income",
            confidence=0.86,
            raw_text=text,
            missing_fields=[],
        )

    if _contains_any(normalized, EXPENSE_KEYWORDS):
        return FinanceIntent(
            intent="record_expense",
            confidence=0.84,
            raw_text=text,
            missing_fields=[],
        )

    return FinanceIntent(
        intent="unknown",
        confidence=0.2,
        raw_text=text,
        missing_fields=[],
    )