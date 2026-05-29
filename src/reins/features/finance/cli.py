from __future__ import annotations

from datetime import date
from typing import Sequence

from reins.features.finance.db import doctor as db_doctor
from reins.features.finance.errors import FinanceError
from reins.features.finance.formatter import (
    format_parsed_intent,
    format_summary_report,
    format_transaction,
    format_transaction_created,
)
from reins.features.finance.parser import parse_finance_text
from reins.features.finance.reports import current_month_range, parse_month, summarize_period
from reins.features.finance.repository import (
    create_sample_transaction,
    create_transaction,
    list_transactions,
    void_transaction,
)
from reins.features.finance.schema import TransactionFilter

# tools
from reins.features.finance.tools import (
    list_finance_transactions,
    parse_transaction_text,
    record_transaction_from_text,
    summarize_finance_period,
)

# Finance Plugin
from reins.features.finance.plugin_installer import (
    install_hermes_plugin,
    print_install_instructions,
)

# Export finance data into CSV
from reins.features.finance.export import export_transactions_to_csv, parse_export_args


def print_finance_help() -> None:
    print(
        """Reins Finance

Usage:
  reins finance [command]

Commands:
  doctor                    Check finance database status
  parse <text>              Parse finance natural language text
  add <text>                Add a transaction from natural language
  sample                    Insert a sample coffee transaction
  list                      List recent posted transactions
  list --month YYYY-MM      List transactions for a month
  list --limit N            Limit the number of returned transactions
  report                    Show current month report
  report --month YYYY-MM    Show report for a month
  void <id>                 Void a posted transaction
  tool-test <text>          Test the finance tools API
  install-plugin            Install finance plugin
  export csv                Export posted transactions to CSV
  export csv --month YYYY-MM
  export csv --output PATH
  export csv --include-voided

Examples:
  reins finance doctor
  reins finance parse "今天买咖啡 28"
  reins finance add "今天买咖啡 28"
  reins finance add "昨天打车 45"
  reins finance add "收到客户转账 3000"
  reins finance list
  reins finance list --month 2026-05
  reins finance list --limit 10
  reins finance report
  reins finance report --month 2026-05
  reins finance void 1
  reins finance tool-test "今天买咖啡 28"
  reins finance install-plugin
  reins finance export csv
  reins finance export csv --month 2026-05
  reins finance export csv --output ~/Desktop/reins-finance.csv
"""
    )


def _parse_month_option(argv: Sequence[str]) -> tuple[date | None, date | None]:
    if "--month" not in argv:
        return None, None

    index = argv.index("--month")

    if index + 1 >= len(argv):
        raise FinanceError("Missing month value. Use: --month YYYY-MM")

    return parse_month(argv[index + 1])


def _parse_limit_option(argv: Sequence[str], default: int = 20) -> int:
    if "--limit" not in argv:
        return default

    index = argv.index("--limit")

    if index + 1 >= len(argv):
        raise FinanceError("Missing limit value. Use: --limit 20")

    try:
        value = int(argv[index + 1])
    except ValueError as exc:
        raise FinanceError("Limit must be a number.") from exc

    if value <= 0:
        raise FinanceError("Limit must be greater than zero.")

    return value


def handle_doctor() -> int:
    return db_doctor()


def handle_parse(argv: Sequence[str]) -> int:
    if not argv:
        print('Usage: reins finance parse "今天买咖啡 28"')
        return 1

    text = " ".join(argv)

    try:
        parsed = parse_finance_text(text)
    except FinanceError as exc:
        print(f"Finance error: {exc}")
        return 1

    print(format_parsed_intent(parsed))
    return 0


def handle_add(argv: Sequence[str]) -> int:
    if not argv:
        print('Usage: reins finance add "今天买咖啡 28"')
        return 1

    text = " ".join(argv)

    try:
        parsed = parse_finance_text(text)
    except FinanceError as exc:
        print(f"Finance error: {exc}")
        return 1

    if parsed.intent not in {"record_expense", "record_income"}:
        print("This does not look like an income or expense transaction.")
        print('Example: reins finance add "今天买咖啡 28"')
        return 1

    if parsed.missing_fields:
        if "amount" in parsed.missing_fields:
            print("Missing amount. How much was this transaction?")
            return 1

        print(f"Missing fields: {', '.join(parsed.missing_fields)}")
        return 1

    if parsed.transaction is None:
        print("Could not create a transaction from this text.")
        return 1

    try:
        tx = create_transaction(parsed.transaction)
    except FinanceError as exc:
        print(f"Finance error: {exc}")
        return 1

    print(format_transaction_created(tx))
    return 0


