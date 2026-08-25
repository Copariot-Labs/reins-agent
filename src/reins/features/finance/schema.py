from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


TransactionType = Literal["income", "expense"]
TransactionStatus = Literal["posted", "voided"]

FinanceIntentName = Literal[
    "record_expense",
    "record_income",
    "query_transactions",
    "query_summary",
    "export_excel",
    "unknown",
]


@dataclass(frozen=True)
class TransactionInput:
    type: TransactionType
    amount: float
    description: str
    occurred_at: date
    category: str = "其他"
    currency: str = "CNY"
    counterparty: str | None = None
    payment_method: str | None = None
    raw_text: str | None = None
    source: str = "manual"


@dataclass(frozen=True)
class Transaction:
    id: int
    type: TransactionType
    amount: float
    currency: str
    category: str
    description: str
    occurred_at: date
    created_at: datetime
    updated_at: datetime | None = None
    counterparty: str | None = None
    payment_method: str | None = None
    raw_text: str | None = None
    source: str = "manual"
    status: TransactionStatus = "posted"


@dataclass(frozen=True)
class TransactionFilter:
    start_date: date | None = None
    end_date: date | None = None
    type: TransactionType | None = None
    category: str | None = None
    status: TransactionStatus = "posted"
    limit: int = 20
    offset: int = 0


@dataclass(frozen=True)
class FinanceIntent:
    intent: FinanceIntentName
    confidence: float
    raw_text: str
    missing_fields: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedFinanceIntent:
    intent: FinanceIntentName
    confidence: float
    raw_text: str
    missing_fields: list[str] = field(default_factory=list)
    transaction: TransactionInput | None = None
    start_date: date | None = None
    end_date: date | None = None
    limit: int | None = None


@dataclass(frozen=True)
class SummaryReport:
    start_date: date
    end_date: date
    total_income: float
    total_expense: float
    net: float
    income_by_category: dict[str, float]
    expense_by_category: dict[str, float]
    recent_transactions: list[Transaction]
