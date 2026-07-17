from __future__ import annotations

import subprocess

from pathlib import Path

from reins.features.presentation.config import get_engine_config


class PresentationDocumentIntakeError(RuntimeError):
    pass


def extract_pdf_markdown(
    source_path: Path,
    output_path: Path,
    *,
    timeout: int = 180,
) -> str:
    source = source_path.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise PresentationDocumentIntakeError(
            "A valid PDF source is required."
        )

    config = get_engine_config("ppt_master")
    python_path = config["venv"] / "bin" / "python"
    converter_path = (
        config["path"]
        / "skills"
        / "ppt-master"
        / "scripts"
        / "source_to_md"
        / "pdf_to_md.py"
    )
    if not python_path.is_file() or not converter_path.is_file():
        raise PresentationDocumentIntakeError(
            "PDF intake requires the PPT Master runtime."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            [
                str(python_path),
                str(converter_path),
                str(source),
                "--output",
                str(output_path),
                "--images",
                "none",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PresentationDocumentIntakeError(
            f"Could not extract the PDF source: {exc}"
        ) from exc

    if completed.returncode != 0 or not output_path.is_file():
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PresentationDocumentIntakeError(
            detail or "The PDF source could not be converted to text."
        )

    content = output_path.read_text(encoding="utf-8").strip()
    if not content:
        raise PresentationDocumentIntakeError(
            "The uploaded PDF does not contain extractable text."
        )
    return content