def handle_sample() -> int:
    try:
        tx = create_sample_transaction()
    except FinanceError as exc:
        print(f"Finance error: {exc}")
        return 1

    print("Sample transaction created:")
    print(format_transaction(tx))
    return 0


def handle_list(argv: Sequence[str]) -> int:
    try:
        start_date, end_date = _parse_month_option(argv)
        limit = _parse_limit_option(argv, default=20)

        transactions = list_transactions(
            TransactionFilter(
                start_date=start_date,
                end_date=end_date,
                status="posted",
                limit=limit,
            )
        )
    except FinanceError as exc:
        print(f"Finance error: {exc}")
        return 1

    if not transactions:
        print("No transactions found for this period.")
        return 0

    for tx in transactions:
        print(format_transaction(tx))

    return 0


def handle_report(argv: Sequence[str]) -> int:
    try:
        start_date, end_date = _parse_month_option(argv)

        if start_date is None or end_date is None:
            start_date, end_date = current_month_range()

        report = summarize_period(start_date, end_date)
    except FinanceError as exc:
        print(f"Finance error: {exc}")
        return 1

    print(format_summary_report(report))
    return 0


def handle_void(argv: Sequence[str]) -> int:
    if not argv:
        print("Usage: reins finance void <id>")
        return 1

    try:
        transaction_id = int(argv[0])
    except ValueError:
        print(f"Invalid transaction id: {argv[0]}")
        return 1

    try:
        tx = void_transaction(transaction_id)
    except FinanceError as exc:
        print(f"Finance error: {exc}")
        return 1

    print("Transaction voided:")
    print(format_transaction(tx))
    return 0


# Tools
def handle_tool_test(argv: Sequence[str]) -> int:
    if not argv:
        print('Usage: reins finance tool-test "今天买咖啡 28"')
        return 1

    text = " ".join(argv)

    parsed = parse_transaction_text(text)
    print("parse_transaction_text:")
    print(parsed)
    print()

    recorded = record_transaction_from_text(text)
    print("record_transaction_from_text:")
    print(recorded)
    print()

    listed = list_finance_transactions(limit=5)
    print("list_finance_transactions:")
    print(listed)
    print()

    summary = summarize_finance_period(period="this_month")
    print("summarize_finance_period:")
    print(summary)

    return 0


# Finance plugins functions
def handle_install_plugin() -> int:
    plugin_dir = install_hermes_plugin()
    print_install_instructions(plugin_dir)
    return 0

# Export as CSV
def handle_export(argv: Sequence[str]) -> int:
    if not argv:
        print("Usage: reins finance export csv [--month YYYY-MM] [--output PATH] [--include-voided]")
        return 1

    export_type = argv[0]

    if export_type != "csv":
        print(f"Unknown export type: {export_type}")
        print("Supported export types: csv")
        return 1

    try:
        options = parse_export_args(argv[1:])

        output_path = export_transactions_to_csv(
            output_path=options["output_path"],  # type: ignore[arg-type]
            month=options["month"],  # type: ignore[arg-type]
            include_voided=bool(options["include_voided"]),
        )
    except FinanceError as exc:
        print(f"Finance error: {exc}")
        return 1

    print("Finance transactions exported.")
    print(f"Output: {output_path}")
    return 0

def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = []

    if not argv or argv[0] in {"-h", "--help", "help"}:
        print_finance_help()
        return 0

    command = argv[0]

    if command == "doctor":
        return handle_doctor()

    if command == "parse":
        return handle_parse(argv[1:])

    if command == "add":
        return handle_add(argv[1:])

    if command == "sample":
        return handle_sample()

    if command == "list":
        return handle_list(argv[1:])

    if command == "report":
        return handle_report(argv[1:])

    if command == "void":
        return handle_void(argv[1:])

    if command == "tool-test":
        return handle_tool_test(argv[1:])

    if command == "install-plugin":
        return handle_install_plugin()
    
    if command == "export":
        return handle_export(argv[1:])

    print(f"Unknown finance command: {command}")
    print("Run `reins finance --help` for available commands.")
    return 1
