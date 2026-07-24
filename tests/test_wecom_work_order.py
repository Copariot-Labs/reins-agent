from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from reins.features.wecom import notifier
from reins.features.wecom.hermes_plugin import register as register_hermes_tools
from reins.features.wecom.plugin_installer import install_hermes_plugin
from reins.features.wecom.work_order import create_work_order, parse_work_order_message


TEST_GROUP_WEBHOOK = (
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-group-robot-key"
)


PRODUCTION_WECOM_TICKET = """待处理工单：待处理工单
· 工单号：t_89751e8754e44289
· 优先级：normal
· 来源：微信客服·工单补充
· 类别：community_sanitation

· 状态：待工作人员跟进
· 生成时间：2026-07-17 15:17:28 CST

客户描述
客户原话：我要报保洁：A栋楼道垃圾没人清理，需要保洁处理。位置：A栋3楼。

已核实信息
· 工单类别：公共区域清扫
· 微信客户：redacted-wechat-customer-reference
· 地点：A栋3楼
· 问题/现象：楼道垃圾无人清理
· 客户原话：我要报保洁：A栋楼道垃圾没人清理，需要保洁处理。位置：A栋3楼。

客服研判
居民报告A栋3楼楼道垃圾无人清理，需要保洁处理。

处理要求
请尽快联系或到场处理；处理后在企业微信同步结果。"""

REPAIR_WECOM_TICKET = """待处理工单：优先工单
· 工单号：t_b20df17d855f4130
· 优先级：high
· 来源：微信客服·工单补充
· 类别：community_repair

· 状态：待工作人员跟进
· 生成时间：2026-07-17 16:01:01 CST

客户描述
客户原话：B栋401卫生间漏水，需要维修

已核实信息
· 工单类别：公共设施维修
· 微信客户：redacted-wechat-customer-reference
· 地点：B栋401
· 问题/现象：卫生间漏水
· 客户原话：B栋401卫生间漏水，需要维修

客服研判
居民报告B栋401卫生间漏水，需要维修。

处理要求
请尽快联系或到场处理；处理后在企业微信同步结果。"""

EMERGENCY_WECOM_TICKET = """【新建工单】
工单编号：t_27f4f7b483174238
处理状态：待处理
优先级：紧急
问题类别：危急事件
消息来源：微信客服
生成时间：2026-07-17 17:00:06（北京时间）
【客户诉求】
客户原话：心脏不舒服，药吃完了，快帮忙
【已确认信息】
- 地点：6栋3单元502
- 问题/现象：心脏不舒服，药吃完了，需要帮助
- 涉及人员：1
- 当前危险：是
【客服判断】
居民心脏不舒服，药吃完了，需要紧急帮助。位置：6栋3单元502。
【处理要求】
请尽快联系或到场处理；完成后在本群同步结果。
【系统信息】
客户标识：redacted-wechat-customer-reference
【工单结束】"""

SCREENSHOT_WECOM_TICKET = """【新建工单】
工单编号：t_3ab6a6d8f17648ad
处理状态：待处理
优先级：紧急
问题类别：危急事件
消息来源：微信居民消息
生成时间：2026-07-20 08:05:34（北京时间）
【居民诉求】
居民原话：居民反映6栋2单元602有人多次将电动车推进楼道充电，昨晚仍在充电，疑似飞线充电且通道有遮挡。
【已确认信息】
- 地点：6栋2单元602
- 问题/现象：有人多次将电动车推进楼道充电，疑似存在飞线充电，通道有一定遮挡。
- 联系方式：136886886886
【网格员研判】
居民反映6栋2单元602有人多次将电动车推进楼道充电，疑似存在飞线充电，通道有一定遮挡。
【处理要求】
请尽快联系或到场处理；完成后在本群同步结果。
【系统信息】
居民标识：wmvlKYcAAAcuk-t3-61mAc2tStCYuNKA
【工单结束】"""

MENTIONED_POWER_OUTAGE_TICKET = """@社区美女
【新建工单】
工单编号：t_a04299d4b5e34bb4
处理状态：待处理
优先级：优先
问题类别：公共设施维修
消息来源：微信居民消息
生成时间：2026-07-22 10:53:18（北京时间）
【居民诉求】
居民原话：3栋 404 没电了
【已确认信息】
- 地点：3栋404
- 问题/现象：停电
【网格员研判】
居民反映3栋404没电了
【处理要求】
请尽快联系或到场处理；完成后在本群同步结果。
【系统信息】
居民标识：wmvlKYcAAAVUcll6OBn5cwI6JnqPcN2g
【工单结束】"""


