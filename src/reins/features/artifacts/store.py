from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reins.features.artifacts.paths import artifact_index_path, artifact_root
from reins.features.artifacts.schema import ArtifactRecord, normalize_artifact_format


class ArtifactStore:
    def __init__(
        self,
        *,
        root: str | Path | None = None,
        index_path: str | Path | None = None,
    ) -> None:
        self.root = Path(root) if root else artifact_root()
        self.root.mkdir(parents=True, exist_ok=True)

        self.index_path = Path(index_path) if index_path else artifact_index_path()
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, record: ArtifactRecord) -> ArtifactRecord:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)

        with self.index_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")

        return record

    def register(
        self,
        *,
        title: str,
        kind: str,
        path: str | Path,
        summary: str = "",
        source: str = "reins",
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        record = ArtifactRecord.create(
            title=title,
            kind=kind,
            path=path,
            summary=summary,
            source=source,
            metadata=metadata,
        )
        return self.save(record)

    def list(self, *, limit: int = 50, kind: str | None = None) -> list[ArtifactRecord]:
        if not self.index_path.exists():
            return []

        records: list[ArtifactRecord] = []

        with self.index_path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()

                if not line:
                    continue

                try:
                    data = json.loads(line)
                    record = ArtifactRecord.from_dict(data)
                except Exception:
                    continue

                if kind:
                    normalized_kind = normalize_artifact_format(kind, default=kind)
                    if record.kind != normalized_kind:
                        continue

                records.append(record)

        if limit <= 0:
            return records

        return records[-limit:]

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        for record in reversed(self.list(limit=0)):
            if record.id == artifact_id:
                return record

        return None

    def latest(self, *, kind: str | None = None) -> ArtifactRecord | None:
        records = self.list(limit=0, kind=kind)

        if not records:
            return None

        return records[-1]


_DEFAULT_STORE: ArtifactStore | None = None


def get_default_artifact_store() -> ArtifactStore:
    global _DEFAULT_STORE

    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = ArtifactStore()

    return _DEFAULT_STORE