from __future__ import annotations

from reins.compat.paths import get_reins_home


def print_about() -> int:
    print(
        f"""Reins

Reins is a local-first personal agent product.

Product layer:
  Name: Reins
  Command: reins
  Config prefix: REINS_*
  Data directory: {get_reins_home()}

Design:
  Reins owns product commands, local features, finance tools, reports, and user-facing docs.
  The upstream core provides the agent loop, memory, skills, gateway, and tool runtime.
"""
    )
    return 0