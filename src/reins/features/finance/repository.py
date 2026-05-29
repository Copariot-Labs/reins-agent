from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from reins.features.finance.db import migrate, transaction
from reins.features.finance.errors import (
    InvalidDateRangeError,
    InvalidTransactionInputError,
    TransactionNotFoundError,
    UnknownTransactionTypeError,
)
from reins.features.finance.schema import (
    Transaction,
    TransactionFilter,
    TransactionInput,
    TransactionStatus,
    TransactionType,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_to_iso(value: date) -> str:
    return value.isoformat()


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    return datetime.fromisoformat(value)


def _validate_transaction_input(input: TransactionInput) -> None:
    if input.type not in {"income", "expense"}:
        raise UnknownTransactionTypeError(f"Unknown transaction type: {input.type}")

    if input.amount <= 0:
        raise InvalidTransactionInputError("Amount must be greater than zero.")

    if not input.description.strip():
        raise InvalidTransactionInputError("Description is required.")

    if not input.category.strip():
        raise InvalidTransactionInputError("Category is required.")

    if not input.currency.strip():
        raise InvalidTransactionInputError("Currency is required.")


def _row_to_transaction(row: Any) -> Transaction:
    return Transaction(
        id=int(row["id"]),
        type=row["type"],
        amount=float(row["amount"]),
        currency=row["currency"],
        category=row["category"],
        description=row["description"],
        occurred_at=_parse_date(row["occurred_at"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=_parse_datetime(row["updated_at"]),
        counterparty=row["counterparty"],
        payment_method=row["payment_method"],
        raw_text=row["raw_text"],
        source=row["source"],
        status=row["status"],
    )


def create_transaction(input: TransactionInput) -> Transaction:
    migrate()
    _validate_transaction_input(input)

    created_at = _now_iso()

    with transaction() as connection:
        cursor = connection.execute(
            """
            INSERT INTO finance_transactions (
                type,
                amount,
                currency,
                category,
                description,
                counterparty,
                payment_method,
                occurred_at,
                created_at,
                updated_at,
                source,
                raw_text,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, 'posted')
            """,
            (
                input.type,
                input.amount,
                input.currency,
                input.category,
                input.description,
                input.counterparty,
                input.payment_method,
                _date_to_iso(input.occurred_at),
                created_at,
                input.source,
                input.raw_text,
            ),
        )

        transaction_id = int(cursor.lastrowid)

        row = connection.execute(
            """
            SELECT *
            FROM finance_transactions
            WHERE id = ?
            """,
            (transaction_id,),
        ).fetchone()

    if row is None:
        raise TransactionNotFoundError(f"Transaction not found: {transaction_id}")

    return _row_to_transaction(row)


def get_transaction(transaction_id: int) -> Transaction:
    migrate()

    with transaction() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM finance_transactions
            WHERE id = ?
            """,
            (transaction_id,),
        ).fetchone()

    if row is None:
        raise TransactionNotFoundError(f"Transaction not found: {transaction_id}")

    return _row_to_transaction(row)


def list_transactions(filters: TransactionFilter | None = None) -> list[Transaction]:
    migrate()

    if filters is None:
        filters = TransactionFilter()

    if filters.start_date and filters.end_date and filters.start_date > filters.end_date:
        raise InvalidDateRangeError("Start date cannot be later than end date.")

    if filters.limit <= 0:
        raise InvalidTransactionInputError("Limit must be greater than zero.")

    if filters.offset < 0:
        raise InvalidTransactionInputError("Offset cannot be negative.")

    clauses = []
    params: list[object] = []

    if filters.status:
        clauses.append("status = ?")
        params.append(filters.status)

    if filters.type:
        clauses.append("type = ?")
        params.append(filters.type)

    if filters.category:
        clauses.append("category = ?")
        params.append(filters.category)

    if filters.start_date:
        clauses.append("occurred_at >= ?")
        params.append(_date_to_iso(filters.start_date))

    if filters.end_date:
        clauses.append("occurred_at <= ?")
        params.append(_date_to_iso(filters.end_date))

    where_sql = ""

    if clauses:
        where_sql = "WHERE " + " AND ".join(clauses)

    params.extend([filters.limit, filters.offset])

    with transaction() as connection:
        rows = connection.execute(
            f"""
            SELECT *
            FROM finance_transactions
            {where_sql}
            ORDER BY occurred_at DESC, id DESC
            LIMIT ?
            OFFSET ?
            """,
            params,
        ).fetchall()

    return [_row_to_transaction(row) for row in rows]


def void_transaction(transaction_id: int) -> Transaction:
    migrate()

    updated_at = _now_iso()

    with transaction() as connection:
        cursor = connection.execute(
            """
            UPDATE finance_transactions
            SET status = 'voided',
                updated_at = ?
            WHERE id = ?
              AND status = 'posted'
            """,
            (updated_at, transaction_id),
        )

        if cursor.rowcount == 0:
            raise TransactionNotFoundError(
                f"Posted transaction not found: {transaction_id}"
            )

        row = connection.execute(
            """
            SELECT *
            FROM finance_transactions
            WHERE id = ?
            """,
            (transaction_id,),
        ).fetchone()

    if row is None:
        raise TransactionNotFoundError(f"Transaction not found: {transaction_id}")

    return _row_to_transaction(row)


def count_transactions(status: TransactionStatus | None = "posted") -> int:
    migrate()

    with transaction() as connection:
        if status is None:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM finance_transactions"
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM finance_transactions
                WHERE status = ?
                """,
                (status,),
            ).fetchone()

    return int(row["count"]) if row else 0


def create_sample_transaction() -> Transaction:
    return create_transaction(
        TransactionInput(
            type="expense",
            amount=28,
            currency="CNY",
            category="餐饮",
            description="买咖啡",
            occurred_at=date.today(),
            raw_text="今天买咖啡 28",
            source="manual",
        )
    )
