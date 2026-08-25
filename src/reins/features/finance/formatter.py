from __future__ import annotations

from reins.features.finance.schema import (
    ParsedFinanceIntent,
    SummaryReport,
    Transaction,
    TransactionInput,
)


def format_money(amount: float, currency: str = "CNY") -> str:
    symbol = "¥" if currency == "CNY" else f"{currency} "
    return f"{symbol}{amount:,.2f}"


def format_transaction_type(value: str) -> str:
    if value == "income":
        return "收入"

    if value == "expense":
        return "支出"

    return value


def format_transaction_input(tx: TransactionInput) -> str:
    return (
        f"{format_transaction_type(tx.type)} "
        f"{format_money(tx.amount, tx.currency)} "
        f"{tx.category} "
        f"{tx.description} "
        f"{tx.occurred_at.isoformat()}"
    )


def format_transaction(tx: Transaction) -> str:
    return (
        f"#{tx.id} "
        f"{tx.occurred_at.isoformat()} "
        f"{format_transaction_type(tx.type)} "
        f"{format_money(tx.amount, tx.currency)} "
        f"{tx.category} "
        f"{tx.description}"
    )


def format_transaction_created(tx: Transaction) -> str:
    return "\n".join(
        [
            f"已记录{format_transaction_type(tx.type)}：{format_money(tx.amount, tx.currency)}",
            f"分类：{tx.category}",
            f"日期：{tx.occurred_at.isoformat()}",
            f"说明：{tx.description}",
            f"编号：{tx.id}",
        ]
    )


def format_summary_report(report: SummaryReport) -> str:
    lines = [
        f"财务汇总：{report.start_date.isoformat()} 至 {report.end_date.isoformat()}",
        "",
        f"总收入：{format_money(report.total_income)}",
        f"总支出：{format_money(report.total_expense)}",
        f"净收支：{format_money(report.net)}",
    ]

    if report.expense_by_category:
        lines.extend(["", "支出分类："])
        for category, amount in report.expense_by_category.items():
            lines.append(f"- {category}: {format_money(amount)}")

    if report.income_by_category:
        lines.extend(["", "收入分类："])
        for category, amount in report.income_by_category.items():
            lines.append(f"- {category}: {format_money(amount)}")

    if report.recent_transactions:
        lines.extend(["", "最近交易："])
        for tx in report.recent_transactions:
            lines.append(f"- {format_transaction(tx)}")

    if not report.recent_transactions:
        lines.extend(["", "该时间段内暂无交易记录。"])

    return "\n".join(lines)


def format_parsed_intent(parsed: ParsedFinanceIntent) -> str:
    lines = [
        f"intent: {parsed.intent}",
        f"confidence: {parsed.confidence:.2f}",
    ]

    if parsed.missing_fields:
        lines.append(f"missing_fields: {', '.join(parsed.missing_fields)}")
    else:
        lines.append("missing_fields: none")

    if parsed.transaction:
        tx = parsed.transaction
        lines.extend(
            [
                "transaction:",
                f"  type: {tx.type}",
                f"  amount: {tx.amount}",
                f"  currency: {tx.currency}",
                f"  category: {tx.category}",
                f"  description: {tx.description}",
                f"  occurred_at: {tx.occurred_at.isoformat()}",
                f"  payment_method: {tx.payment_method or ''}",
                f"  source: {tx.source}",
            ]
        )

    if parsed.start_date and parsed.end_date:
        lines.extend(
            [
                "period:",
                f"  start_date: {parsed.start_date.isoformat()}",
                f"  end_date: {parsed.end_date.isoformat()}",
            ]
        )

    if parsed.limit:
        lines.append(f"limit: {parsed.limit}")

    return "\n".join(lines)
