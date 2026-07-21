from __future__ import annotations

import json
import re
from typing import Any

from datetime import datetime, timezone

from reins.features.wecom.notifier import notify_staff
from reins.features.wecom.store import add_record, export_records_xlsx, find_record_by_metadata, get_record, update_record


FIELD_ALIASES = {
    "external_id": ("external_id", "externalId", "ticket_id", "ticketId", "work_order_id", "workOrderId", "工单编号", "工单号", "工单ID", "编号"),
    "ticket_created_at": ("ticket_created_at", "ticketCreatedAt", "created_at", "createdAt", "ticket_time", "ticketTime", "创建时间", "工单创建时间", "生成时间"),
    "title": ("title", "subject", "summary", "标题", "主题", "工单标题", "问题标题", "问题/现象"),
    "description": ("description", "content", "problem", "request", "问题描述", "描述", "内容", "居民诉求", "诉求", "问题", "客户原话", "居民原话"),
    "resident_ref": ("resident_ref", "residentRef", "customer_ref", "customerRef", "user_ref", "userRef", "居民引用", "居民标识", "客户引用", "微信客户", "客户标识"),
    "resident_name": ("resident_name", "residentName", "customer_name", "customerName", "name", "居民姓名", "客户姓名", "姓名", "联系人"),
    "resident_contact": ("resident_contact", "residentContact", "phone", "mobile", "tel", "contact", "联系方式", "联系电话", "手机号", "电话"),
    "location": ("location", "address", "community", "building", "room", "位置", "地点", "地址", "小区", "楼栋", "房号"),
    "category": ("category", "type", "question_type", "questionType", "issue_type", "issueType", "分类", "类别", "类型", "问题类型", "问题类别", "工单类型", "工单类别"),
    "original_category": ("original_category", "originalCategory", "source_category", "sourceCategory", "原始类别", "来源类别"),
    "priority": ("priority", "urgency", "level", "优先级", "紧急程度", "等级"),
    "original_priority": ("original_priority", "originalPriority", "原始优先级"),
    "assigned_role": ("assigned_role", "assignedRole", "responsible_role", "responsibleRole", "负责角色", "责任角色", "处理部门"),
    "source_channel": ("source_channel", "sourceChannel", "source", "channel", "来源渠道", "消息来源", "来源", "渠道"),
    "assignee": ("assignee", "owner", "handler", "处理人", "负责人", "跟进人"),
    "due_at": ("due_at", "dueAt", "deadline", "expected_time", "expectedTime", "截止时间", "期望处理时间", "要求完成时间"),
    "upstream_status": ("upstream_status", "upstreamStatus", "工单状态", "处理状态", "状态"),
    "customer_assessment": ("customer_assessment", "customerAssessment", "客服研判", "客服判断", "网格员研判", "网格研判", "研判"),
    "handling_requirements": ("handling_requirements", "handlingRequirements", "处理要求", "办理要求"),
    "people_involved": ("people_involved", "peopleInvolved", "涉及人数", "涉及人员"),
    "current_danger": ("current_danger", "currentDanger", "当前危险", "是否危险"),
}

CLI_FIELD_NAMES = {
    "external_id",
    "ticket_created_at",
    "title",
    "description",
    "resident_ref",
    "resident_name",
    "resident_contact",
    "location",
    "category",
    "original_category",
    "priority",
    "original_priority",
    "assigned_role",
    "source_channel",
    "assignee",
    "due_at",
    "upstream_status",
    "customer_assessment",
    "handling_requirements",
    "people_involved",
    "current_danger",
}

SECTION_FIELDS = {
    "新建工单": "",
    "客户描述": "",
    "客户诉求": "",
    "居民诉求": "",
    "已核实信息": "",
    "已确认信息": "",
    "客服研判": "customer_assessment",
    "客服判断": "customer_assessment",
    "网格员研判": "customer_assessment",
    "网格研判": "customer_assessment",
    "处理要求": "handling_requirements",
    "系统信息": "",
    "工单结束": "",
}

ROLE_LABELS = {
    "property": "物业",
    "cleaning": "保洁",
    "police": "公安局/民警",
    "hospital": "医院/社区卫生",
    "community": "社区工作人员",
    "human_review": "人工审核",
}

