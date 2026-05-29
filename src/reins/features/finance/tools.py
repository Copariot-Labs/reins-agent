from __future__ import annotations

from datetime import date
from typing import Any

from reins.features.finance.errors import FinanceError, InvalidDateRangeError
from reins.features.finance.formatter import (
    format_summary_report,
    format_transaction,
    format_transaction_created,
)
from reins.features.finance.parser import parse_finance_text
from reins.features.finance.reports import current_month_range, parse_month, summarize_period
from reins.features.finance.repository import create_transaction, list_transactions
from reins.features.finance.schema import TransactionFilter, TransactionInput


def _date_from_string(value: str | None) -> date | None:
    if value is None:
        return None

    return date.fromisoformat(value)


def _transaction_to_dict(tx) -> dict[str, Any]:
    return {
        "id": tx.id,
        "type": tx.type,
        "amount": tx.amount,
        "currency": tx.currency,
        "category": tx.category,
        "description": tx.description,
        "occurred_at": tx.occurred_at.isoformat(),
        "created_at": tx.created_at.isoformat(),
        "updated_at": tx.updated_at.isoformat() if tx.updated_at else None,
        "counterparty": tx.counterparty,
        "payment_method": tx.payment_method,
        "raw_text": tx.raw_text,
        "source": tx.source,
        "status": tx.status,
    }


def _summary_to_dict(report) -> dict[str, Any]:
    return {
        "start_date": report.start_date.isoformat(),
        "end_date": report.end_date.isoformat(),
        "total_income": report.total_income,
        "total_expense": report.total_expense,
        "net": report.net,
        "income_by_category": report.income_by_category,
        "expense_by_category": report.expense_by_category,
        "recent_transactions": [
            _transaction_to_dict(tx) for tx in report.recent_transactions
        ],
    }


def parse_transaction_text(text: str) -> dict[str, Any]:
    try:
        parsed = parse_finance_text(text)
    except FinanceError as exc:
        return {
            "ok": False,
            "error": str(exc),
        }

    transaction = None

    if parsed.transaction:
        tx = parsed.transaction
        transaction = {
            "type": tx.type,
            "amount": tx.amount,
            "currency": tx.currency,
            "category": tx.category,
            "description": tx.description,
            "occurred_at": tx.occurred_at.isoformat(),
            "counterparty": tx.counterparty,
            "payment_method": tx.payment_method,
            "raw_text": tx.raw_text,
            "source": tx.source,
        }

    return {
        "ok": True,
        "intent": parsed.intent,
        "confidence": parsed.confidence,
        "missing_fields": parsed.missing_fields,
        "transaction": transaction,
        "start_date": parsed.start_date.isoformat() if parsed.start_date else None,
        "end_date": parsed.end_date.isoformat() if parsed.end_date else None,
        "limit": parsed.limit,
    }


def record_transaction(
    type: str,
    amount: float,
    description: str,
    occurred_at: str,
    currency: str = "CNY",
    category: str = "其他",
    counterparty: str | None = None,
    payment_method: str | None = None,
    raw_text: str | None = None,
    source: str = "tool",
) -> dict[str, Any]:
    try:
        tx_input = TransactionInput(
            type=type,  # type: ignore[arg-type]
            amount=amount,
            currency=currency,
            category=category,
            description=description,
            occurred_at=date.fromisoformat(occurred_at),
            counterparty=counterparty,
            payment_method=payment_method,
            raw_text=raw_text,
            source=source,
        )

        tx = create_transaction(tx_input)

        return {
            "ok": True,
            "transaction_id": tx.id,
            "transaction": _transaction_to_dict(tx),
            "message": format_transaction_created(tx),
        }
    except FinanceError as exc:
        return {
            "ok": False,
            "error": str(exc),
        }
    except ValueError as exc:
        return {
            "ok": False,
            "error": f"Invalid date format. Use YYYY-MM-DD. Details: {exc}",
        }


def record_transaction_from_text(text: str) -> dict[str, Any]:
    try:
        parsed = parse_finance_text(text)
    except FinanceError as exc:
        return {
            "ok": False,
            "error": str(exc),
        }

    if parsed.intent not in {"record_expense", "record_income"}:
        return {
            "ok": False,
            "error": "This does not look like an income or expense transaction.",
            "intent": parsed.intent,
        }

    if parsed.missing_fields:
        return {
            "ok": False,
            "error": f"Missing fields: {', '.join(parsed.missing_fields)}",
            "intent": parsed.intent,
            "missing_fields": parsed.missing_fields,
        }

    if parsed.transaction is None:
        return {
            "ok": False,
            "error": "Could not create a transaction from this text.",
            "intent": parsed.intent,
        }

    tx = parsed.transaction

    return record_transaction(
        type=tx.type,
        amount=tx.amount,
        currency=tx.currency,
        category=tx.category,
        description=tx.description,
        occurred_at=tx.occurred_at.isoformat(),
        counterparty=tx.counterparty,
        payment_method=tx.payment_method,
        raw_text=tx.raw_text,
        source=tx.source,
    )


def list_finance_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    type: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    try:
        filters = TransactionFilter(
            start_date=_date_from_string(start_date),
            end_date=_date_from_string(end_date),
            type=type,  # type: ignore[arg-type]
            category=category,
            status="posted",
            limit=limit,
        )

        transactions = list_transactions(filters)

        return {
            "ok": True,
            "transactions": [_transaction_to_dict(tx) for tx in transactions],
            "message": "\n".join(format_transaction(tx) for tx in transactions)
            if transactions
            else "No transactions found for this period.",
        }
    except FinanceError as exc:
        return {
            "ok": False,
            "error": str(exc),
        }
    except ValueError as exc:
        return {
            "ok": False,
            "error": f"Invalid date format. Use YYYY-MM-DD. Details: {exc}",
        }


def summarize_finance_period(
    period: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    try:
        if period == "this_month" or (
            period is None and start_date is None and end_date is None
        ):
            start, end = current_month_range()
        elif period and period.startswith("month:"):
            start, end = parse_month(period.removeprefix("month:"))
        elif start_date and end_date:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        else:
            raise InvalidDateRangeError(
                "Provide period='this_month', period='month:YYYY-MM', or both start_date and end_date."
            )

        report = summarize_period(start, end)

        return {
            "ok": True,
            **_summary_to_dict(report),
            "message": format_summary_report(report),
        }
    except FinanceError as exc:
        return {
            "ok": False,
            "error": str(exc),
        }
    except ValueError as exc:
        return {
            "ok": False,
            "error": f"Invalid date format. Use YYYY-MM-DD. Details: {exc}",
        }


def get_finance_tool_functions() -> dict[str, Any]:
    return {
        "finance.parse_transaction_text": parse_transaction_text,
        "finance.record_transaction": record_transaction,
        "finance.record_transaction_from_text": record_transaction_from_text,
        "finance.list_transactions": list_finance_transactions,
        "finance.summarize_period": summarize_finance_period,
    }
