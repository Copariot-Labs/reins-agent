from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from reins.compat.paths import (
    default_hermes_home,
    ensure_reins_home,
    get_reins_home,
    migration_marker_path,
)


class MigrationError(RuntimeError):
    pass


def _copy_directory_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        target = destination / item.name

        if target.exists():
            continue

        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def migrate_hermes_to_reins(force: bool = False) -> int:
    hermes_home = default_hermes_home()
    reins_home = get_reins_home()
    marker = migration_marker_path(reins_home)

    if not hermes_home.exists():
        print(f"No Hermes data directory found at {hermes_home}")
        print(f"Reins home is ready at {ensure_reins_home()}")
        return 0

    ensure_reins_home()

    if marker.exists() and not force:
        print("Migration already completed.")
        print(f"Marker: {marker}")
        print("Use `reins migrate hermes --force` to run again.")
        return 0

    if hermes_home.resolve() == reins_home.resolve():
        raise MigrationError(
            "Hermes home and Reins home resolve to the same directory. "
            "Refusing to migrate."
        )

    print(f"Source:      {hermes_home}")
    print(f"Destination: {reins_home}")
    print("Copying files that do not already exist...")

    _copy_directory_contents(hermes_home, reins_home)

    marker.write_text(
        "\n".join(
            [
                "Migrated Hermes data directory to Reins.",
                f"source={hermes_home}",
                f"destination={reins_home}",
                f"timestamp={datetime.now(timezone.utc).isoformat()}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print("Migration complete.")
    print(f"Original Hermes directory was not deleted: {hermes_home}")
    print(f"Migration marker written to: {marker}")

    return 0