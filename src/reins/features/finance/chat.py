from __future__ import annotations

from datetime import date
import re
from typing import Any

from reins.features.finance.errors import FinanceError
from reins.features.finance.export import export_transactions_to_xlsx
from reins.features.finance.formatter import format_money
from reins.features.finance.parser import parse_finance_text
from reins.features.finance.reports import summarize_period
from reins.features.finance.repository import create_transaction, list_transactions
from reins.features.finance.schema import Transaction, TransactionFilter


def _transaction_dict(tx: Transaction) -> dict[str, Any]:
    return {
        "id": tx.id,
        "type": tx.type,
        "amount": tx.amount,
        "currency": tx.currency,
        "category": tx.category,
        "description": tx.description,
        "occurred_at": tx.occurred_at.isoformat(),
        "counterparty": tx.counterparty,
        "payment_method": tx.payment_method,
    }


def _base_result(text: str, action: str) -> dict[str, Any]:
    return {
        "handled": True,
        "ok": True,
        "action": action,
        "raw_text": text,
        "needs_clarification": False,
        "message_zh": "",
        "message_en": "",
    }


def run_finance_chat_request(text: str, today: date | None = None) -> dict[str, Any]:
    try:
        parsed = parse_finance_text(text, today=today)
        if parsed.intent == "unknown" or parsed.confidence < 0.75:
            if re.search(r"(?:记账|记一笔|记录一笔|新增一笔|添加一笔|录入一笔)", text):
                result = _base_result(text, "clarify_transaction_type")
                result.update({
                    "needs_clarification": True,
                    "pending_text": text,
                    "message_zh": "这笔交易是收入还是支出？请直接回复“收入”或“支出”。",
                    "message_en": "Is this transaction income or an expense? Reply with income or expense.",
                })
                return result
            return {"handled": False, "ok": True, "action": "unknown", "raw_text": text}

        result = _base_result(text, parsed.intent)
        if parsed.intent in {"record_expense", "record_income"}:
            if "amount" in parsed.missing_fields:
                result.update({
                    "needs_clarification": True,
                    "pending_text": text,
                    "message_zh": "这笔交易的金额是多少？请直接回复金额，例如“28 元”。",
                    "message_en": "How much was this transaction? Reply with an amount, for example, CNY 28.",
                })
                return result
            if parsed.transaction is None:
                result.update({
                    "needs_clarification": True,
                    "pending_text": text,
                    "message_zh": "请补充交易金额、用途或来源，我会继续记录这笔交易。",
                    "message_en": "Please provide the amount and purpose or source so I can record the transaction.",
                })
                return result
            tx = create_transaction(parsed.transaction)
            tx_type = "收入" if tx.type == "income" else "支出"
            result.update({
                "transaction": _transaction_dict(tx),
                "message_zh": "\n".join([
                    f"已记录{tx_type}：{format_money(tx.amount, tx.currency)}",
                    f"- 分类：{tx.category}",
                    f"- 日期：{tx.occurred_at.isoformat()}",
                    f"- 说明：{tx.description}",
                    f"- 编号：{tx.id}",
                ]),
                "message_en": f"Recorded {tx.type}: {format_money(tx.amount, tx.currency)} (ID {tx.id}).",
            })
            return result

        start_date = parsed.start_date
        end_date = parsed.end_date
        if start_date is None or end_date is None:
            raise FinanceError("Could not determine the finance period.")

        if parsed.intent == "query_transactions":
            transactions = list_transactions(TransactionFilter(
                start_date=start_date,
                end_date=end_date,
                status="posted",
                limit=parsed.limit or 20,
            ))
            rows = [_transaction_dict(tx) for tx in transactions]
            if rows:
                lines = [f"找到 {len(rows)} 笔交易："]
                for tx in transactions:
                    tx_type = "收入" if tx.type == "income" else "支出"
                    lines.append(
                        f"- #{tx.id} {tx.occurred_at.isoformat()} {tx_type} "
                        f"{format_money(tx.amount, tx.currency)} · {tx.category} · {tx.description}"
                    )
                message_zh = "\n".join(lines)
            else:
                message_zh = "该时间段内暂无交易记录。"
            result.update({
                "transactions": rows,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "message_zh": message_zh,
                "message_en": f"Found {len(rows)} transactions for this period.",
            })
            return result

        report = summarize_period(start_date, end_date)
        period_transactions = list_transactions(TransactionFilter(
            start_date=start_date,
            end_date=end_date,
            status="posted",
            limit=100_000,
        ))
        if parsed.intent == "query_summary":
            result.update({
                "summary": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "total_income": report.total_income,
                    "total_expense": report.total_expense,
                    "net": report.net,
                    "income_by_category": report.income_by_category,
                    "expense_by_category": report.expense_by_category,
                },
                "message_zh": "\n".join([
                    f"财务汇总：{start_date.isoformat()} 至 {end_date.isoformat()}",
                    f"- 总收入：{format_money(report.total_income)}",
                    f"- 总支出：{format_money(report.total_expense)}",
                    f"- 净收支：{format_money(report.net)}",
                    f"- 交易笔数：{len(period_transactions)}",
                ]),
                "message_en": (
                    f"Finance summary: income {format_money(report.total_income)}, "
                    f"expense {format_money(report.total_expense)}, net {format_money(report.net)}."
                ),
            })
            return result

        if parsed.intent == "export_excel":
            path = export_transactions_to_xlsx(start_date=start_date, end_date=end_date)
            result.update({
                "file": {
                    "path": str(path),
                    "file_name": path.name,
                    "kind": "xlsx",
                },
                "message_zh": f"财务 Excel 工作簿已生成，共导出 {len(period_transactions)} 笔交易。",
                "message_en": "The finance Excel workbook has been generated.",
            })
            return result

        return {"handled": False, "ok": True, "action": "unknown", "raw_text": text}
    except Exception as exc:
        return {
            "handled": True,
            "ok": False,
            "action": "error",
            "raw_text": text,
            "needs_clarification": False,
            "message_zh": "财务操作未完成，请稍后重试。",
            "message_en": "The finance operation did not complete. Please try again.",
            "error": str(exc),
        }
