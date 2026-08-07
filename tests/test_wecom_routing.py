from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reins.features.wecom.notifier import notify_staff
from reins.features.wecom.routing import RoutingConfig, resolve_hybrid_routing
from reins.features.wecom.work_order import create_work_order


class WeComHybridRoutingTests(unittest.TestCase):
    def test_recognized_category_remains_authoritative(self):
        calls = []

        def model_router(messages, timeout):
            calls.append((messages, timeout))
            raise AssertionError("Hermes should not run for an authoritative category")

        result = resolve_hybrid_routing(
            {"category": "公共设施维修", "description": "卫生间水管损坏，需要清洁现场"},
            {
                "assigned_role": "property",
                "assignment_reason": "provided_category:property",
                "priority": "normal",
            },
            candidate_roles=["property", "cleaning"],
            config=RoutingConfig(mode="hybrid"),
            model_router=model_router,
        )

        self.assertEqual(result["assigned_role"], "property")
        self.assertEqual(result["routing_source"], "rules")
        self.assertEqual(calls, [])

    def test_ambiguous_ticket_uses_validated_hermes_roles_and_redacts_identifiers(self):
        captured = {}

        def model_router(messages, timeout):
            captured["messages"] = messages
            captured["timeout"] = timeout
            return (
                json.dumps(
                    {
                        "primary_role": "property",
                        "supporting_roles": ["community"],
                        "confidence": 0.94,
                        "reason": "A utility issue needs property support and resident coordination.",
                        "requires_human_review": False,
                    }
                ),
                "test-router",
            )

        result = resolve_hybrid_routing(
            {
                "title": "居民需要帮助",
                "description": "请联系 13688688688，居民标识 wmvlKYcAAAVUcll6OBn5cwI6JnqPcN2g，家中设施异常。",
                "category": "其他",
                "priority": "normal",
            },
            {
                "assigned_role": "human_review",
                "assignment_reason": "provided_category:generic",
                "priority": "normal",
            },
            config=RoutingConfig(mode="hybrid", confidence_threshold=0.85, timeout=9),
            model_router=model_router,
        )

        prompt = json.dumps(captured["messages"], ensure_ascii=False)
        self.assertNotIn("13688688688", prompt)
        self.assertNotIn("wmvlKYcAAAVUcll6OBn5cwI6JnqPcN2g", prompt)
        self.assertEqual(captured["timeout"], 9)
        self.assertEqual(result["assigned_role"], "property")
        self.assertEqual(result["assigned_roles"], ["property", "community"])
        self.assertTrue(result["routing_ai_applied"])
        self.assertEqual(result["routing_model"], "test-router")

    def test_low_confidence_and_invalid_roles_fail_closed(self):
        low_confidence = resolve_hybrid_routing(
            {"description": "无法判断由谁处理"},
            {
                "assigned_role": "human_review",
                "assignment_reason": "uncertain",
                "priority": "normal",
            },
            config=RoutingConfig(mode="hybrid", confidence_threshold=0.85),
            model_router=lambda _messages, _timeout: (
                json.dumps(
                    {
                        "primary_role": "community",
                        "supporting_roles": [],
                        "confidence": 0.5,
                        "reason": "Possibly a community matter.",
                        "requires_human_review": False,
                    }
                ),
                "test-router",
            ),
        )
        invalid_role = resolve_hybrid_routing(
            {"description": "无法判断由谁处理"},
            {
                "assigned_role": "human_review",
                "assignment_reason": "uncertain",
                "priority": "normal",
            },
            config=RoutingConfig(mode="hybrid"),
            model_router=lambda _messages, _timeout: (
                json.dumps(
                    {
                        "primary_role": "random_user_123",
                        "supporting_roles": [],
                        "confidence": 0.99,
                        "reason": "Invalid destination.",
                        "requires_human_review": False,
                    }
                ),
                "test-router",
            ),
        )

        self.assertEqual(low_confidence["assigned_role"], "human_review")
        self.assertEqual(low_confidence["routing_source"], "hermes_human_review")
        self.assertFalse(low_confidence["routing_ai_applied"])
        self.assertEqual(invalid_role["assigned_role"], "human_review")
        self.assertEqual(invalid_role["routing_source"], "hermes_fallback")
        self.assertIn("outside the permitted routing set", invalid_role["routing_error"])

    def test_high_priority_safety_candidate_cannot_be_dropped(self):
        result = resolve_hybrid_routing(
            {"description": "居民晕倒，现场也需要社区协助"},
            {
                "assigned_role": "hospital",
                "assignment_reason": "keyword:hospital",
                "priority": "high",
            },
            candidate_roles=["hospital", "community"],
            config=RoutingConfig(mode="hybrid"),
            model_router=lambda _messages, _timeout: (
                json.dumps(
                    {
                        "primary_role": "community",
                        "supporting_roles": [],
                        "confidence": 0.98,
                        "reason": "Community can coordinate.",
                        "requires_human_review": False,
                    }
                ),
                "test-router",
            ),
        )

        self.assertEqual(result["assigned_role"], "human_review")
        self.assertEqual(result["routing_error"], "safety_role_missing")

    def test_notifier_merges_allowlisted_recipients_for_multiple_roles(self):
        record = {
            "id": 1,
            "message": "楼道设施损坏，需要社区协调。",
            "metadata": {
                "external_id": "ticket-multi-role",
                "assigned_role": "property",
                "assigned_roles": ["property", "community"],
                "priority": "normal",
                "category": "社区设施",
                "description": "楼道设施损坏，需要社区协调。",
            },
        }
        env = {
            "REINS_WECOM_NOTIFY_GROUP_WEBHOOK": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key",
            "REINS_WECOM_NOTIFY_USERS_PROPERTY": "property-user|shared-user",
            "REINS_WECOM_NOTIFY_USERS_COMMUNITY": "community-user|shared-user",
        }
        with patch.dict(os.environ, env, clear=True):
            result = notify_staff(record, dry_run=True)

        self.assertTrue(result["ok"])
        self.assertEqual(result["assigned_roles"], ["property", "community"])
        self.assertEqual(
            result["recipients"],
            ["property-user", "shared-user", "community-user"],
        )
        self.assertIn("负责人：物业、社区工作人员", result["content"])

    def test_duplicate_ticket_reuses_persisted_hermes_decision(self):
        model_response = json.dumps(
            {
                "primary_role": "property",
                "supporting_roles": [],
                "confidence": 0.93,
                "reason": "Property should inspect the facility.",
                "requires_human_review": False,
            }
        )
        payload = {
            "external_id": "ticket-routing-reuse",
            "ticket_created_at": "2026-08-07 10:00:00",
            "title": "居民需要协助",
            "description": "家中设施出现不明确的问题。",
            "category": "其他",
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(
                os.environ,
                {
                    "REINS_HOME": directory,
                    "REINS_WECOM_ROUTING_MODE": "hybrid",
                },
                clear=True,
            ):
                with patch(
                    "reins.features.wecom.routing._call_hermes_router",
                    return_value=(model_response, "test-router"),
                ) as model_router:
                    first = create_work_order(payload)
                    second = create_work_order(payload)

                workbook_exists = (Path(directory) / "wecom" / "records.xlsx").is_file()

        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(model_router.call_count, 1)
        self.assertEqual(second["record"]["metadata"]["routing_model"], "test-router")
        self.assertTrue(workbook_exists)


if __name__ == "__main__":
    unittest.main()
