from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from reins.features.finance.chat import run_finance_chat_request
from reins.features.finance.classifier import classify_finance_intent
from reins.features.finance.export import export_transactions_to_xlsx
from reins.features.finance.parser import parse_finance_text
from reins.features.finance.hermes_plugin import register as register_finance_tools
from reins.features.finance.tools import record_transaction_from_text


class FinanceChineseChatTests(unittest.TestCase):
    def test_brain_tool_requests_clarification_for_incomplete_transaction(self) -> None:
        result = record_transaction_from_text("帮我记录一笔午餐支出")

        self.assertFalse(result["ok"])
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["missing_fields"], ["amount"])
        self.assertIn("金额是多少", result["question_zh"])

    def test_structured_brain_tool_does_not_throw_when_required_fields_are_missing(self) -> None:
        registered: dict[str, object] = {}

        class FakeContext:
            def register_tool(self, **kwargs) -> None:
                registered[kwargs["name"]] = kwargs["handler"]

        register_finance_tools(FakeContext())
        handler = registered["finance_record_transaction"]
        result = json.loads(handler({"amount": 30}))

        self.assertFalse(result["ok"])
        self.assertTrue(result["needs_clarification"])
        self.assertIn("type", result["missing_fields"])
        self.assertIn("description", result["missing_fields"])
        self.assertIn("occurred_at", result["missing_fields"])
        self.assertIn("请补充", result["question_zh"])
        self.assertIn("finance_export_excel", registered)

    def test_record_command_is_not_misclassified_as_history_query(self) -> None:
        parsed = parse_finance_text("记录一笔午餐支出30元", today=date(2026, 8, 25))

        self.assertEqual(parsed.intent, "record_expense")
        self.assertEqual(parsed.transaction.amount, 30)
        self.assertEqual(parsed.transaction.category, "餐饮")
        self.assertEqual(parsed.transaction.description, "午餐支出")

    def test_recognizes_chinese_queries_summaries_and_excel_exports(self) -> None:
        self.assertEqual(classify_finance_intent("查看本月交易记录").intent, "query_transactions")
        self.assertEqual(classify_finance_intent("本月财务情况怎么样").intent, "query_summary")
        self.assertEqual(classify_finance_intent("导出本月财务Excel").intent, "export_excel")
        self.assertEqual(classify_finance_intent("制作财务预算表格").intent, "unknown")
        self.assertEqual(
            parse_finance_text("查看最近10笔流水", today=date(2026, 8, 25)).limit,
            10,
        )

    def test_chinese_chat_records_and_summarizes_the_same_local_database(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {"REINS_HOME": directory},
            clear=False,
        ):
            recorded = run_finance_chat_request("今天午餐支出30元", today=date(2026, 8, 25))
            summary = run_finance_chat_request("查看本月财务汇总", today=date(2026, 8, 25))

        self.assertTrue(recorded["ok"])
        self.assertEqual(recorded["transaction"]["amount"], 30)
        self.assertIn("已记录支出", recorded["message_zh"])
        self.assertEqual(summary["summary"]["total_expense"], 30)
        self.assertIn("交易笔数：1", summary["message_zh"])

    def test_missing_amount_returns_a_conversational_clarification(self) -> None:
        result = run_finance_chat_request("帮我记录一笔午餐支出", today=date(2026, 8, 25))

        self.assertTrue(result["handled"])
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["pending_text"], "帮我记录一笔午餐支出")
        self.assertIn("金额是多少", result["message_zh"])
        self.assertNotIn("error", result)

    def test_missing_transaction_type_returns_a_conversational_clarification(self) -> None:
        result = run_finance_chat_request("帮我记账30元", today=date(2026, 8, 25))

        self.assertTrue(result["handled"])
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["pending_text"], "帮我记账30元")
        self.assertIn("收入还是支出", result["message_zh"])

    def test_excel_export_uses_officecli_renderer_in_the_workspace(self) -> None:
        captured: dict[str, object] = {}

        def fake_render(**kwargs):
            captured.update(kwargs)
            path = Path(kwargs["output_path"])
            path.touch()
            return path

        with TemporaryDirectory() as directory, patch.dict(
            os.environ,
            {
                "REINS_HOME": str(Path(directory) / "state"),
                "REINS_WORKSPACE_ROOT": str(Path(directory) / "workspace"),
            },
            clear=False,
        ), patch("reins.features.finance.export.render_office_content", side_effect=fake_render):
            run_finance_chat_request("今天午餐支出30元", today=date(2026, 8, 25))
            run_finance_chat_request("今天收到工资100元", today=date(2026, 8, 25))
            output = export_transactions_to_xlsx(
                start_date=date(2026, 8, 1),
                end_date=date(2026, 8, 31),
                transaction_type="expense",
            )

        self.assertEqual(captured["office_format"], "xlsx")
        content = captured["content"]
        self.assertEqual([sheet["name"] for sheet in content["sheets"]], ["财务汇总", "分类统计", "交易明细"])
        self.assertEqual(content["sheets"][0]["rows"][-1], ["交易笔数", 1])
        self.assertEqual(content["sheets"][2]["rows"][0][2], "支出")
        self.assertIn("Generated/Finance", output.as_posix())
        self.assertEqual(output.suffix, ".xlsx")


if __name__ == "__main__":
    unittest.main()
