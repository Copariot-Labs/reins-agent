from __future__ import annotations

import json
import os
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from reins.features.wecom.cli import _load_wecom_env, main as wecom_main
from reins.features.wecom.ticket_api import (
    TicketAPIConfig,
    fetch_tickets,
    inspect_tickets,
    load_cursor,
    parse_statuses,
    poll_once,
    ticket_to_work_order_payload,
)
from reins.features.wecom.ticket_service import (
    SERVICE_LABEL,
    SYSTEMD_UNIT_NAME,
    WINDOWS_TASK_NAME,
    build_linux_poller_script,
    build_service_definition,
    build_systemd_unit,
    build_windows_task_script,
    install_service,
    service_status,
    stop_service,
    uninstall_service,
)
from reins.features.wecom.work_order import create_work_order, parse_work_order_message


TEST_GROUP_WEBHOOK = (
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-group-robot-key"
)


POWER_OUTAGE_MARKDOWN = """@社区美女
【新建工单】
**工单编号：t_api_power_001**
处理状态：待处理
优先级：优先
问题类别：公共设施维修
消息来源：微信居民消息
生成时间：2026-07-22 10:53:18（北京时间）
【居民诉求】
居民原话：3栋404没电了
【已确认信息】
- 地点：3栋404
- 问题/现象：停电
【网格员研判】
居民反映3栋404没电了
【处理要求】
请尽快联系或到场处理；完成后在本群同步结果。
【系统信息】
居民标识：resident-redacted-001
【工单结束】"""


def api_ticket(*, status: str = "pending_dispatch") -> dict:
    return {
        "id": "t_api_power_001",
        "case_id": "c_api_case_001",
        "content_markdown": POWER_OUTAGE_MARKDOWN,
        "status": status,
        "priority": "优先",
        "created_at": "2026-07-22T02:53:18Z",
        "updated_at": "2026-07-22T03:04:06Z",
    }


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


