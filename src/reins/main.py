from __future__ import annotations

from reins.compat.bootstrap import apply_bootstrap


def main() -> int:
    apply_bootstrap()

    from reins.compat.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())