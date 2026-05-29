from __future__ import annotations

from dataclasses import dataclass

from reins.features.finance.errors import FinanceError
from reins.features.finance.formatter import (
    format_summary_report,
    format_transaction,
    format_transaction_created,
)
from reins.features.finance.parser import parse_finance_text
from reins.features.finance.reports import summarize_period
from reins.features.finance.repository import create_transaction, list_transactions
from reins.features.finance.schema import ParsedFinanceIntent, TransactionFilter


@dataclass(frozen=True)
class FinancePreprocessResult:
    handled: bool
    message: str
    exit_code: int = 0


def should_handle_finance_text(parsed: ParsedFinanceIntent) -> bool:
    if parsed.intent in {"record_expense", "record_income"}:
        return parsed.confidence >= 0.75

    if parsed.intent in {"query_transactions", "query_summary"}:
        return parsed.confidence >= 0.8

    return False


def handle_record_transaction(parsed: ParsedFinanceIntent) -> FinancePreprocessResult:
    if parsed.missing_fields:
        if "amount" in parsed.missing_fields:
            return FinancePreprocessResult(
                handled=True,
                message="Missing amount. How much was this transaction?",
                exit_code=1,
            )

        return FinancePreprocessResult(
            handled=True,
            message=f"Missing fields: {', '.join(parsed.missing_fields)}",
            exit_code=1,
        )

    if parsed.transaction is None:
        return FinancePreprocessResult(
            handled=True,
            message="Could not create a transaction from this text.",
            exit_code=1,
        )

    try:
        tx = create_transaction(parsed.transaction)
    except FinanceError as exc:
        return FinancePreprocessResult(
            handled=True,
            message=f"Finance error: {exc}",
            exit_code=1,
        )

    return FinancePreprocessResult(
        handled=True,
        message=format_transaction_created(tx),
        exit_code=0,
    )


def handle_query_transactions(parsed: ParsedFinanceIntent) -> FinancePreprocessResult:
    try:
        transactions = list_transactions(
            TransactionFilter(
                start_date=parsed.start_date,
                end_date=parsed.end_date,
                status="posted",
                limit=parsed.limit or 20,
            )
        )
    except FinanceError as exc:
        return FinancePreprocessResult(
            handled=True,
            message=f"Finance error: {exc}",
            exit_code=1,
        )

    if not transactions:
        return FinancePreprocessResult(
            handled=True,
            message="No transactions found for this period.",
            exit_code=0,
        )

    lines = ["Transactions:"]
    for tx in transactions:
        lines.append(f"- {format_transaction(tx)}")

    return FinancePreprocessResult(
        handled=True,
        message="\n".join(lines),
        exit_code=0,
    )


def handle_query_summary(parsed: ParsedFinanceIntent) -> FinancePreprocessResult:
    if parsed.start_date is None or parsed.end_date is None:
        return FinancePreprocessResult(
            handled=True,
            message="Could not determine the report period.",
            exit_code=1,
        )

    try:
        report = summarize_period(parsed.start_date, parsed.end_date)
    except FinanceError as exc:
        return FinancePreprocessResult(
            handled=True,
            message=f"Finance error: {exc}",
            exit_code=1,
        )

    return FinancePreprocessResult(
        handled=True,
        message=format_summary_report(report),
        exit_code=0,
    )


def preprocess_finance_text(text: str) -> FinancePreprocessResult:
    try:
        parsed = parse_finance_text(text)
    except FinanceError as exc:
        return FinancePreprocessResult(
            handled=True,
            message=f"Finance error: {exc}",
            exit_code=1,
        )

    if not should_handle_finance_text(parsed):
        return FinancePreprocessResult(
            handled=False,
            message="",
            exit_code=0,
        )

    if parsed.intent in {"record_expense", "record_income"}:
        return handle_record_transaction(parsed)

    if parsed.intent == "query_transactions":
        return handle_query_transactions(parsed)

    if parsed.intent == "query_summary":
        return handle_query_summary(parsed)

    return FinancePreprocessResult(
        handled=False,
        message="",
        exit_code=0,
    )