ROLE_ALIASES = {
    "property": ("property", "物业", "物业维修", "维修", "报修", "公共设施", "maintenance", "repair", "facility", "facilities"),
    "cleaning": ("cleaning", "保洁", "环境卫生", "清洁", "垃圾", "sanitation", "clean", "garbage", "trash"),
    "police": ("police", "公安", "公安局", "派出所", "民警", "治安", "报警", "security", "public_security"),
    "hospital": ("hospital", "医院", "医疗", "医疗卫生", "社区卫生", "急救", "health", "medical", "clinic"),
    "community": ("community", "社区", "居委会", "社区工作人员", "政策咨询", "政务", "service"),
    "human_review": ("human_review", "manual_review", "manual", "人工", "人工审核", "人工确认", "待审核"),
}

ROLE_RULES = [
    (
        "police",
        "治安",
        ("公安", "派出所", "民警", "打架", "盗窃", "偷", "诈骗", "威胁", "赌博", "纠纷升级", "扰民严重"),
    ),
    (
        "hospital",
        "医疗卫生",
        (
            "医院",
            "社区卫生",
            "卫生院",
            "卫生服务中心",
            "医生",
            "护士",
            "急救",
            "拨打120",
            "打120",
            "急救电话",
            "心脏",
            "胸痛",
            "呼吸困难",
            "晕倒",
            "昏迷",
            "药吃完",
            "缺药",
            "发烧",
            "受伤",
            "疫苗",
            "孕检",
            "预防接种",
            "消毒",
            "传染",
        ),
    ),
    (
        "property",
        "物业维修",
        (
            "物业",
            "漏水",
            "电梯",
            "维修",
            "楼道灯",
            "门禁",
            "下水",
            "水管",
            "停水",
            "停电",
            "停车",
            "消防通道",
            "公共设施",
            "飞线充电",
            "电动车充电",
            "楼道充电",
            "占用通道",
            "通道堵塞",
        ),
    ),
    (
        "cleaning",
        "环境卫生",
        ("保洁", "垃圾", "卫生", "清扫", "清洁", "异味", "臭", "楼道脏", "杂物", "蚊虫", "积水"),
    ),
    (
        "community",
        "社区事务",
        ("社区", "居委会", "高龄", "津贴", "社保", "医保", "办证", "证明", "活动", "报名", "政策", "补贴"),
    ),
]

CATEGORY_ROLE_RULES = [
    ("property", "物业维修", ROLE_ALIASES["property"]),
    ("cleaning", "环境卫生", ROLE_ALIASES["cleaning"]),
    ("police", "治安", ROLE_ALIASES["police"]),
    ("hospital", "医疗卫生", ROLE_ALIASES["hospital"]),
    ("community", "社区事务", ROLE_ALIASES["community"]),
]

GENERIC_CATEGORY_ALIASES = {
    "complaint",
    "feedback",
    "other",
    "general",
    "unknown",
    "投诉",
    "反馈",
    "建议",
    "其他",
    "其它",
    "一般",
}

HIGH_PRIORITY_RE = re.compile(
    r"紧急|马上|立即|严重|危险|急救|(?<!\d)120(?!\d)|(?<!\d)119(?!\d)|火灾|着火|燃气|煤气|漏电|电梯困人|被困|"
    r"受伤|流血|打架|威胁|老人独居|儿童|孕妇|瘫痪|无法出门"
)
LOW_PRIORITY_RE = re.compile(r"咨询|了解|问一下|什么时候|哪里|如何办理|怎么申请")
RESOLVED_RE = re.compile(r"已处理|已解决|已完成|完成|解决了|修好|办结|closed|resolved|done", re.IGNORECASE)

PRIORITY_ALIASES = {
    "high": ("high", "urgent", "critical", "emergency", "紧急", "危急", "高", "重要"),
    "normal": ("normal", "medium", "普通", "正常", "一般", "中"),
    "low": ("low", "低", "较低", "不紧急"),
}


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "notify", "send"}


def _first_value(payload: dict[str, Any], field: str) -> str:
    for key in FIELD_ALIASES[field]:
        value = _string(payload.get(key))
        if value:
            return value
    return ""


