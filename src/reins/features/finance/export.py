from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from reins.compat.paths import reins_workspace_dir
from reins.features.finance.errors import FinanceError
from reins.features.finance.repository import list_transactions
from reins.features.finance.reports import parse_month
from reins.features.finance.schema import TransactionFilter


CSV_COLUMNS = [
    "id",
    "type",
    "amount",
    "currency",
    "category",
    "description",
    "counterparty",
    "payment_method",
    "occurred_at",
    "created_at",
    "updated_at",
    # "source",
    # "raw_text",
    # "status",
]


def get_export_dir() -> Path:
    export_dir = reins_workspace_dir("Generated") / "Finance"
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir


def default_export_path() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    return get_export_dir() / f"transactions-{timestamp}.csv"


def transaction_to_csv_row(tx) -> dict[str, object]:
    return {
        "id": tx.id,
        "type": tx.type,
        "amount": tx.amount,
        "currency": tx.currency,
        "category": tx.category,
        "description": tx.description,
        "counterparty": tx.counterparty or "",
        "payment_method": tx.payment_method or "",
        "occurred_at": tx.occurred_at.isoformat(),
        "created_at": tx.created_at.isoformat(),
        "updated_at": tx.updated_at.isoformat() if tx.updated_at else "",
        # "source": tx.source,
        # "raw_text": tx.raw_text or "",
        # "status": tx.status,
    }


def export_transactions_to_csv(
    output_path: Path | None = None,
    month: str | None = None,
    include_voided: bool = False,
    limit: int = 100_000,
) -> Path:
    start_date = None
    end_date = None

    if month:
        start_date, end_date = parse_month(month)

    status = None if include_voided else "posted"

    transactions = list_transactions(
        TransactionFilter(
            start_date=start_date,
            end_date=end_date,
            status=status,  # type: ignore[arg-type]
            limit=limit,
        )
    )

    if output_path is None:
        output_path = default_export_path()
    else:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        for tx in transactions:
            writer.writerow(transaction_to_csv_row(tx))

    return output_path


def parse_export_args(argv: Sequence[str]) -> dict[str, object]:
    month = None
    output_path = None
    include_voided = False

    if "--month" in argv:
        index = argv.index("--month")

        if index + 1 >= len(argv):
            raise FinanceError("Missing month value. Use: --month YYYY-MM")

        month = argv[index + 1]

    if "--output" in argv:
        index = argv.index("--output")

        if index + 1 >= len(argv):
            raise FinanceError("Missing output path. Use: --output path/to/file.csv")

        output_path = Path(argv[index + 1])

    if "--include-voided" in argv:
        include_voided = True

    unknown_args = [
        arg
        for arg in argv
        if arg not in {
            "--month",
            "--output",
            "--include-voided",
        }
    ]

    # Remove values that belong to known flags.
    if "--month" in argv:
        month_index = argv.index("--month")
        if month_index + 1 < len(argv) and argv[month_index + 1] in unknown_args:
            unknown_args.remove(argv[month_index + 1])

    if "--output" in argv:
        output_index = argv.index("--output")
        if output_index + 1 < len(argv) and argv[output_index + 1] in unknown_args:
            unknown_args.remove(argv[output_index + 1])

    if unknown_args:
        raise FinanceError(f"Unknown export option: {unknown_args[0]}")

    return {
        "month": month,
        "output_path": output_path,
        "include_voided": include_voided,
    }