class WeComWorkOrderTests(unittest.TestCase):
    def test_ignores_reins_staff_notification_to_prevent_group_loops(self):
        self.assertEqual(
            parse_work_order_message(
                "【Reins工单提醒】请物业跟进\n工单编号：t_loop_test\n标题：卫生间漏水"
            ),
            {},
        )

    def test_parses_production_chinese_ticket_template(self):
        parsed = parse_work_order_message(PRODUCTION_WECOM_TICKET)

        self.assertEqual(parsed["external_id"], "t_89751e8754e44289")
        self.assertEqual(parsed["priority"], "normal")
        self.assertEqual(parsed["source_channel"], "微信客服·工单补充")
        self.assertEqual(parsed["category"], "公共区域清扫")
        self.assertEqual(parsed["original_category"], "community_sanitation")
        self.assertEqual(parsed["upstream_status"], "待工作人员跟进")
        self.assertEqual(parsed["ticket_created_at"], "2026-07-17 15:17:28 CST")
        self.assertEqual(parsed["resident_ref"], "redacted-wechat-customer-reference")
        self.assertEqual(parsed["location"], "A栋3楼")
        self.assertEqual(parsed["title"], "楼道垃圾无人清理")
        self.assertIn("A栋楼道垃圾没人清理", parsed["description"])
        self.assertIn("需要保洁处理", parsed["customer_assessment"])
        self.assertIn("企业微信同步结果", parsed["handling_requirements"])

    def test_records_routes_and_deduplicates_production_ticket(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_CLEANING": "cleaner-1",
                },
                clear=True,
            ):
                first = create_work_order(
                    {
                        "message": PRODUCTION_WECOM_TICKET,
                        "notify": True,
                        "dry_run": True,
                    }
                )
                second = create_work_order({"message": PRODUCTION_WECOM_TICKET})

            metadata = first["record"]["metadata"]
            self.assertEqual(first["analysis"]["assigned_role"], "cleaning")
            self.assertEqual(metadata["assigned_role_label"], "保洁")
            self.assertEqual(metadata["category"], "公共区域清扫")
            self.assertEqual(first["notification"]["channel"], "group_webhook_mention")
            self.assertEqual(first["notification"]["target_env"], "REINS_WECOM_NOTIFY_GROUP_WEBHOOK")
            self.assertEqual(
                first["notification"]["recipient_env"],
                "REINS_WECOM_NOTIFY_USERS_CLEANING",
            )
            self.assertIn("客服研判", first["notification"]["content"])
            self.assertFalse(first["duplicate"])
            self.assertTrue(second["duplicate"])
            self.assertEqual(first["record"]["id"], second["record"]["id"])

            workbook_path = Path(first["records_xlsx_path"])
            self.assertTrue(workbook_path.is_file())
            with ZipFile(workbook_path) as workbook:
                worksheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("工单编号", worksheet)
            self.assertIn("居民诉求", worksheet)
            self.assertIn("处理要求", worksheet)
            self.assertIn("通知状态", worksheet)
            self.assertIn("cleaner-1", worksheet)
            self.assertIn("t_89751e8754e44289", worksheet)
            self.assertIn('state="frozen"', worksheet)
            self.assertIn('<autoFilter ref="A1:O2"/>', worksheet)

    def test_verified_repair_category_beats_ambiguous_bathroom_keyword(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-user-1|property-user-2",
                },
                clear=True,
            ):
                result = create_work_order(
                    {
                        "message": REPAIR_WECOM_TICKET,
                        "notify": True,
                        "dry_run": True,
                    }
                )

        self.assertEqual(result["analysis"]["priority"], "high")
        self.assertEqual(result["analysis"]["assigned_role"], "property")
        self.assertEqual(result["record"]["metadata"]["assigned_role_label"], "物业")
        self.assertEqual(result["notification"]["channel"], "group_webhook_mention")
        self.assertEqual(result["notification"]["target_env"], "REINS_WECOM_NOTIFY_GROUP_WEBHOOK")
        self.assertEqual(
            result["notification"]["recipient_env"],
            "REINS_WECOM_NOTIFY_USERS_PROPERTY",
        )
        self.assertEqual(result["notification"]["recipients"], ["property-user-1", "property-user-2"])

    def test_parses_and_routes_bracketed_emergency_ticket(self):
        parsed = parse_work_order_message(EMERGENCY_WECOM_TICKET)
        self.assertEqual(parsed["external_id"], "t_27f4f7b483174238")
        self.assertEqual(parsed["priority"], "紧急")
        self.assertEqual(parsed["category"], "危急事件")
        self.assertEqual(parsed["upstream_status"], "待处理")
        self.assertEqual(parsed["resident_ref"], "redacted-wechat-customer-reference")
        self.assertEqual(parsed["location"], "6栋3单元502")
        self.assertEqual(parsed["people_involved"], "1")
        self.assertEqual(parsed["current_danger"], "是")
        self.assertIn("需要紧急帮助", parsed["customer_assessment"])

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REINS_HOME": directory}):
                result = create_work_order({"message": EMERGENCY_WECOM_TICKET})

        self.assertEqual(result["analysis"]["priority"], "high")
        self.assertEqual(result["analysis"]["assigned_role"], "hospital")
        self.assertEqual(result["record"]["metadata"]["priority"], "high")
        self.assertEqual(result["record"]["metadata"]["original_priority"], "紧急")
        self.assertEqual(result["record"]["metadata"]["assigned_role_label"], "医院/社区卫生")

    def test_parses_screenshot_ticket_and_routes_charging_hazard_to_property(self):
        parsed = parse_work_order_message(SCREENSHOT_WECOM_TICKET)
        self.assertIn("飞线充电", parsed["description"])
        self.assertIn("电动车推进楼道充电", parsed["customer_assessment"])
        self.assertEqual(parsed["resident_contact"], "136886886886")
        self.assertEqual(parsed["resident_ref"], "wmvlKYcAAAcuk-t3-61mAc2tStCYuNKA")

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-maintenance-1",
                },
                clear=True,
            ):
                result = create_work_order(
                    {
                        "message": SCREENSHOT_WECOM_TICKET,
                        "notify": True,
                        "dry_run": True,
                    }
                )

        self.assertEqual(result["analysis"]["priority"], "high")
        self.assertEqual(result["analysis"]["assigned_role"], "property")
        self.assertEqual(result["record"]["metadata"]["assigned_role_label"], "物业")
        self.assertEqual(result["notification"]["channel"], "group_webhook_mention")
        self.assertEqual(result["notification"]["recipients"], ["property-maintenance-1"])

    def test_parses_mentioned_power_outage_and_normalizes_priority(self):
        parsed = parse_work_order_message(MENTIONED_POWER_OUTAGE_TICKET)
        self.assertEqual(parsed["external_id"], "t_a04299d4b5e34bb4")
        self.assertEqual(parsed["priority"], "优先")
        self.assertEqual(parsed["category"], "公共设施维修")
        self.assertEqual(parsed["location"], "3栋404")
        self.assertEqual(parsed["title"], "停电")

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-maintenance-1",
                },
                clear=True,
            ):
                result = create_work_order(
                    {
                        "message": MENTIONED_POWER_OUTAGE_TICKET,
                        "notify": True,
                        "dry_run": True,
                    }
                )

        self.assertEqual(result["analysis"]["priority"], "high")
        self.assertEqual(result["analysis"]["assigned_role"], "property")
        self.assertEqual(result["record"]["metadata"]["original_priority"], "优先")
        self.assertEqual(result["notification"]["recipients"], ["property-maintenance-1"])

    def test_parses_model_tool_call_with_literal_escaped_newlines(self):
        escaped_message = SCREENSHOT_WECOM_TICKET.replace("\n", "\\n")

        parsed = parse_work_order_message(escaped_message)
        self.assertEqual(parsed["external_id"], "t_3ab6a6d8f17648ad")
        self.assertEqual(parsed["priority"], "紧急")
        self.assertIn("飞线充电", parsed["description"])

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REINS_HOME": directory}, clear=True):
                result = create_work_order({"message": escaped_message})

        self.assertEqual(result["analysis"]["priority"], "high")
        self.assertEqual(result["analysis"]["assigned_role"], "property")
        self.assertEqual(result["record"]["metadata"]["validation_errors"], [])

    def test_exact_duplicate_does_not_notify_staff_twice(self):
        sent_notification = {
            "ok": True,
            "status": "sent",
            "channel": "group_webhook_mention",
            "assigned_role": "hospital",
            "target_env": "REINS_WECOM_NOTIFY_GROUP_WEBHOOK",
            "recipient_env": "REINS_WECOM_NOTIFY_USERS_HOSPITAL",
            "recipients": ["doctor-1"],
            "content": "notification",
            "error": "",
            "message_id": "message-1",
        }

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REINS_HOME": directory}, clear=True):
                with patch(
                    "reins.features.wecom.work_order.notify_staff",
                    return_value=sent_notification,
                ) as notify:
                    first = create_work_order({"message": EMERGENCY_WECOM_TICKET, "notify": True})
                    second = create_work_order({"message": EMERGENCY_WECOM_TICKET, "notify": True})

        self.assertEqual(first["notification"]["status"], "sent")
        self.assertEqual(second["notification"]["status"], "skipped_duplicate")
        self.assertEqual(notify.call_count, 1)

    def test_sends_group_webhook_message_with_real_user_mentions(self):
        requests = []

        class FakeResponse:
            def __init__(self, payload):
                self.payload = json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return self.payload

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))
            return FakeResponse({"errcode": 0, "errmsg": "ok"})

        with patch("reins.features.wecom.notifier.urlopen", side_effect=fake_urlopen):
            result = notifier.send_wecom_text(
                TEST_GROUP_WEBHOOK,
                content="urgent ticket",
                mentioned_user_ids=["doctor-1", "doctor-2"],
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0][0].full_url, TEST_GROUP_WEBHOOK)
        sent_payload = json.loads(requests[0][0].data.decode("utf-8"))
        self.assertEqual(sent_payload["msgtype"], "text")
        self.assertEqual(sent_payload["text"]["content"], "urgent ticket")
        self.assertEqual(sent_payload["text"]["mentioned_list"], ["doctor-1", "doctor-2"])
        self.assertNotIn("touser", sent_payload)

    def test_group_webhook_rejects_invalid_success_response(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return b"{}"

        with patch("reins.features.wecom.notifier.urlopen", return_value=FakeResponse()):
            result = notifier.send_wecom_text(
                TEST_GROUP_WEBHOOK,
                content="ticket",
                mentioned_user_ids=["property-1"],
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("missing", result["error"])

    def test_group_notification_never_falls_back_to_private_app_credentials(self):
        record = {
            "id": 1,
            "message": "3栋404停电",
            "metadata": {
                "external_id": "t_no_private_fallback",
                "assigned_role": "property",
            },
        }
        with patch.dict(
            os.environ,
            {
                "REINS_WECOM_CORP_ID": "legacy-corp",
                "REINS_WECOM_APP_SECRET": "legacy-secret",
                "REINS_WECOM_APP_AGENT_ID": "1000002",
                "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-1",
            },
            clear=True,
        ):
            with patch("reins.features.wecom.notifier.send_wecom_text") as send:
                result = notifier.notify_staff(record)

        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "pending_configuration")
        self.assertEqual(result["channel"], "group_webhook_mention")
        self.assertIn("REINS_WECOM_NOTIFY_GROUP_WEBHOOK", result["error"])
        send.assert_not_called()

    def test_exports_ticket_before_attempting_notification(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-1",
                },
                clear=True,
            ):
                with patch(
                    "reins.features.wecom.work_order.notify_staff",
                    side_effect=RuntimeError("simulated notifier crash"),
                ):
                    with self.assertRaisesRegex(RuntimeError, "simulated notifier crash"):
                        create_work_order(
                            {
                                "message": MENTIONED_POWER_OUTAGE_TICKET,
                                "notify": True,
                            }
                        )

            workbook_path = Path(directory) / "wecom" / "records.xlsx"
            self.assertTrue(workbook_path.is_file())
            with ZipFile(workbook_path) as workbook:
                worksheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("t_a04299d4b5e34bb4", worksheet)

    def test_doctor_reports_roles_that_share_the_same_recipient_mapping(self):
        with patch.dict(
            os.environ,
            {
                "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                "REINS_WECOM_NOTIFY_USERS_PROPERTY": "shared-user",
                "REINS_WECOM_NOTIFY_USERS_CLEANING": "shared-user",
            },
            clear=True,
        ):
            result = notifier.notification_doctor()

        warnings = result["recipient_mapping_warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0]["roles"], ["property", "cleaning"])
        self.assertEqual(
            result["roles"]["property"]["shared_with_roles"],
            ["cleaning"],
        )

    def test_long_group_notification_preserves_reply_instruction(self):
        record = {
            "id": 1,
            "metadata": {
                "external_id": "t_long_ticket",
                "assigned_role": "property",
                "description": "停电和漏水" * 2000,
            },
        }

        content = notifier.build_staff_notification(record)

        self.assertLessEqual(len(content.encode("utf-8")), notifier.WECOM_TEXT_MAX_BYTES)
        self.assertIn("工单内容过长，已截断", content)
        self.assertIn("@社区美女", content)
        self.assertIn("t_long_ticket 已处理", content)

    def test_hermes_plugin_registers_and_processes_group_ticket(self):
        class FakeContext:
            def __init__(self):
                self.tools = {}
                self.hooks = {}

            def register_tool(self, **kwargs):
                self.tools[kwargs["name"]] = kwargs

            def register_hook(self, name, callback):
                self.hooks[name] = callback

        context = FakeContext()
        register_hermes_tools(context)
        self.assertEqual(
            set(context.tools),
            {
                "wecom_ingest_group_ticket",
                "wecom_record_staff_reply",
                "wecom_work_order_report",
                "wecom_work_order_doctor",
            },
        )
        self.assertEqual(set(context.hooks), {"pre_llm_call"})

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_HOSPITAL": "doctor-1",
                },
                clear=True,
            ):
                output = context.tools["wecom_ingest_group_ticket"]["handler"](
                    {"message": EMERGENCY_WECOM_TICKET, "dry_run": True}
                )

        result = json.loads(output)
        self.assertTrue(result["ok"])
        self.assertEqual(result["external_id"], "t_27f4f7b483174238")
        self.assertEqual(result["assigned_role"], "hospital")
        self.assertEqual(result["notification"]["channel"], "group_webhook_mention")
        self.assertEqual(result["notification"]["recipients"], ["doctor-1"])

    def test_pre_llm_hook_processes_ticket_without_model_tool_call(self):
        class FakeContext:
            def __init__(self):
                self.tools = {}
                self.hooks = {}

            def register_tool(self, **kwargs):
                self.tools[kwargs["name"]] = kwargs

            def register_hook(self, name, callback):
                self.hooks[name] = callback

        context = FakeContext()
        register_hermes_tools(context)

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-maintenance-1",
                },
                clear=True,
            ):
                injected = context.hooks["pre_llm_call"](
                    user_message=SCREENSHOT_WECOM_TICKET,
                    platform="wecom",
                    sender_id="ticket-sender-1",
                )

        self.assertIsNotNone(injected)
        context_text = injected["context"]
        self.assertIn("REINS_WECOM_PREPROCESSED_WORK_ORDER", context_text)
        self.assertIn('"external_id": "t_3ab6a6d8f17648ad"', context_text)
        self.assertIn('"assigned_role": "property"', context_text)
        self.assertIn('"target_env": "REINS_WECOM_NOTIFY_GROUP_WEBHOOK"', context_text)
        self.assertIn('"recipient_env": "REINS_WECOM_NOTIFY_USERS_PROPERTY"', context_text)

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-maintenance-1",
                },
                clear=True,
            ):
                mentioned = context.hooks["pre_llm_call"](
                    user_message=MENTIONED_POWER_OUTAGE_TICKET,
                    platform="wecom",
                )

        self.assertIsNotNone(mentioned)
        self.assertIn('"external_id": "t_a04299d4b5e34bb4"', mentioned["context"])
        self.assertIn('"priority": "high"', mentioned["context"])

        self.assertIsNone(
            context.hooks["pre_llm_call"](
                user_message="普通群聊消息",
                platform="wecom",
            )
        )

    def test_plugin_installer_copies_to_reins_and_hermes_homes(self):
        with tempfile.TemporaryDirectory() as directory:
            reins_home = Path(directory) / "reins"
            hermes_home = Path(directory) / "hermes"
            with patch.dict(
                os.environ,
                {"REINS_HOME": str(reins_home), "HERMES_HOME": str(hermes_home)},
                clear=True,
            ):
                plugin_dirs = install_hermes_plugin()
            self.assertEqual(len(plugin_dirs), 2)
            for plugin_dir in plugin_dirs:
                self.assertEqual(plugin_dir.name, "reins-wecom")
                self.assertTrue((plugin_dir / "plugin.yaml").is_file())
                self.assertTrue((plugin_dir / "reins_wecom_plugin.py").is_file())


if __name__ == "__main__":
    unittest.main()