def _normal_label(value: str) -> str:
    clean = re.sub(r"^[·•\-]\s*", "", value.strip())
    return re.sub(r"[\s：:]+", "", clean)


def _normal_section_label(value: str) -> str:
    return _normal_label(value).strip("【】[]")


def _fold(value: str) -> str:
    return re.sub(r"[\s_\-\/：:]+", "", value.strip().lower())


def _canonical_role(value: str) -> str:
    folded = _fold(value)
    if not folded:
        return ""

    for role, aliases in ROLE_ALIASES.items():
        for alias in aliases:
            alias_folded = _fold(alias)
            if folded == alias_folded or alias_folded in folded:
                return role
    return ""


def _normalize_message_newlines(value: str) -> str:
    text = _string(value)
    if ("\n" in text or "\r" in text) or not ("\\n" in text or "\\r" in text):
        return text

    # Some local OpenAI-compatible models double-escape tool-call newlines,
    # leaving the handler with one literal ``\\n``-delimited line.
    return text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")


def _is_generic_category(value: str) -> bool:
    folded = _fold(value)
    return any(folded == _fold(alias) or _fold(alias) in folded for alias in GENERIC_CATEGORY_ALIASES)


def parse_work_order_message(message: str) -> dict[str, str]:
    text = _normalize_message_newlines(message)
    if not text:
        return {}
    if text.lstrip().startswith("【Reins工单通知】"):
        return {}

    reverse_aliases: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            reverse_aliases[_normal_label(alias)] = field

    parsed: dict[str, str] = {}
    section_values: dict[str, list[str]] = {}
    current_section = ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for raw_line in lines:
        line = re.sub(r"^[·•\-]\s*", "", raw_line).strip()
        normalized_line = _normal_section_label(line)
        section_field = SECTION_FIELDS.get(normalized_line)
        if section_field is not None:
            current_section = section_field
            if section_field:
                section_values.setdefault(section_field, [])
            continue

        match = re.match(r"^([^:：]{1,40})[:：]\s*(.+)$", line)
        if not match:
            if current_section:
                section_values.setdefault(current_section, []).append(line)
            continue
        label = _normal_label(match.group(1))
        value = match.group(2).strip()
        field = reverse_aliases.get(label)
        if not field:
            if current_section:
                section_values.setdefault(current_section, []).append(line)
            continue
        if not value:
            continue
        if field == "category" and parsed.get("category") and parsed["category"] != value:
            parsed.setdefault("original_category", parsed["category"])
        parsed[field] = value

    for field, values in section_values.items():
        section_text = "\n".join(value for value in values if value).strip()
        if section_text:
            parsed[field] = section_text

    if "title" not in parsed:
        first_line = lines[0] if lines else ""
        first_line = re.sub(r"^[【\[]?(?:居民)?工单[】\]]?\s*", "", first_line).strip()
        if first_line and ":" not in first_line and "：" not in first_line:
            parsed["title"] = first_line[:120]

    return parsed


def _metadata_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    message = _string(payload.get("message") or payload.get("content") or payload.get("description"))
    metadata = parse_work_order_message(message)

    nested_metadata = payload.get("metadata")
    if isinstance(nested_metadata, dict):
        metadata.update(nested_metadata)

    raw_metadata = payload.get("metadata_json") or payload.get("metadataJson")
    if raw_metadata:
        try:
            decoded = json.loads(_string(raw_metadata))
        except json.JSONDecodeError:
            decoded = {}
        if isinstance(decoded, dict):
            metadata.update(decoded)

    for field in CLI_FIELD_NAMES:
        value = _first_value(payload, field)
        if value:
            metadata[field] = value

    metadata.setdefault("source_channel", "wecom_work_order")
    return metadata


