from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

from reins.compat.paths import reins_workspace_dir
from reins.features.finance.errors import FinanceError
from reins.features.finance.repository import list_transactions
from reins.features.finance.reports import current_month_range, parse_month
from reins.features.finance.schema import TransactionFilter
from reins.features.office.officecli_client import OfficeCliClient
from reins.features.office.renderer import render_office_content


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


def default_xlsx_export_path() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    return get_export_dir() / f"财务收支-{timestamp}.xlsx"


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
    transaction_type: str | None = None,
    category: str | None = None,
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
            type=transaction_type,  # type: ignore[arg-type]
            category=category,
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


def export_transactions_to_xlsx(
    output_path: Path | None = None,
    month: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    include_voided: bool = False,
    transaction_type: str | None = None,
    category: str | None = None,
    limit: int = 100_000,
    client: OfficeCliClient | None = None,
) -> Path:
    if month:
        start_date, end_date = parse_month(month)
    elif start_date is None and end_date is None:
        start_date, end_date = current_month_range()
    elif start_date is None or end_date is None:
        raise FinanceError("Excel export requires both start_date and end_date.")

    status = None if include_voided else "posted"
    transactions = list_transactions(
        TransactionFilter(
            start_date=start_date,
            end_date=end_date,
            type=transaction_type,  # type: ignore[arg-type]
            category=category,
            status=status,  # type: ignore[arg-type]
            limit=limit,
        )
    )
    output_path = (output_path or default_xlsx_export_path()).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_income = sum(tx.amount for tx in transactions if tx.type == "income")
    total_expense = sum(tx.amount for tx in transactions if tx.type == "expense")
    income_by_category: dict[str, float] = {}
    expense_by_category: dict[str, float] = {}
    for tx in transactions:
        target = income_by_category if tx.type == "income" else expense_by_category
        target[tx.category] = target.get(tx.category, 0.0) + tx.amount

    period_label = f"{start_date.isoformat()} 至 {end_date.isoformat()}"
    summary_rows = [
        ["统计区间", period_label],
        ["总收入", total_income],
        ["总支出", total_expense],
        ["净收支", total_income - total_expense],
        ["交易笔数", len(transactions)],
    ]
    category_rows = [
        *[["收入", item_category, amount] for item_category, amount in income_by_category.items()],
        *[["支出", item_category, amount] for item_category, amount in expense_by_category.items()],
    ]
    transaction_rows = [
        [
            tx.id,
            tx.occurred_at.isoformat(),
            "收入" if tx.type == "income" else "支出",
            tx.amount,
            tx.currency,
            tx.category,
            tx.description,
            tx.counterparty or "",
            tx.payment_method or "",
        ]
        for tx in transactions
    ]
    content = {
        "title": f"财务收支报表 {start_date.strftime('%Y-%m')}",
        "body": f"Reins 财务数据，统计区间：{period_label}",
        "design": {
            "style": "financial",
            "header_style": "dark",
            "row_density": "comfortable",
            "table_style": "medium2",
            "show_title": True,
            "banded_rows": True,
            "zoom": 95,
        },
        "sheets": [
            {
                "name": "财务汇总",
                "subtitle": period_label,
                "headers": ["指标", "数值"],
                "rows": summary_rows,
                "column_widths": [20, 26],
            },
            {
                "name": "分类统计",
                "subtitle": "按收入与支出分类汇总",
                "headers": ["类型", "分类", "金额"],
                "rows": category_rows,
                "column_widths": [12, 24, 16],
                "column_formats": [{"column": "金额", "format": "currency"}],
            },
            {
                "name": "交易明细",
                "subtitle": f"共 {len(transactions)} 笔已入账交易",
                "headers": ["编号", "日期", "类型", "金额", "币种", "分类", "说明", "交易对象", "支付方式"],
                "rows": transaction_rows,
                "column_widths": [10, 14, 10, 14, 10, 16, 32, 20, 16],
                "column_formats": [
                    {"column": "编号", "format": "integer"},
                    {"column": "日期", "format": "date"},
                    {"column": "金额", "format": "currency"},
                ],
                "conditional_highlights": [
                    {"column": "类型", "contains": "支出", "fill": "FDE8E7"},
                    {"column": "类型", "contains": "收入", "fill": "DCFCE7"},
                ],
            },
        ],
    }
    return render_office_content(
        office_format="xlsx",
        content=content,
        output_path=output_path,
        client=client,
    )


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
