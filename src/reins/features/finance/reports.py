from __future__ import annotations

from datetime import date, timedelta

from reins.features.finance.errors import InvalidDateRangeError
from reins.features.finance.repository import list_transactions
from reins.features.finance.schema import SummaryReport, Transaction, TransactionFilter


def month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)

    if month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)

    return start, end


def current_month_range(today: date | None = None) -> tuple[date, date]:
    if today is None:
        today = date.today()

    return month_range(today.year, today.month)


def parse_month(value: str) -> tuple[date, date]:
    try:
        year_raw, month_raw = value.split("-", 1)
        year = int(year_raw)
        month = int(month_raw)
    except ValueError as exc:
        raise InvalidDateRangeError(
            "Invalid month format. Use YYYY-MM, for example 2026-05."
        ) from exc

    if month < 1 or month > 12:
        raise InvalidDateRangeError("Month must be between 1 and 12.")

    return month_range(year, month)


def summarize_period(
    start_date: date,
    end_date: date,
    recent_limit: int = 10,
) -> SummaryReport:
    if start_date > end_date:
        raise InvalidDateRangeError("Start date cannot be later than end date.")

    transactions = list_transactions(
        TransactionFilter(
            start_date=start_date,
            end_date=end_date,
            status="posted",
            limit=10_000,
        )
    )

    total_income = 0.0
    total_expense = 0.0
    income_by_category: dict[str, float] = {}
    expense_by_category: dict[str, float] = {}

    for tx in transactions:
        if tx.type == "income":
            total_income += tx.amount
            income_by_category[tx.category] = (
                income_by_category.get(tx.category, 0.0) + tx.amount
            )

        if tx.type == "expense":
            total_expense += tx.amount
            expense_by_category[tx.category] = (
                expense_by_category.get(tx.category, 0.0) + tx.amount
            )

    recent_transactions: list[Transaction] = transactions[:recent_limit]

    return SummaryReport(
        start_date=start_date,
        end_date=end_date,
        total_income=total_income,
        total_expense=total_expense,
        net=total_income - total_expense,
        income_by_category=dict(
            sorted(income_by_category.items(), key=lambda item: item[1], reverse=True)
        ),
        expense_by_category=dict(
            sorted(expense_by_category.items(), key=lambda item: item[1], reverse=True)
        ),
        recent_transactions=recent_transactions,
    )