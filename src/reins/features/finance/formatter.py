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
        return "income"

    if value == "expense":
        return "expense"

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
            f"Recorded {format_transaction_type(tx.type)}: {format_money(tx.amount, tx.currency)}",
            f"Category: {tx.category}",
            f"Date: {tx.occurred_at.isoformat()}",
            f"Description: {tx.description}",
            f"ID: {tx.id}",
        ]
    )


def format_summary_report(report: SummaryReport) -> str:
    lines = [
        f"Finance summary: {report.start_date.isoformat()} to {report.end_date.isoformat()}",
        "",
        f"Total income: {format_money(report.total_income)}",
        f"Total expense: {format_money(report.total_expense)}",
        f"Net income: {format_money(report.net)}",
    ]

    if report.expense_by_category:
        lines.extend(["", "Expense by category:"])
        for category, amount in report.expense_by_category.items():
            lines.append(f"- {category}: {format_money(amount)}")

    if report.income_by_category:
        lines.extend(["", "Income by category:"])
        for category, amount in report.income_by_category.items():
            lines.append(f"- {category}: {format_money(amount)}")

    if report.recent_transactions:
        lines.extend(["", "Recent transactions:"])
        for tx in report.recent_transactions:
            lines.append(f"- {format_transaction(tx)}")

    if not report.recent_transactions:
        lines.extend(["", "No transactions found for this period."])

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