from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reins.features.wecom.chat import (
    export_work_orders_excel,
    get_work_order,
    list_work_orders,
    summarize_work_orders,
)
from reins.features.wecom.store import add_record


class WeComChatToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.environment = patch.dict(
            os.environ,
            {
                "REINS_HOME": str(root / "reins-home"),
                "REINS_WORKSPACE_ROOT": str(root / "Reins Workspace"),
            },
            clear=True,
        )
        self.environment.start()

        add_record(
            kind="work_order",
            status="open",
            message=(
                "客户标识：resident-private-id\n"
                "A栋楼道垃圾未清理，联系电话：13800138000"
            ),
            metadata={
                "external_id": "t_cleaning_001",
                "ticket_created_at": "2026-08-20 09:30:00",
                "priority": "high",
                "category": "公共区域清扫",
                "assigned_role": "cleaning",
                "assigned_role_label": "保洁",
                "location": "A栋3楼",
                "description": "楼道垃圾未清理，联系电话：13800138000",
                "handling_requirements": "今日处理",
                "resident_contact": "13800138000",
                "notification_status": "failed",
                "source_channel": "wecom",
            },
        )
        add_record(
            kind="work_order",
            status="resolved",
            message="路灯故障",
            reply="已恢复照明",
            metadata={
                "external_id": "t_property_002",
                "ticket_created_at": "2026-07-15 11:00:00",
                "priority": "normal",
                "category": "公共设施维修",
                "assigned_role": "property",
                "assigned_role_label": "物业维修",
                "location": "B栋门口",
                "description": "路灯故障",
                "notification_status": "sent",
                "last_staff_reply": "已恢复照明",
            },
        )

    def tearDown(self) -> None:
        self.environment.stop()
        self.temp_dir.cleanup()

    def test_summary_supports_dates_and_chinese_statuses(self) -> None:
        august = summarize_work_orders(
            start_date="2026-08-01",
            end_date="2026-08-31",
        )
        self.assertEqual(august["total"], 1)
        self.assertEqual(august["pending"], 1)
        self.assertEqual(august["urgent"], 1)
        self.assertEqual(august["notification_failed"], 1)

        pending = list_work_orders(status="待处理")
        self.assertEqual(pending["total"], 1)
        self.assertEqual(pending["records"][0]["external_id"], "t_cleaning_001")

        completed = list_work_orders(status="已完成")
        self.assertEqual(completed["total"], 1)
        self.assertEqual(completed["records"][0]["external_id"], "t_property_002")

    def test_list_and_detail_hide_resident_private_data(self) -> None:
        listed = list_work_orders(search="垃圾", role="保洁")
        self.assertEqual(listed["total"], 1)
        serialized = str(listed)
        self.assertNotIn("resident-private-id", serialized)
        self.assertNotIn("13800138000", serialized)
        self.assertNotIn("resident_contact", serialized)
        self.assertIn("[已隐藏联系方式]", serialized)

        detail = get_work_order("t_cleaning_001")
        self.assertTrue(detail["ok"])
        self.assertEqual(detail["record"]["assigned_role_label"], "保洁")
        self.assertFalse(get_work_order("")["ok"])
        self.assertTrue(get_work_order("")["needs_clarification"])

    def test_exports_workbook_to_reins_workspace(self) -> None:
        result = export_work_orders_excel()
        self.assertTrue(result["ok"])
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "社区工单台账.xlsx")
        self.assertEqual(path.parent.name, "Work Orders")
        self.assertEqual(path.parent.parent.name, "Generated")


if __name__ == "__main__":
    unittest.main()