class WeComTicketAPITests(unittest.TestCase):
    def test_windows_utf8_bom_env_loads_chinese_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "REINS_TICKET_API_TOKEN=china-token\n"
                "REINS_WECOM_REPLY_BOT_NAME=社区助手\n",
                encoding="utf-8-sig",
            )
            with patch.dict(os.environ, {"REINS_HOME": directory}, clear=True):
                _load_wecom_env()
                self.assertEqual(os.environ["REINS_TICKET_API_TOKEN"], "china-token")
                self.assertEqual(os.environ["REINS_WECOM_REPLY_BOT_NAME"], "社区助手")

    def test_parses_real_api_markdown_ticket_number(self):
        parsed = parse_work_order_message(POWER_OUTAGE_MARKDOWN)

        self.assertEqual(parsed["external_id"], "t_api_power_001")
        self.assertEqual(parsed["location"], "3栋404")

    def test_uses_api_category_when_markdown_has_no_category(self):
        ticket = api_ticket()
        ticket["category"] = "community_sanitation"
        ticket["content_markdown"] = """【新建工单】
工单编号：t_api_category_001
处理状态：待处理
生成时间：2026-07-22 10:53:18（北京时间）
【居民诉求】
居民原话：公共区域需要安排人员处理
【已确认信息】
- 地点：3栋大厅
- 问题/现象：现场需要处理
【工单结束】"""
        payload = ticket_to_work_order_payload(ticket, dry_run=True)

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
                result = create_work_order(payload)

        self.assertEqual(result["record"]["metadata"]["api_category"], "community_sanitation")
        self.assertEqual(result["record"]["metadata"]["assigned_role"], "cleaning")
        self.assertEqual(
            result["notification"]["recipient_env"],
            "REINS_WECOM_NOTIFY_USERS_CLEANING",
        )

    def test_default_statuses_include_real_api_dispatched_state(self):
        with patch.dict(os.environ, {}, clear=True):
            config = TicketAPIConfig.from_env(token="secret-token")

        self.assertEqual(
            config.statuses,
            ("pending_dispatch", "dispatched", "reopened", "notification_failed"),
        )

    def test_cursor_now_command_seeds_first_watch_without_replaying_history(self):
        with tempfile.TemporaryDirectory() as directory:
            cursor_path = Path(directory) / "wecom" / "ticket-api-cursor.json"
            with patch.dict(os.environ, {"REINS_HOME": directory}, clear=True):
                exit_code = wecom_main(["ticket-api", "cursor", "--now", "--json"])

            self.assertEqual(exit_code, 0)
            self.assertTrue(load_cursor(cursor_path)["since"])

    def test_service_install_seeds_cursor_unless_replay_is_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            cursor_path = Path(directory) / "wecom" / "ticket-api-cursor.json"
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_TICKET_API_TOKEN": "secret-token",
                },
                clear=True,
            ):
                with patch(
                    "reins.features.wecom.cli.install_service",
                    return_value={"ok": True, "installed": True, "running": True},
                ):
                    exit_code = wecom_main(["ticket-api", "service", "install"])

            self.assertEqual(exit_code, 0)
            self.assertTrue(load_cursor(cursor_path)["since"])

    def test_fetches_each_configured_status_with_bearer_auth(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return FakeResponse({"data": {"tickets": [api_ticket()]}})

        config = TicketAPIConfig(
            url="https://kf.example.test/internal/tickets?source=reins",
            token="secret-token",
            statuses=("pending_dispatch", "reopened"),
            limit=20,
            poll_interval=30,
            timeout=7,
            cursor_path=Path("/tmp/not-used.json"),
        )
        tickets = fetch_tickets(config, since="2026-07-22T00:00:00", opener=opener)

        self.assertEqual(len(tickets), 1)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0][0].get_header("Authorization"), "Bearer secret-token")
        self.assertEqual(requests[0][1], 7)
        first_query = parse_qs(urlsplit(requests[0][0].full_url).query)
        second_query = parse_qs(urlsplit(requests[1][0].full_url).query)
        self.assertEqual(first_query["source"], ["reins"])
        self.assertEqual(first_query["status"], ["pending_dispatch"])
        self.assertEqual(second_query["status"], ["reopened"])
        self.assertEqual(first_query["since"], ["2026-07-22 00:00:00"])
        self.assertEqual(first_query["limit"], ["20"])

    def test_normalizes_iso_since_to_upstream_timestamp_format(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse({"tickets": []})

        config = TicketAPIConfig(
            url="https://kf.example.test/internal/tickets",
            token="secret-token",
            statuses=("dispatched",),
            limit=5,
            poll_interval=30,
            timeout=7,
            cursor_path=Path("/tmp/not-used.json"),
        )
        fetch_tickets(config, since="2026-07-22T07:27:41Z", opener=opener)

        query = parse_qs(urlsplit(requests[0].full_url).query)
        self.assertEqual(query["since"], ["2026-07-22 07:27:41"])

    def test_inspect_returns_sanitized_upstream_metadata_without_content(self):
        def opener(request, timeout):
            return FakeResponse({"tickets": [api_ticket(status="dispatched")]})

        config = TicketAPIConfig(
            url="https://kf.example.test/internal/tickets",
            token="secret-token",
            statuses=(),
            limit=5,
            poll_interval=30,
            timeout=7,
            cursor_path=Path("/tmp/not-used.json"),
        )
        result = inspect_tickets(config, opener=opener)

        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["tickets"][0]["id"], "t_api_power_001")
        self.assertEqual(result["tickets"][0]["status"], "dispatched")
        self.assertNotIn("content_markdown", result["tickets"][0])

    def test_rejects_unsupported_status(self):
        with self.assertRaisesRegex(ValueError, "unsupported ticket status"):
            parse_statuses("pending_dispatch,closed")

    def test_poll_classifies_notifies_deduplicates_and_saves_cursor(self):
        requests = []

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse({"tickets": [api_ticket()]})

        sent_notification = {
            "ok": True,
            "status": "sent",
            "channel": "group_webhook_mention",
            "assigned_role": "property",
            "target_env": "REINS_WECOM_NOTIFY_GROUP_WEBHOOK",
            "recipient_env": "REINS_WECOM_NOTIFY_USERS_PROPERTY",
            "recipients": ["property-user-1"],
            "content": "notification",
            "error": "",
            "message_id": "message-1",
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = TicketAPIConfig(
                url="https://kf.example.test/internal/tickets",
                token="secret-token",
                statuses=("pending_dispatch",),
                limit=20,
                poll_interval=30,
                timeout=7,
                cursor_path=root / "cursor.json",
            )
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": str(root / "reins"),
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-user-1",
                },
                clear=True,
            ):
                dry_run = poll_once(config, dry_run=True, opener=opener)
                self.assertTrue(dry_run["ok"])
                self.assertFalse(dry_run["cursor_advanced"])
                self.assertEqual(dry_run["tickets"][0]["assigned_role"], "property")
                self.assertEqual(
                    dry_run["tickets"][0]["notification_recipient_env"],
                    "REINS_WECOM_NOTIFY_USERS_PROPERTY",
                )
                self.assertEqual(dry_run["tickets"][0]["notification_recipient_count"], 1)
                self.assertEqual(dry_run["tickets"][0]["external_id"], "t_api_power_001")
                self.assertEqual(dry_run["tickets"][0]["notification_status"], "dry_run")
                self.assertFalse(config.cursor_path.exists())

                with patch(
                    "reins.features.wecom.work_order.notify_staff",
                    return_value=sent_notification,
                ) as notify:
                    first = poll_once(config, opener=opener)
                    second = poll_once(config, opener=opener)

            self.assertTrue(first["ok"])
            self.assertEqual(first["statuses"], ["pending_dispatch"])
            self.assertTrue(first["cursor_advanced"])
            self.assertEqual(first["notifications_sent"], 1)
            self.assertEqual(load_cursor(config.cursor_path)["since"], "2026-07-22T03:04:06Z")
            self.assertTrue(second["ok"])
            self.assertEqual(second["notifications_skipped"], 1)
            self.assertEqual(notify.call_count, 1)
            latest_query = parse_qs(urlsplit(requests[-1].full_url).query)
            self.assertEqual(latest_query["since"], ["2026-07-22 03:04:06"])

    def test_notification_failure_does_not_advance_cursor(self):
        def opener(request, timeout):
            return FakeResponse([api_ticket()])

        def failed_processor(payload):
            return {
                "ok": True,
                "duplicate": False,
                "record": {
                    "metadata": {
                        "external_id": "t_api_power_001",
                        "assigned_role": "property",
                    }
                },
                "notification": {
                    "ok": False,
                    "status": "pending_configuration",
                    "error": "missing REINS_WECOM_NOTIFY_USERS_PROPERTY",
                },
            }

        with tempfile.TemporaryDirectory() as directory:
            config = TicketAPIConfig(
                url="https://kf.example.test/internal/tickets",
                token="secret-token",
                statuses=("pending_dispatch",),
                limit=20,
                poll_interval=30,
                timeout=7,
                cursor_path=Path(directory) / "cursor.json",
            )
            result = poll_once(config, opener=opener, processor=failed_processor)

            self.assertFalse(result["ok"])
            self.assertEqual(result["notification_failures"], 1)
            self.assertFalse(result["cursor_advanced"])
            self.assertFalse(config.cursor_path.exists())

    def test_same_reopened_api_event_is_only_notified_once(self):
        def opener(request, timeout):
            return FakeResponse({"tickets": [api_ticket(status="reopened")]})

        sent_notification = {
            "ok": True,
            "status": "sent",
            "channel": "group_webhook_mention",
            "assigned_role": "property",
            "target_env": "REINS_WECOM_NOTIFY_GROUP_WEBHOOK",
            "recipient_env": "REINS_WECOM_NOTIFY_USERS_PROPERTY",
            "recipients": ["property-user-1"],
            "content": "notification",
            "error": "",
            "message_id": "message-reopened-1",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = TicketAPIConfig(
                url="https://kf.example.test/internal/tickets",
                token="secret-token",
                statuses=("reopened",),
                limit=20,
                poll_interval=30,
                timeout=7,
                cursor_path=root / "cursor.json",
            )
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": str(root / "reins"),
                    "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": TEST_GROUP_WEBHOOK,
                    "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-user-1",
                },
                clear=True,
            ):
                with patch(
                    "reins.features.wecom.work_order.notify_staff",
                    return_value=sent_notification,
                ) as notify:
                    first = poll_once(config, opener=opener)
                    second = poll_once(config, opener=opener)

        self.assertEqual(first["notifications_sent"], 1)
        self.assertEqual(second["notifications_skipped"], 1)
        self.assertEqual(notify.call_count, 1)

    def test_launchd_definition_runs_standalone_ticket_poller_without_secrets(self):
        definition = build_service_definition(interval=12)
        arguments = definition["ProgramArguments"]

        self.assertEqual(definition["Label"], SERVICE_LABEL)
        self.assertIn("ticket-api", arguments)
        self.assertIn("--watch", arguments)
        self.assertIn("--json-lines", arguments)
        self.assertIn("12.0", arguments)
        serialized = json.dumps(definition)
        self.assertNotIn("REINS_TICKET_API_TOKEN", serialized)
        self.assertNotIn("REINS_WECOM_APP_SECRET", serialized)
        self.assertNotIn("REINS_WECOM_NOTIFY_GROUP_WEBHOOK", serialized)

    def test_stopping_an_unloaded_launchd_service_is_successful(self):
        result = CompletedProcess(
            ["launchctl"],
            returncode=3,
            stdout="",
            stderr="Boot-out failed: 3: No such process",
        )
        with patch("reins.features.wecom.ticket_service.sys.platform", "darwin"):
            with patch("reins.features.wecom.ticket_service._launchctl", return_value=result):
                stopped = stop_service()

        self.assertTrue(stopped["ok"])
        self.assertFalse(stopped["running"])
        self.assertEqual(stopped["error"], "")

    def test_windows_task_script_runs_utf8_poller_without_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            reins_home = Path(directory) / "社区数据"
            with patch.dict(os.environ, {"REINS_HOME": str(reins_home)}, clear=True):
                script = build_windows_task_script(interval=12)

        self.assertIn("$env:PYTHONUTF8 = '1'", script)
        self.assertIn("'ticket-api'", script)
        self.assertIn("'--watch'", script)
        self.assertIn("'--json-lines'", script)
        self.assertIn("'12.0'", script)
        self.assertIn("社区数据", script)
        self.assertNotIn("REINS_TICKET_API_TOKEN", script)
        self.assertNotIn("REINS_WECOM_NOTIFY_GROUP_WEBHOOK", script)

    def test_windows_service_installs_and_starts_scheduled_task(self):
        created = CompletedProcess(["schtasks.exe"], returncode=0, stdout="SUCCESS", stderr="")
        configured = CompletedProcess(["powershell.exe"], returncode=0, stdout="", stderr="")
        started = CompletedProcess(["schtasks.exe"], returncode=0, stdout="SUCCESS", stderr="")

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REINS_HOME": directory}, clear=True):
                with patch("reins.features.wecom.ticket_service.sys.platform", "win32"):
                    with patch(
                        "reins.features.wecom.ticket_service._schtasks",
                        side_effect=[created, started],
                    ) as schtasks:
                        with patch(
                            "reins.features.wecom.ticket_service._powershell",
                            return_value=configured,
                        ) as powershell:
                            result = install_service(interval=12)

        self.assertTrue(result["ok"])
        self.assertTrue(result["installed"])
        self.assertTrue(result["running"])
        create_args = schtasks.call_args_list[0].args[0]
        self.assertEqual(create_args[:4], ["/Create", "/TN", WINDOWS_TASK_NAME, "/SC"])
        self.assertIn("ONLOGON", create_args)
        self.assertIn("powershell.exe", create_args[create_args.index("/TR") + 1])
        settings_command = powershell.call_args.args[0][-1]
        self.assertIn("ExecutionTimeLimit", settings_command)
        self.assertIn("RestartCount 999", settings_command)
        self.assertIn("MultipleInstances IgnoreNew", settings_command)
        self.assertEqual(
            schtasks.call_args_list[1].args[0],
            ["/Run", "/TN", WINDOWS_TASK_NAME],
        )

    def test_windows_service_status_uses_language_independent_state_code(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {"REINS_HOME": directory}, clear=True):
                with patch("reins.features.wecom.ticket_service.sys.platform", "win32"):
                    with patch(
                        "reins.features.wecom.ticket_service._windows_task_exists",
                        return_value=True,
                    ):
                        with patch(
                            "reins.features.wecom.ticket_service._windows_task_state",
                            return_value=(4, ""),
                        ):
                            result = service_status()

        self.assertTrue(result["ok"])
        self.assertTrue(result["installed"])
        self.assertTrue(result["running"])
        self.assertEqual(result["state"], "running")

    def test_ubuntu_runner_and_systemd_unit_are_utf8_and_secret_free(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reins_home = root / "社区数据"
            script_path = reins_home / "wecom" / "ticket-poller.sh"
            with patch.dict(os.environ, {"REINS_HOME": str(reins_home)}, clear=True):
                with patch(
                    "reins.features.wecom.ticket_service.linux_poller_script_path",
                    return_value=script_path,
                ):
                    script = build_linux_poller_script(interval=12)
                    unit = build_systemd_unit(interval=12)

        self.assertIn("export PYTHONUTF8=1", script)
        self.assertIn("ticket-api poll --watch --json-lines", script)
        self.assertIn("社区数据", script)
        self.assertNotIn("REINS_TICKET_API_TOKEN", script)
        self.assertNotIn("REINS_WECOM_NOTIFY_GROUP_WEBHOOK", script)
        self.assertIn(f"Description=Reins WeCom Ticket Poller", unit)
        self.assertIn("Restart=always", unit)
        self.assertIn("WantedBy=default.target", unit)
        self.assertIn(str(script_path), unit)

    def test_ubuntu_service_installs_and_starts_systemd_user_unit(self):
        reloaded = CompletedProcess(["systemctl"], returncode=0, stdout="", stderr="")
        enabled = CompletedProcess(["systemctl"], returncode=0, stdout="", stderr="")
        started = CompletedProcess(["systemctl"], returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reins_home = root / "reins"
            script_path = reins_home / "wecom" / "ticket-poller.sh"
            unit_path = root / ".config" / "systemd" / "user" / SYSTEMD_UNIT_NAME
            with patch.dict(os.environ, {"REINS_HOME": str(reins_home)}, clear=True):
                with patch(
                    "reins.features.wecom.ticket_service.linux_poller_script_path",
                    return_value=script_path,
                ):
                    with patch(
                        "reins.features.wecom.ticket_service.systemd_unit_path",
                        return_value=unit_path,
                    ):
                        with patch("reins.features.wecom.ticket_service.sys.platform", "linux"):
                            with patch(
                                "reins.features.wecom.ticket_service._systemctl",
                                side_effect=[reloaded, enabled, started],
                            ) as systemctl:
                                result = install_service(interval=12)
                                script_exists = script_path.is_file()
                                unit_exists = unit_path.is_file()

        self.assertTrue(result["ok"])
        self.assertTrue(result["installed"])
        self.assertTrue(result["running"])
        self.assertTrue(script_exists)
        self.assertTrue(unit_exists)
        self.assertEqual(systemctl.call_args_list[0].args[0], ["daemon-reload"])
        self.assertEqual(
            systemctl.call_args_list[1].args[0],
            ["enable", SYSTEMD_UNIT_NAME],
        )
        self.assertEqual(
            systemctl.call_args_list[2].args[0],
            ["restart", SYSTEMD_UNIT_NAME],
        )

    def test_ubuntu_service_status_parses_systemd_properties(self):
        status = CompletedProcess(
            ["systemctl"],
            returncode=0,
            stdout=(
                "LoadState=loaded\n"
                "ActiveState=active\n"
                "SubState=running\n"
                "MainPID=4321\n"
            ),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit_path = root / SYSTEMD_UNIT_NAME
            unit_path.write_text("[Unit]\n", encoding="utf-8")
            with patch.dict(os.environ, {"REINS_HOME": str(root / 'reins')}, clear=True):
                with patch(
                    "reins.features.wecom.ticket_service.systemd_unit_path",
                    return_value=unit_path,
                ):
                    with patch("reins.features.wecom.ticket_service.sys.platform", "linux"):
                        with patch(
                            "reins.features.wecom.ticket_service._systemctl",
                            return_value=status,
                        ):
                            result = service_status()

        self.assertTrue(result["ok"])
        self.assertTrue(result["installed"])
        self.assertTrue(result["loaded"])
        self.assertTrue(result["running"])
        self.assertEqual(result["state"], "running")
        self.assertEqual(result["pid"], 4321)

    def test_ubuntu_service_uninstall_disables_and_removes_files(self):
        disabled = CompletedProcess(["systemctl"], returncode=0, stdout="", stderr="")
        reloaded = CompletedProcess(["systemctl"], returncode=0, stdout="", stderr="")
        reset = CompletedProcess(["systemctl"], returncode=0, stdout="", stderr="")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script_path = root / "reins" / "wecom" / "ticket-poller.sh"
            unit_path = root / ".config" / "systemd" / "user" / SYSTEMD_UNIT_NAME
            script_path.parent.mkdir(parents=True)
            unit_path.parent.mkdir(parents=True)
            script_path.write_text("#!/bin/sh\n", encoding="utf-8")
            unit_path.write_text("[Unit]\n", encoding="utf-8")
            with patch.dict(os.environ, {"REINS_HOME": str(root / "reins")}, clear=True):
                with patch(
                    "reins.features.wecom.ticket_service.linux_poller_script_path",
                    return_value=script_path,
                ):
                    with patch(
                        "reins.features.wecom.ticket_service.systemd_unit_path",
                        return_value=unit_path,
                    ):
                        with patch("reins.features.wecom.ticket_service.sys.platform", "linux"):
                            with patch(
                                "reins.features.wecom.ticket_service._systemctl",
                                side_effect=[disabled, reloaded, reset],
                            ) as systemctl:
                                result = uninstall_service()
                                script_exists = script_path.exists()
                                unit_exists = unit_path.exists()

        self.assertTrue(result["ok"])
        self.assertFalse(result["installed"])
        self.assertFalse(script_exists)
        self.assertFalse(unit_exists)
        self.assertEqual(
            systemctl.call_args_list[0].args[0],
            ["disable", "--now", SYSTEMD_UNIT_NAME],
        )
        self.assertEqual(systemctl.call_args_list[1].args[0], ["daemon-reload"])


if __name__ == "__main__":
    unittest.main()
