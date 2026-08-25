from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from reins.compat.paths import (
    REINS_WORKSPACE_FOLDERS,
    ensure_reins_workspace,
    get_reins_workspace,
    reins_workspace_dir,
)
from reins.features.finance.export import get_export_dir
from reins.features.office.paths import migrate_legacy_office_documents, unique_office_path


class ReinsWorkspaceTests(unittest.TestCase):
    def test_configured_workspace_creates_native_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "Reins Workspace"
            with patch.dict(os.environ, {"REINS_WORKSPACE_ROOT": str(workspace)}, clear=True):
                self.assertEqual(get_reins_workspace(), workspace.resolve())
                self.assertEqual(ensure_reins_workspace(), workspace.resolve())
                self.assertEqual(reins_workspace_dir("Inbox"), workspace.resolve() / "Inbox")
                for folder in REINS_WORKSPACE_FOLDERS:
                    self.assertTrue((workspace / folder).is_dir())

    def test_office_formats_use_visible_workspace_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "Reins Workspace"
            with patch.dict(os.environ, {"REINS_WORKSPACE_ROOT": str(workspace)}, clear=True):
                word = unique_office_path(title="防汛工作方案", office_format="docx")
                sheet = unique_office_path(title="预算", office_format="xlsx")
                slides = unique_office_path(title="汇报", office_format="pptx")

            self.assertEqual(word.parent, workspace.resolve() / "Word")
            self.assertEqual(sheet.parent, workspace.resolve() / "Excel")
            self.assertEqual(slides.parent, workspace.resolve() / "PowerPoint")
            self.assertIn("防汛工作方案", word.name)

    def test_legacy_indexed_office_files_are_moved_and_reindexed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            workspace = Path(directory) / "Reins Workspace"
            legacy = home / "office" / "documents"
            legacy.mkdir(parents=True)
            source = legacy / "旧方案.docx"
            source.write_bytes(b"docx")
            index = home / "office" / "documents.jsonl"
            index.write_text(
                json.dumps({
                    "id": "office_1",
                    "title": "旧方案",
                    "kind": "docx",
                    "path": str(source),
                    "file_name": source.name,
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {
                "REINS_HOME": str(home),
                "REINS_WORKSPACE_ROOT": str(workspace),
            }, clear=True):
                self.assertEqual(migrate_legacy_office_documents(), 1)

            destination = workspace.resolve() / "Word" / source.name
            self.assertTrue(destination.is_file())
            self.assertFalse(source.exists())
            latest = json.loads(index.read_text(encoding="utf-8").splitlines()[-1])
            self.assertEqual(latest["path"], str(destination))

    def test_finance_exports_use_generated_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "Reins Workspace"
            with patch.dict(os.environ, {"REINS_WORKSPACE_ROOT": str(workspace)}, clear=True):
                export_dir = get_export_dir()

            self.assertEqual(export_dir, workspace.resolve() / "Generated" / "Finance")
            self.assertTrue(export_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