def _message_from_metadata(metadata: dict[str, Any], fallback: str = "") -> str:
    parts = []
    for field, label in [
        ("external_id", "工单编号"),
        ("ticket_created_at", "创建时间"),
        ("title", "标题"),
        ("category", "类型"),
        ("priority", "优先级"),
        ("resident_ref", "居民引用"),
        ("resident_name", "居民"),
        ("resident_contact", "联系方式"),
        ("location", "位置"),
        ("source_channel", "来源"),
        ("upstream_status", "上游状态"),
        ("people_involved", "涉及人员"),
        ("current_danger", "当前危险"),
        ("description", "内容"),
        ("customer_assessment", "客服研判"),
        ("handling_requirements", "处理要求"),
    ]:
        value = _string(metadata.get(field))
        if value:
            parts.append(f"{label}: {value}")

    if parts:
        return "\n".join(parts)
    return _string(fallback)


def _analysis_text(metadata: dict[str, Any]) -> str:
    return "\n".join(
        _string(metadata.get(field))
        for field in (
            "title",
            "description",
            "customer_assessment",
            "handling_requirements",
            "current_danger",
            "category",
            "location",
            "source_channel",
        )
        if _string(metadata.get(field))
    )


def _role_from_category(category: str) -> tuple[str, str, str]:
    folded = _fold(category)
    if not folded:
        return "", "", ""

    for role, normalized_category, aliases in CATEGORY_ROLE_RULES:
        for alias in aliases:
            alias_folded = _fold(alias)
            if folded == alias_folded or alias_folded in folded:
                return normalized_category, role, f"provided_category:{role}"

    if _is_generic_category(category):
        return category, "human_review", "provided_category:generic"

    return category, "human_review", "provided_category:unmapped"


def _infer_category_and_role(metadata: dict[str, Any]) -> tuple[str, str, str]:
    provided_role = _canonical_role(_string(metadata.get("assigned_role")))
    if provided_role:
        category = _string(metadata.get("category"))
        if not category:
            for role, normalized_category, _aliases in CATEGORY_ROLE_RULES:
                if role == provided_role:
                    category = normalized_category
                    break
        return category, provided_role, "provided_assigned_role"

    category = _string(metadata.get("category"))
    if category:
        mapped_category, mapped_role, mapped_reason = _role_from_category(category)
        if mapped_role and mapped_role != "human_review":
            return mapped_category, mapped_role, mapped_reason

    text = _analysis_text(metadata)
    for role, category, keywords in ROLE_RULES:
        if any(keyword in text for keyword in keywords):
            return category, role, f"keyword:{role}"

    if category:
        return _role_from_category(category)

    return "", "human_review", "uncertain"


def _infer_priority(metadata: dict[str, Any]) -> tuple[str, str]:
    provided = _string(metadata.get("priority")).lower()
    if provided:
        folded = _fold(provided)
        for priority, aliases in PRIORITY_ALIASES.items():
            if any(folded == _fold(alias) for alias in aliases):
                return priority, "provided_priority"
        return provided, "provided_priority_unmapped"

    danger = _fold(_string(metadata.get("current_danger")))
    if danger in {"是", "有", "yes", "true", "1"}:
        return "high", "current_danger"

    text = _analysis_text(metadata)
    if HIGH_PRIORITY_RE.search(text):
        return "high", "high_priority_keywords"
    if LOW_PRIORITY_RE.search(text):
        return "low", "low_priority_keywords"
    return "normal", "default_priority"


def analyze_work_order(metadata: dict[str, Any]) -> dict[str, Any]:
    category, role, role_reason = _infer_category_and_role(metadata)
    priority, priority_reason = _infer_priority(metadata)

    validation_errors: list[str] = []
    if not _string(metadata.get("external_id")):
        validation_errors.append("missing_ticket_id")
    if not _string(metadata.get("title") or metadata.get("description")):
        validation_errors.append("missing_summary")
    if not _string(metadata.get("ticket_created_at")):
        validation_errors.append("missing_ticket_created_at")
    if role == "human_review":
        validation_errors.append("uncertain_assignment")

    status = "new"
    if validation_errors:
        status = "waiting_human_review"

    return {
        "category": category,
        "priority": priority,
        "assigned_role": role,
        "assigned_role_label": ROLE_LABELS.get(role, role),
        "assignment_reason": role_reason,
        "priority_reason": priority_reason,
        "validation_errors": validation_errors,
        "recommended_status": status,
    }


