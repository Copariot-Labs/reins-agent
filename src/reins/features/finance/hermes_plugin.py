from __future__ import annotations

import json
from typing import Any

from reins.features.finance.tools import (
    list_finance_transactions,
    parse_transaction_text,
    record_transaction,
    record_transaction_from_text,
    summarize_finance_period,
)


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def register(ctx) -> None:
    register_parse_transaction_text(ctx)
    register_record_transaction(ctx)
    register_record_transaction_from_text(ctx)
    register_list_transactions(ctx)
    register_summarize_period(ctx)


def register_parse_transaction_text(ctx) -> None:
    schema = {
        "name": "finance_parse_transaction_text",
        "description": (
            "Parse Chinese finance text into a transaction intent. "
            "Use this before recording if the user gave natural-language Chinese input."
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
            "Record a finance transaction into the local Reins finance database. "
            "Use this when transaction fields are already known."
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
            source="hermes_tool",
        )
        return _json_result(payload)

    ctx.register_tool(
        name="finance_record_transaction",
        toolset="reins_finance",
        schema=schema,
        handler=handler,
        description="Record a local Reins finance transaction.",
    )


def register_record_transaction_from_text(ctx) -> None:
    schema = {
        "name": "finance_record_transaction_from_text",
        "description": (
            "Parse and record a Chinese natural-language finance transaction. "
            "Use this for inputs like 今天买咖啡 28 or 收到客户转账 3000."
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
        description="Parse and record a Chinese finance transaction.",
    )


def register_list_transactions(ctx) -> None:
    schema = {
        "name": "finance_list_transactions",
        "description": "List local Reins finance transactions.",
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
        "description": "Summarize local Reins finance income and expenses for a period.",
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