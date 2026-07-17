from __future__ import annotations

import json
import re
import shutil
import uuid

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from reins.features.presentation.config import (
    get_presentations_home,
)
from reins.features.presentation.models import (
    PresentationArtifact,
    PresentationJobState,
    PresentationJobStatus,
    PresentationPlan,
    PresentationRequest,
    PresentationWorkspace,
)


class PresentationStorageError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    token = uuid.uuid4().hex[:8]

    return f"ppt_{timestamp}_{token}"


def validate_job_id(job_id: str) -> str:
    if not re.fullmatch(r"ppt_[A-Za-z0-9_-]+", job_id):
        raise PresentationStorageError(
            f"Invalid presentation job ID: {job_id!r}"
        )

    return job_id


def write_json(
    path: Path,
    data: BaseModel | dict[str, Any] | list[Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if isinstance(data, BaseModel):
        payload = data.model_dump(
            mode="json",
        )
    else:
        payload = data

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PresentationStorageError(
            f"JSON file does not exist: {path}"
        )

    try:
        return json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise PresentationStorageError(
            f"Invalid JSON file: {path}"
        ) from exc


class PresentationStorage:
    def __init__(
        self,
        root: Path | None = None,
    ) -> None:
        self.root = Path(
            root or get_presentations_home()
        ).expanduser().resolve()

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def get_workspace(
        self,
        job_id: str,
    ) -> PresentationWorkspace:
        validate_job_id(job_id)

        job_root = self.root / job_id

        return PresentationWorkspace(
            job_id=job_id,
            root=job_root,
            request_path=job_root / "request.json",
            plan_path=job_root / "presentation-plan.json",
            status_path=job_root / "status.json",
            output_dir=job_root / "output",
            preview_dir=job_root / "previews",
            asset_dir=job_root / "assets",
            log_dir=job_root / "logs",
        )

    def create_workspace(
        self,
        request: PresentationRequest,
        job_id: str | None = None,
    ) -> PresentationWorkspace:
        resolved_job_id = job_id or create_job_id()
        workspace = self.get_workspace(
            resolved_job_id
        )
        source_path: Path | None = None
        if request.source_path is not None:
            source_path = request.source_path.expanduser().resolve()
            if not source_path.is_file():
                raise PresentationStorageError(
                    f"Presentation source does not exist: {source_path}"
                )

        if workspace.root.exists():
            raise PresentationStorageError(
                "Presentation workspace already exists: "
                f"{workspace.root}"
            )

        workspace.root.mkdir(
            parents=True,
            exist_ok=False,
        )

        for directory in [
            workspace.output_dir,
            workspace.preview_dir,
            workspace.asset_dir,
            workspace.log_dir,
        ]:
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )

        stored_request = request
        if source_path is not None:
            source_dir = workspace.asset_dir / "source"
            source_dir.mkdir(parents=True, exist_ok=True)
            staged_source = source_dir / source_path.name
            shutil.copy2(source_path, staged_source)
            stored_request = request.model_copy(
                update={"source_path": staged_source.resolve()}
            )

        now = utc_now_iso()

        state = PresentationJobState(
            job_id=workspace.job_id,
            status=PresentationJobStatus.CREATED,
            progress=0,
            phase="Presentation job created",
            action=request.action,
            engine=request.engine,
            created_at=now,
            updated_at=now,
        )

        self.save_request(
            workspace,
            stored_request,
        )

        self.save_state(
            workspace,
            state,
        )

        return workspace

    def save_request(
        self,
        workspace: PresentationWorkspace,
        request: PresentationRequest,
    ) -> None:
        write_json(
            workspace.request_path,
            request,
        )

    def load_request(
        self,
        workspace: PresentationWorkspace,
    ) -> PresentationRequest:
        return PresentationRequest.model_validate(
            read_json(workspace.request_path)
        )

    def save_plan(
        self,
        workspace: PresentationWorkspace,
        plan: PresentationPlan,
    ) -> None:
        write_json(
            workspace.plan_path,
            plan,
        )

    def load_plan(
        self,
        workspace: PresentationWorkspace,
    ) -> PresentationPlan:
        return PresentationPlan.model_validate(
            read_json(workspace.plan_path)
        )

    def save_state(
        self,
        workspace: PresentationWorkspace,
        state: PresentationJobState,
    ) -> None:
        write_json(
            workspace.status_path,
            state,
        )

    def load_state(
        self,
        workspace: PresentationWorkspace,
    ) -> PresentationJobState:
        return PresentationJobState.model_validate(
            read_json(workspace.status_path)
        )

    def update_state(
        self,
        workspace: PresentationWorkspace,
        *,
        status: PresentationJobStatus | None = None,
        progress: int | None = None,
        phase: str | None = None,
        engine: Any | None = None,
        output_path: Path | None = None,
        error: str | None = None,
        warnings: list[str] | None = None,
        artifacts: list[PresentationArtifact] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PresentationJobState:
        state = self.load_state(workspace)

        update_data: dict[str, Any] = {
            "updated_at": utc_now_iso(),
        }

        if status is not None:
            update_data["status"] = status

        if progress is not None:
            update_data["progress"] = progress

        if phase is not None:
            update_data["phase"] = phase

        if engine is not None:
            update_data["engine"] = engine

        if output_path is not None:
            update_data["output_path"] = output_path

        if error is not None:
            update_data["error"] = error

        if warnings is not None:
            update_data["warnings"] = warnings

        if artifacts is not None:
            update_data["artifacts"] = artifacts

        if metadata:
            update_data["metadata"] = {
                **state.metadata,
                **metadata,
            }

        updated_state = state.model_copy(
            update=update_data
        )

        self.save_state(
            workspace,
            updated_state,
        )

        return updated_state

    def list_job_ids(self) -> list[str]:
        jobs: list[str] = []

        for path in self.root.iterdir():
            if (
                path.is_dir()
                and path.name.startswith("ppt_")
            ):
                jobs.append(path.name)

        return sorted(
            jobs,
            reverse=True,
        )

    def list_job_states(
        self,
        *,
        limit: int = 25,
    ) -> list[PresentationJobState]:
        states: list[PresentationJobState] = []

        for job_id in self.list_job_ids():
            if len(states) >= max(1, min(limit, 100)):
                break

            workspace = self.get_workspace(job_id)
            try:
                states.append(self.load_state(workspace))
            except PresentationStorageError:
                continue

        return states