def _apply_analysis(metadata: dict[str, Any]) -> dict[str, Any]:
    canonical_role = _canonical_role(_string(metadata.get("assigned_role")))
    if canonical_role:
        metadata["assigned_role"] = canonical_role

    analysis = analyze_work_order(metadata)

    current_category = _string(metadata.get("category"))
    if analysis.get("category") and (not current_category or _is_generic_category(current_category)):
        if current_category and current_category != analysis["category"]:
            metadata.setdefault("original_category", current_category)
        metadata["category"] = analysis["category"]

    analyzed_priority = _string(analysis.get("priority"))
    current_priority = _string(metadata.get("priority"))
    if analyzed_priority and analyzed_priority != current_priority:
        if current_priority:
            metadata.setdefault("original_priority", current_priority)
        metadata["priority"] = analyzed_priority

    if analysis.get("assigned_role") and not _string(metadata.get("assigned_role")):
        metadata["assigned_role"] = analysis["assigned_role"]

    metadata["assigned_role_label"] = analysis["assigned_role_label"]
    metadata["assignment_reason"] = analysis["assignment_reason"]
    metadata["priority_reason"] = analysis["priority_reason"]
    metadata["validation_errors"] = analysis["validation_errors"]
    metadata["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    return analysis


def _existing_ticket(metadata: dict[str, Any]) -> dict[str, Any] | None:
    external_id = _string(metadata.get("external_id"))
    if not external_id:
        return None
    return find_record_by_metadata("external_id", external_id, kind="work_order")


def _record_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    record_id = _string(payload.get("record_id") or payload.get("recordId") or payload.get("id"))
    if record_id:
        record = get_record(int(record_id))
        if record:
            return record

    metadata = _metadata_from_payload(payload)
    existing = _existing_ticket(metadata)
    if existing:
        return existing

    raise ValueError("work order record not found.")


def _merge_metadata(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    current = existing.get("metadata")
    merged = dict(current if isinstance(current, dict) else {})
    for key, value in incoming.items():
        if value not in ("", None, []):
            merged[key] = value
    return merged


def _apply_notification_result(record: dict[str, Any], notification: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(record.get("metadata") if isinstance(record.get("metadata"), dict) else {})
    metadata["notification_status"] = notification.get("status", "")
    metadata["notification_target"] = notification.get("target_env", "")
    metadata["notification_channel"] = notification.get("channel", "")
    metadata["notification_recipients"] = notification.get("recipients", [])
    metadata["notification_message_id"] = notification.get("message_id", "")
    metadata["notification_error"] = notification.get("error", "")
    metadata["notified_at"] = datetime.now(timezone.utc).isoformat()

    current_status = _string(record.get("status"))
    next_status = current_status
    if notification.get("status") == "sent" and current_status in {"new", "pending_notification", "open"}:
        next_status = "notified"
    elif notification.get("status") == "pending_configuration" and current_status in {"new", "open"}:
        next_status = "pending_notification"

    if metadata.get("assigned_role") == "human_review":
        next_status = "waiting_human_review"

    return update_record(
        int(record["id"]),
        status=next_status,
        metadata=metadata,
    )


def create_work_order(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = _metadata_from_payload(payload)
    external_id = _string(metadata.get("external_id"))
    if external_id:
        metadata.setdefault("ticket_id", external_id)
    analysis = _apply_analysis(metadata)
    message = _message_from_metadata(
        metadata,
        fallback=_string(payload.get("message") or payload.get("content") or payload.get("description")),
    )
    if not message:
        raise ValueError("work order requires at least a title, description, or message.")

    sender_id = _string(
        payload.get("sender_id")
        or payload.get("senderId")
        or payload.get("external_userid")
        or payload.get("externalUserId")
        or payload.get("resident_id")
        or payload.get("residentId")
    )
    sender_name = _string(payload.get("sender_name") or payload.get("senderName") or metadata.get("resident_name"))
    chat_id = _string(payload.get("chat_id") or payload.get("chatId") or payload.get("conversation_id") or payload.get("conversationId"))
    chat_type = _string(payload.get("chat_type") or payload.get("chatType")) or "work_order"
    kind = _string(payload.get("kind") or payload.get("record_kind") or payload.get("recordKind")) or "work_order"
    explicit_status = _string(payload.get("status"))
    status = explicit_status or analysis["recommended_status"]

    metadata.setdefault("platform", _string(payload.get("platform")) or "wecom")
    metadata.setdefault("record_kind", kind)

    duplicate = False
    exact_duplicate = False
    existing = _existing_ticket(metadata)
    if existing:
        duplicate = True
        exact_duplicate = _string(existing.get("message")) == message
        metadata = _merge_metadata(existing, metadata)
        metadata["last_duplicate_received_at"] = datetime.now(timezone.utc).isoformat()
        if not explicit_status:
            status = _string(existing.get("status")) or status
        record = update_record(
            int(existing["id"]),
            status=status,
            message=message,
            selected_meaning=_string(metadata.get("title")),
            ai_fallback=False,
            metadata=metadata,
        )
    else:
        record = add_record(
            kind=kind,
            status=status,
            sender_id=sender_id,
            sender_name=sender_name,
            chat_id=chat_id,
            chat_type=chat_type,
            message=message,
            selected_meaning=_string(metadata.get("title")),
            matched_faq_id="",
            reply="",
            ai_fallback=False,
            metadata=metadata,
        )

    notification: dict[str, Any] | None = None
    if _bool(payload.get("notify")) or _bool(payload.get("send_notification") or payload.get("sendNotification")):
        previous_metadata = existing.get("metadata") if existing and isinstance(existing.get("metadata"), dict) else {}
        already_sent = previous_metadata.get("notification_status") == "sent"
        force_notify = _bool(payload.get("force_notify") or payload.get("forceNotify"))
        if exact_duplicate and already_sent and not force_notify:
            notification = {
                "ok": True,
                "status": "skipped_duplicate",
                "channel": previous_metadata.get("notification_channel", ""),
                "assigned_role": metadata.get("assigned_role", ""),
                "target_env": previous_metadata.get("notification_target", ""),
                "recipients": previous_metadata.get("notification_recipients", []),
                "content": "",
                "error": "",
            }
        else:
            notification = notify_staff(record, dry_run=_bool(payload.get("dry_run") or payload.get("dryRun")))
            record = _apply_notification_result(record, notification)

    return {
        "ok": True,
        "duplicate": duplicate,
        "record_saved": True,
        "record_kind": kind,
        "analysis": analysis,
        "notification": notification,
        "work_order": metadata,
        "record": record,
        "records_xlsx_path": str(export_records_xlsx()),
    }


def notify_work_order(payload: dict[str, Any]) -> dict[str, Any]:
    record = _record_from_payload(payload)
    notification = notify_staff(record, dry_run=_bool(payload.get("dry_run") or payload.get("dryRun")))
    record = _apply_notification_result(record, notification)
    return {
        "ok": bool(notification.get("ok")),
        "notification": notification,
        "record": record,
        "records_xlsx_path": str(export_records_xlsx()),
    }


def record_staff_reply(payload: dict[str, Any]) -> dict[str, Any]:
    record = _record_from_payload(payload)
    message = _string(payload.get("message") or payload.get("reply") or payload.get("content"))
    if not message:
        raise ValueError("staff reply message is required.")

    responder = _string(payload.get("responder") or payload.get("sender_name") or payload.get("senderName"))
    explicit_status = _string(payload.get("status"))
    status = explicit_status or ("resolved" if RESOLVED_RE.search(message) else "processing")
    replied_at = _string(payload.get("replied_at") or payload.get("repliedAt")) or datetime.now(timezone.utc).isoformat()

    metadata = dict(record.get("metadata") if isinstance(record.get("metadata"), dict) else {})
    history = metadata.get("staff_reply_history")
    if not isinstance(history, list):
        history = []
    history.append(
        {
            "message": message,
            "responder": responder,
            "status": status,
            "replied_at": replied_at,
        }
    )
    metadata["staff_reply_history"] = history
    metadata["last_staff_reply"] = message
    metadata["last_staff_reply_at"] = replied_at
    metadata["last_staff_responder"] = responder

    updated = update_record(
        int(record["id"]),
        status=status,
        reply=message,
        metadata=metadata,
    )
    return {
        "ok": True,
        "record_updated": True,
        "record": updated,
        "records_xlsx_path": str(export_records_xlsx()),
    }
