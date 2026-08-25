from __future__ import annotations

import json
from typing import Any

from reins.features.finance.tools import (
    export_finance_excel,
    list_finance_transactions,
    parse_transaction_text,
    record_transaction,
    record_transaction_from_text,
    summarize_finance_period,
)


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _missing_required_fields(params: dict[str, Any], fields: list[str]) -> list[str]:
    return [field for field in fields if params.get(field) in {None, ""}]


def _missing_fields_result(missing_fields: list[str]) -> str:
    labels = {
        "type": "收入或支出类型",
        "amount": "金额",
        "description": "用途或来源",
        "occurred_at": "交易日期",
    }
    missing_zh = "、".join(labels.get(field, field) for field in missing_fields)
    question = f"请补充这笔交易的{missing_zh}。"
    return _json_result({
        "ok": False,
        "needs_clarification": True,
        "missing_fields": missing_fields,
        "question_zh": question,
        "message": question,
    })


def register(ctx) -> None:
    register_parse_transaction_text(ctx)
    register_record_transaction(ctx)
    register_record_transaction_from_text(ctx)
    register_list_transactions(ctx)
    register_summarize_period(ctx)
    register_export_excel(ctx)


def register_parse_transaction_text(ctx) -> None:
    schema = {
        "name": "finance_parse_transaction_text",
        "description": (
            "解析中文财务文本并识别交易意图。Parse Chinese finance text into a "
            "transaction intent before recording natural-language input."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": 'Chinese finance text, for example: "今天买咖啡 28"',
                }
            },
            "required": ["text"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        text = str(params.get("text", ""))
        return _json_result(parse_transaction_text(text))

    ctx.register_tool(
        name="finance_parse_transaction_text",
        toolset="reins_finance",
        schema=schema,
        handler=handler,
        description="Parse Chinese finance text into structured transaction data.",
    )


def register_record_transaction(ctx) -> None:
    schema = {
        "name": "finance_record_transaction",
        "description": (
            "将字段完整的收入或支出记录到 Reins 本地财务数据库。仅在收入/支出类型、金额、"
            "用途或来源及日期都明确后调用；信息缺失时应先向用户提问。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["income", "expense"],
                    "description": "Transaction type.",
                },
                "amount": {
                    "type": "number",
                    "description": "Positive transaction amount.",
                },
                "currency": {
                    "type": "string",
                    "description": "Currency code. Default is CNY.",
                    "default": "CNY",
                },
                "category": {
                    "type": "string",
                    "description": "Category, for example 餐饮, 交通, 工资, 业务收入.",
                    "default": "其他",
                },
                "description": {
                    "type": "string",
                    "description": "Short transaction description.",
                },
                "occurred_at": {
                    "type": "string",
                    "description": "Transaction date in YYYY-MM-DD format.",
                },
                "counterparty": {
                    "type": ["string", "null"],
                    "description": "Optional counterparty.",
                },
                "payment_method": {
                    "type": ["string", "null"],
                    "description": "Optional payment method, for example 微信 or 支付宝.",
                },
                "raw_text": {
                    "type": ["string", "null"],
                    "description": "Original user text if available.",
                },
            },
            "required": ["type", "amount", "description", "occurred_at"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        missing_fields = _missing_required_fields(
            params,
            ["type", "amount", "description", "occurred_at"],
        )
        if missing_fields:
            return _missing_fields_result(missing_fields)
        payload = record_transaction(
            type=str(params["type"]),
            amount=float(params["amount"]),
            currency=str(params.get("currency") or "CNY"),
            category=str(params.get("category") or "其他"),
            description=str(params["description"]),
            occurred_at=str(params["occurred_at"]),
            counterparty=params.get("counterparty"),
            payment_method=params.get("payment_method"),
            raw_text=params.get("raw_text"),
            source="reins_brain",
        )
        return _json_result(payload)

    ctx.register_tool(
        name="finance_record_transaction",
        toolset="reins_finance",
        schema=schema,
        handler=handler,
        description="字段完整后记录 Reins 财务交易；字段缺失时先向用户提问。",
    )


def register_record_transaction_from_text(ctx) -> None:
    schema = {
        "name": "finance_record_transaction_from_text",
        "description": (
            "解析并记录信息完整的中文自然语言财务交易。仅在类型、金额和用途或来源明确时调用；"
            "如果内容不完整，先向用户提问。示例：今天买咖啡 28 元。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": 'Chinese finance text, for example: "今天买咖啡 28"',
                }
            },
            "required": ["text"],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        text = str(params.get("text", ""))
        return _json_result(record_transaction_from_text(text))

    ctx.register_tool(
        name="finance_record_transaction_from_text",
        toolset="reins_finance",
        schema=schema,
        handler=handler,
        description="解析并记录完整的中文财务交易；缺少信息时返回澄清问题。",
    )


def register_list_transactions(ctx) -> None:
    schema = {
        "name": "finance_list_transactions",
        "description": "查询 Reins 本地财务交易记录。List local finance transactions.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": ["string", "null"],
                    "description": "Start date in YYYY-MM-DD format.",
                },
                "end_date": {
                    "type": ["string", "null"],
                    "description": "End date in YYYY-MM-DD format.",
                },
                "type": {
                    "type": ["string", "null"],
                    "enum": ["income", "expense", None],
                    "description": "Optional transaction type filter.",
                },
                "category": {
                    "type": ["string", "null"],
                    "description": "Optional category filter.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of transactions to return.",
                    "default": 20,
                },
            },
            "required": [],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        payload = list_finance_transactions(
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
            type=params.get("type"),
            category=params.get("category"),
            limit=int(params.get("limit") or 20),
        )
        return _json_result(payload)

    ctx.register_tool(
        name="finance_list_transactions",
        toolset="reins_finance",
        schema=schema,
        handler=handler,
        description="List local Reins finance transactions.",
    )


def register_summarize_period(ctx) -> None:
    schema = {
        "name": "finance_summarize_period",
        "description": "汇总指定时间段内的收入、支出和净收支。Summarize finance activity for a period.",
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": ["string", "null"],
                    "description": (
                        "Optional period. Use this_month or month:YYYY-MM, "
                        "for example month:2026-05."
                    ),
                },
                "start_date": {
                    "type": ["string", "null"],
                    "description": "Start date in YYYY-MM-DD format.",
                },
                "end_date": {
                    "type": ["string", "null"],
                    "description": "End date in YYYY-MM-DD format.",
                },
            },
            "required": [],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        payload = summarize_finance_period(
            period=params.get("period"),
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
        )
        return _json_result(payload)

    ctx.register_tool(
        name="finance_summarize_period",
        toolset="reins_finance",
        schema=schema,
        handler=handler,
        description="Summarize local Reins finance transactions.",
    )


def register_export_excel(ctx) -> None:
    schema = {
        "name": "finance_export_excel",
        "description": (
            "将 Reins 财务数据导出为 Excel 工作簿，并保存到 Reins Workspace/Generated/Finance。"
            "Export finance data to an Excel workbook in the shared workspace."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": ["string", "null"],
                    "description": "Use this_month or month:YYYY-MM.",
                },
                "start_date": {
                    "type": ["string", "null"],
                    "description": "Start date in YYYY-MM-DD format.",
                },
                "end_date": {
                    "type": ["string", "null"],
                    "description": "End date in YYYY-MM-DD format.",
                },
            },
            "required": [],
        },
    }

    def handler(params: dict[str, Any], **kwargs) -> str:
        del kwargs
        return _json_result(export_finance_excel(
            period=params.get("period"),
            start_date=params.get("start_date"),
            end_date=params.get("end_date"),
        ))

    ctx.register_tool(
        name="finance_export_excel",
        toolset="reins_finance",
        schema=schema,
        handler=handler,
        description="导出 Reins 财务 Excel 工作簿。",
    )
