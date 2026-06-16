from __future__ import annotations


DANGEROUS_ACTIONS = {
    "send_message",
    "submit_form",
    "delete_file",
    "make_payment",
    "change_password",
    "install_software",
}


def requires_confirmation(action: str, context: dict | None = None) -> bool:
    context = context or {}

    if action in DANGEROUS_ACTIONS:
        return True

    if context.get("contains_password"):
        return True

    if context.get("external_submit"):
        return True

    return False