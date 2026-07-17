from __future__ import annotations

import subprocess
import sys

from pathlib import Path

from reins.features.presentation.engine_registry import get_engine
from reins.features.presentation.editing import (
    convert_pptx,
    modify_pptx,
    restyle_pptx,
)
from reins.features.presentation.models import (
    PresentationAction,
    PresentationArtifact,
    PresentationEngine,
    PresentationJobState,
    PresentationJobStatus,
    PresentationOutputFormat,
    PresentationPlan,
    PresentationRequest,
    PresentationResult,
    PresentationWorkspace,
)
from reins.features.presentation.parsers import (
    extract_pdf_markdown,
    extract_pptx_plan,
)
from reins.features.presentation.planner import create_presentation_plan
from reins.features.presentation.qa import audit_presentation_artifact
from reins.features.presentation.router import select_presentation_engine
from reins.features.presentation.storage import (
    PresentationStorage,
    write_json,
)


class PresentationServiceError(RuntimeError):
    pass


class PresentationService:
    def __init__(
        self,
        storage: PresentationStorage | None = None,
    ) -> None:
        self.storage = storage or PresentationStorage()

    def submit_job(
        self,
        request: PresentationRequest,
    ) -> PresentationJobState:
        workspace = self.storage.create_workspace(request)
        self.storage.update_state(
            workspace,
            progress=1,
            phase="Queued for presentation planning",
        )

        log_path = workspace.log_dir / "worker.log"
        command = [
            sys.executable,
            "-m",
            "reins.features.presentation.cli",
            "run",
            workspace.job_id,
        ]

        try:
            with log_path.open("a", encoding="utf-8") as log_file:
                subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
        except OSError as exc:
            return self.storage.update_state(
                workspace,
                status=PresentationJobStatus.FAILED,
                phase="Could not start presentation worker",
                error=str(exc),
            )

        return self.storage.load_state(workspace)

    def create_job(
        self,
        request: PresentationRequest,
    ) -> PresentationResult:
        workspace = self.storage.create_workspace(request)
        return self._execute_job(
            workspace,
            self.storage.load_request(workspace),
        )

    def run_job(
        self,
        job_id: str,
    ) -> PresentationResult:
        workspace = self.storage.get_workspace(job_id)
        request = self.storage.load_request(workspace)
        return self._execute_job(workspace, request)

    def _execute_job(
        self,
        workspace: PresentationWorkspace,
        request: PresentationRequest,
    ) -> PresentationResult:
        if request.action != PresentationAction.NEW:
            return self._execute_existing_job(workspace, request)

        engine_name = request.engine
        warnings: list[str] = []
        source_artifacts: list[PresentationArtifact] = []

        try:
            request, source_artifacts = self._prepare_new_request(
                workspace,
                request,
            )
            self._validate_supported_request(request)
            engine_name = select_presentation_engine(request)
            engine_name, fallback_warning = self._resolve_available_engine(
                request,
                engine_name,
            )
            if fallback_warning:
                warnings.append(fallback_warning)

            self.storage.update_state(
                workspace,
                status=PresentationJobStatus.PLANNING,
                progress=10,
                phase="Creating presentation plan",
                engine=engine_name,
                warnings=warnings,
            )

            plan = self.create_plan(request)
            planning_warning = plan.metadata.get("planning_warning")
            if planning_warning:
                warnings.append(str(planning_warning))
            self.storage.save_plan(workspace, plan)

            self.storage.update_state(
                workspace,
                status=PresentationJobStatus.PLAN_READY,
                progress=35,
                phase="Presentation plan is ready",
                engine=engine_name,
                warnings=warnings,
                metadata={
                    "slide_count": len(plan.slides),
                    "title": plan.title,
                    "planner": plan.metadata.get("planner"),
                },
            )

            self.storage.update_state(
                workspace,
                status=PresentationJobStatus.RENDERING,
                progress=50,
                phase=f"Rendering with {engine_name.value}",
            )

            render_result = self._render_with_fallback(
                request=request,
                plan=plan,
                workspace=workspace,
                engine_name=engine_name,
                warnings=warnings,
            )
            engine_name = render_result.engine

            if not render_result.success or render_result.primary_output is None:
                raise PresentationServiceError(
                    "; ".join(render_result.errors)
                    or "The presentation renderer did not produce an output."
                )

            artifacts = [*source_artifacts, *render_result.artifacts]

            if request.run_qa:
                self.storage.update_state(
                    workspace,
                    status=PresentationJobStatus.QA,
                    progress=85,
                    phase="Validating presentation output",
                    engine=engine_name,
                )
                report = audit_presentation_artifact(
                    render_result.primary_output,
                    expected_slide_count=len(plan.slides),
                )
                report_path = workspace.root / "qa-report.json"
                write_json(report_path, report)
                artifacts.append(
                    PresentationArtifact(
                        kind="qa-report",
                        path=report_path,
                        mime_type="application/json",
                    )
                )
                warnings.extend(report.get("warnings", []))
                if not report.get("ok"):
                    raise PresentationServiceError(
                        "Presentation QA failed: "
                        + "; ".join(report.get("errors", []))
                    )

            warnings = list(dict.fromkeys(warnings))
            completed = self.storage.update_state(
                workspace,
                status=PresentationJobStatus.COMPLETED,
                progress=100,
                phase="Presentation is ready",
                engine=engine_name,
                output_path=render_result.primary_output,
                warnings=warnings,
                artifacts=artifacts,
                metadata={
                    "slide_count": len(plan.slides),
                    "title": plan.title,
                    "output_format": request.output_format.value,
                },
            )

            return PresentationResult(
                success=True,
                action=request.action,
                engine=engine_name,
                job_id=workspace.job_id,
                primary_output=completed.output_path,
                artifacts=artifacts,
                warnings=warnings,
                metadata={
                    "workspace": str(workspace.root),
                    "slide_count": len(plan.slides),
                },
            )

        except Exception as exc:
            self.storage.update_state(
                workspace,
                status=PresentationJobStatus.FAILED,
                progress=0,
                phase="Presentation job failed",
                engine=engine_name,
                error=str(exc),
                warnings=warnings,
            )
            return PresentationResult(
                success=False,
                action=request.action,
                engine=engine_name,
                job_id=workspace.job_id,
                warnings=warnings,
                errors=[str(exc)],
                metadata={"workspace": str(workspace.root)},
            )

    def _execute_existing_job(
        self,
        workspace: PresentationWorkspace,
        request: PresentationRequest,
    ) -> PresentationResult:
        engine_name = (
            PresentationEngine.FRONTEND_SLIDES
            if request.output_format == PresentationOutputFormat.HTML
            else PresentationEngine.NATIVE_PPTX
        )
        warnings: list[str] = []

        try:
            self._validate_supported_request(request)
            if request.source_path is None:
                raise PresentationServiceError(
                    "A staged presentation source is required."
                )

            self.storage.update_state(
                workspace,
                status=PresentationJobStatus.ANALYZING,
                progress=10,
                phase="Analyzing source presentation",
                engine=engine_name,
            )
            plan = extract_pptx_plan(request.source_path, request)
            self.storage.save_plan(workspace, plan)

            self.storage.update_state(
                workspace,
                status=PresentationJobStatus.PLAN_READY,
                progress=35,
                phase="Source presentation inventory is ready",
                engine=engine_name,
                metadata={
                    "slide_count": len(plan.slides),
                    "title": plan.title,
                    "planner": plan.metadata.get("planner"),
                },
            )
            self.storage.update_state(
                workspace,
                status=PresentationJobStatus.APPLYING,
                progress=55,
                phase=f"Applying {request.action.value} operation",
                engine=engine_name,
            )

            if request.action == PresentationAction.MODIFY:
                render_result = modify_pptx(
                    request=request,
                    workspace=workspace.root,
                )
            elif request.action == PresentationAction.RESTYLE:
                render_result = restyle_pptx(
                    request=request,
                    workspace=workspace.root,
                )
            elif request.action == PresentationAction.CONVERT:
                render_result = convert_pptx(
                    request=request,
                    plan=plan,
                    workspace=workspace.root,
                )
            else:
                raise PresentationServiceError(
                    f"Unsupported presentation action: {request.action.value}"
                )

            if not render_result.success or render_result.primary_output is None:
                raise PresentationServiceError(
                    "; ".join(render_result.errors)
                    or "The presentation operation did not produce an output."
                )

            engine_name = render_result.engine
            warnings.extend(render_result.warnings)
            artifacts = list(render_result.artifacts)

            if request.run_qa:
                self.storage.update_state(
                    workspace,
                    status=PresentationJobStatus.QA,
                    progress=85,
                    phase="Validating presentation output",
                    engine=engine_name,
                )
                report = audit_presentation_artifact(
                    render_result.primary_output,
                    expected_slide_count=len(plan.slides),
                )
                report_path = workspace.root / "qa-report.json"
                write_json(report_path, report)
                artifacts.append(
                    PresentationArtifact(
                        kind="qa-report",
                        path=report_path,
                        mime_type="application/json",
                    )
                )
                warnings.extend(report.get("warnings", []))
                if not report.get("ok"):
                    raise PresentationServiceError(
                        "Presentation QA failed: "
                        + "; ".join(report.get("errors", []))
                    )

            if render_result.primary_output.suffix.lower() == ".pptx":
                plan = extract_pptx_plan(render_result.primary_output, request)
                self.storage.save_plan(workspace, plan)

            warnings = list(dict.fromkeys(warnings))
            completed = self.storage.update_state(
                workspace,
                status=PresentationJobStatus.COMPLETED,
                progress=100,
                phase="Presentation revision is ready",
                engine=engine_name,
                output_path=render_result.primary_output,
                warnings=warnings,
                artifacts=artifacts,
                metadata={
                    "slide_count": len(plan.slides),
                    "title": plan.title,
                    "output_format": request.output_format.value,
                    **render_result.metadata,
                },
            )
            return PresentationResult(
                success=True,
                action=request.action,
                engine=engine_name,
                job_id=workspace.job_id,
                primary_output=completed.output_path,
                artifacts=artifacts,
                warnings=warnings,
                metadata={
                    "workspace": str(workspace.root),
                    "slide_count": len(plan.slides),
                    **render_result.metadata,
                },
            )

        except Exception as exc:
            self.storage.update_state(
                workspace,
                status=PresentationJobStatus.FAILED,
                progress=0,
                phase="Presentation job failed",
                engine=engine_name,
                error=str(exc),
                warnings=warnings,
            )
            return PresentationResult(
                success=False,
                action=request.action,
                engine=engine_name,
                job_id=workspace.job_id,
                warnings=warnings,
                errors=[str(exc)],
                metadata={"workspace": str(workspace.root)},
            )

    def _validate_supported_request(
        self,
        request: PresentationRequest,
    ) -> None:
        if request.action == PresentationAction.NEW and (
            request.output_format == PresentationOutputFormat.PDF
        ):
            raise PresentationServiceError(
                "Direct PDF rendering is not available. Generate HTML or PPTX."
            )

        if request.action == PresentationAction.NEW:
            if request.source_path is not None and (
                not request.source_path.is_file()
                or request.source_path.suffix.lower() != ".pdf"
            ):
                raise PresentationServiceError(
                    "New presentation source material must be a valid PDF."
                )
            return

        if request.source_path is None or not request.source_path.is_file():
            raise PresentationServiceError(
                "A valid source_path is required for existing-deck operations."
            )
        if request.source_path.suffix.lower() != ".pptx":
            raise PresentationServiceError(
                "Modify, restyle, and conversion currently accept PPTX sources."
            )
        if request.action in {
            PresentationAction.MODIFY,
            PresentationAction.RESTYLE,
        } and request.output_format != PresentationOutputFormat.PPTX:
            raise PresentationServiceError(
                f"{request.action.value.title()} produces an editable PPTX revision."
            )
        if (
            request.action == PresentationAction.CONVERT
            and request.output_format == PresentationOutputFormat.PPTX
        ):
            raise PresentationServiceError(
                "Choose HTML or PDF when converting a PPTX source."
            )

    def _prepare_new_request(
        self,
        workspace: PresentationWorkspace,
        request: PresentationRequest,
    ) -> tuple[PresentationRequest, list[PresentationArtifact]]:
        if request.source_path is None:
            return request, []
        if request.source_path.suffix.lower() != ".pdf":
            return request, []

        markdown_path = workspace.root / "source-content.md"
        source_content = extract_pdf_markdown(
            request.source_path,
            markdown_path,
        )
        prompt = (request.prompt or "").strip()
        separator = (
            "\n\nSource material extracted from the uploaded PDF:\n"
        )
        available = max(0, 30_000 - len(prompt) - len(separator))
        combined_prompt = (prompt + separator + source_content[:available])[
            :30_000
        ]
        enriched = request.model_copy(
            update={
                "prompt": combined_prompt,
                "metadata": {
                    **request.metadata,
                    "source_type": "pdf",
                    "source_file_name": request.source_path.name,
                },
            }
        )
        return enriched, [
            PresentationArtifact(
                kind="source-markdown",
                path=markdown_path,
                mime_type="text/markdown",
            )
        ]

    def _resolve_available_engine(
        self,
        request: PresentationRequest,
        engine_name: PresentationEngine,
    ) -> tuple[PresentationEngine, str | None]:
        if (
            engine_name == PresentationEngine.PPT_MASTER
            and request.aspect_ratio == "4:3"
        ):
            if request.engine == PresentationEngine.AUTO:
                native = get_engine(PresentationEngine.NATIVE_PPTX)
                native_health = native.health()
                if native_health.available:
                    return (
                        PresentationEngine.NATIVE_PPTX,
                        "PPT Master uses a 16:9 SVG contract; used the native "
                        "PPTX renderer for the requested 4:3 deck.",
                    )
            raise PresentationServiceError(
                "PPT Master currently supports 16:9 output in Reins. "
                "Use auto or native_pptx for a 4:3 deck."
            )

        engine = get_engine(engine_name)
        health = engine.health()
        if health.available:
            return engine_name, None

        if (
            request.engine == PresentationEngine.AUTO
            and request.output_format == PresentationOutputFormat.PPTX
        ):
            native = get_engine(PresentationEngine.NATIVE_PPTX)
            native_health = native.health()
            if native_health.available:
                return (
                    PresentationEngine.NATIVE_PPTX,
                    f"{engine_name.value} was unavailable; used the native PPTX renderer.",
                )

        raise PresentationServiceError(health.message)

    def _render_with_fallback(
        self,
        *,
        request: PresentationRequest,
        plan: PresentationPlan,
        workspace: PresentationWorkspace,
        engine_name: PresentationEngine,
        warnings: list[str],
    ) -> PresentationResult:
        engine = get_engine(engine_name)

        try:
            return engine.render(
                request=request,
                plan=plan,
                workspace=workspace.root,
            )
        except Exception as exc:
            if not (
                request.engine == PresentationEngine.AUTO
                and request.output_format == PresentationOutputFormat.PPTX
                and engine_name != PresentationEngine.NATIVE_PPTX
            ):
                raise

            native = get_engine(PresentationEngine.NATIVE_PPTX)
            native_health = native.health()
            if not native_health.available:
                raise

            warnings.append(
                f"{engine_name.value} rendering failed; used the native PPTX renderer."
            )
            failure_log = workspace.log_dir / "renderer-fallback.log"
            failure_log.write_text(str(exc), encoding="utf-8")
            result = native.render(
                request=request,
                plan=plan,
                workspace=workspace.root,
            )
            result.artifacts.append(
                PresentationArtifact(
                    kind="fallback-log",
                    path=failure_log,
                    mime_type="text/plain",
                )
            )
            return result

    def create_plan(
        self,
        request: PresentationRequest,
    ) -> PresentationPlan:
        return create_presentation_plan(request)

    def get_job_state(
        self,
        job_id: str,
    ) -> PresentationJobState:
        workspace = self.storage.get_workspace(job_id)
        return self.storage.load_state(workspace)

    def get_job_plan(
        self,
        job_id: str,
    ) -> PresentationPlan:
        workspace = self.storage.get_workspace(job_id)
        return self.storage.load_plan(workspace)

    def get_job_workspace(
        self,
        job_id: str,
    ) -> Path:
        return self.storage.get_workspace(job_id).root
