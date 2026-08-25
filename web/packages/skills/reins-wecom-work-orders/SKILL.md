---
name: reins-wecom-work-orders
description: Process inbound WeCom group work-order notifications, route them to responsible staff by private message, update tickets from staff replies, and report ticket status. Use for messages beginning with `【新建工单】`, legacy `待处理工单`, staff handling results containing a Reins ticket ID, or requests about the WeCom work-order ledger.
---

# Reins WeCom Work Orders

Use the deterministic `reins_wecom` tools for every state change. Do not use computer use, desktop WeChat automation, or the resident-facing WeChat Customer Service flow.

## New Group Ticket

1. Trigger only when the full message starts with `【新建工单】` or the legacy `待处理工单` heading.
2. Never ingest a message starting with `【Reins工单通知】`; that is outbound Reins content.
3. Call `wecom_ingest_group_ticket` once. Pass the complete message unchanged. Include sender and group IDs when the gateway supplies them.
4. Leave `dry_run` false for real group tickets.
5. Check the tool result. A successful record with `notification.status=sent` means the ticket was saved and staff were notified privately. `pending_configuration`, `failed`, or `partial_sent` requires a concise operational warning.
   When the notification error contains `not allow to access from your ip` or WeCom error `60020`, say that private notification was attempted but WeCom rejected the current public IP because it is not trusted. Do not describe notification as disabled or unconfigured.
6. Reply in the source group with only a short receipt, for example: `工单 t_27f4f7b483174238 已记录，已通知医院/社区卫生。`

Do not invent a category, role, priority, recipient, or success state outside the tool result. Repeated delivery of the same ticket ID is safe and must still use the same tool; Reins deduplicates it.

## Staff Result

When a staff DM or allowed group message contains both a ticket ID and a handling result:

1. Extract the exact ticket ID, complete reply, and sender identity.
2. Call `wecom_record_staff_reply` once.
3. Report the updated status briefly. Do not create a second ticket.

If the message has no ticket ID, ask the staff member for the ticket ID before updating anything.

## Reports And Readiness

- Use `wecom_work_order_report` for date-range counts or operational summaries.
- Use `wecom_list_work_orders` for filtered records such as urgent, pending, category, department, location, or keyword queries.
- Use `wecom_get_work_order` for one exact ticket. Ask for the ticket ID when the user did not provide one.
- Use `wecom_export_work_orders_excel` when the user wants the current ledger in the Reins Workspace.
- Use `wecom_work_order_doctor` to verify Excel storage, application credentials, role recipients, and webhook fallbacks.
- For Word, Excel, or PowerPoint reports, use the real query/summary results as source data and then use Reins Office. Never create a generic report with invented counts.
- Respond in Simplified Chinese and keep progress summaries concise.
- Never use terminal commands, scripts, direct SQLite access, or package installation as a fallback for work-order requests.
- Never expose application secrets, access tokens, or unnecessary resident identifiers in chat.

## Scope

Reins receives and processes tickets after they enter WeCom. It does not answer residents, host WeChat Customer Service callbacks, or create tickets from ordinary conversation.
