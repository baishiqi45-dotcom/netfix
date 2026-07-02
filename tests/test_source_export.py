import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.release_audit import audit
from scripts.source_export import create_source_export


class TestSourceExport(unittest.TestCase):
    def test_source_export_excludes_local_sensitive_and_generated_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / "netfix").mkdir()
            (root / "tests").mkdir()
            (root / "scripts").mkdir()
            (root / "docs").mkdir()
            (root / "docs" / "github").mkdir()
            (root / "cases").mkdir()
            (root / "output" / "playwright" / "audit").mkdir(parents=True)
            (root / "gui" / "web").mkdir(parents=True)
            (root / "gui" / "macos").mkdir(parents=True)
            (root / "rules").mkdir()
            (root / "README.md").write_text("# Netfix\n", encoding="utf-8")
            (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
            (root / "SECURITY.md").write_text("security\n", encoding="utf-8")
            (root / ".gitignore").write_text("dist/\n", encoding="utf-8")
            (root / ".github" / "workflows" / "ci.yml").write_text("name: ci\n", encoding="utf-8")
            (root / "netfix.py").write_text("print('netfix')\n", encoding="utf-8")
            (root / "netfix" / "cli.py").write_text("def main(): pass\n", encoding="utf-8")
            (root / "tests" / "test_cli.py").write_text("def test_cli(): pass\n", encoding="utf-8")
            (root / "scripts" / "release_audit.py").write_text("# audit\n", encoding="utf-8")
            (root / "docs" / "PRIVACY_POLICY_DRAFT.md").write_text("privacy\n", encoding="utf-8")
            (root / "docs" / "EULA_DRAFT.md").write_text("eula\n", encoding="utf-8")
            (root / "docs" / "github" / "STAR_GUIDE.md").write_text("public launch guide\n", encoding="utf-8")
            (root / "docs" / "github" / "SCREENSHOTS.md").write_text("public screenshots\n", encoding="utf-8")
            (root / "docs" / "INTERNAL_PRODUCT_PROMPT_2099_01_01.md").write_text("internal prompt\n", encoding="utf-8")
            (root / "docs" / "INTERNAL_MACRO_AUDIT_2099_01_01.md").write_text("internal audit\n", encoding="utf-8")
            (root / "docs" / "PROXY_DEPLOY_AUDIT_2026_06_29.md").write_text("internal proxy audit\n", encoding="utf-8")
            (root / "cases" / "TEMPLATE.md").write_text("# Case template\n", encoding="utf-8")
            (root / "cases" / "2026-06-29-private-case.md").write_text("private case\n", encoding="utf-8")
            (root / "output" / "playwright" / "audit" / "01-home.png").write_bytes(b"png")
            (root / "final.md").write_text("internal final notes\n", encoding="utf-8")
            (root / "document.md").write_text("internal long notes\n", encoding="utf-8")
            (root / "HANDOFF.md").write_text("internal handoff\n", encoding="utf-8")
            (root / "PRODUCT_STRATEGY.md").write_text("internal strategy\n", encoding="utf-8")
            (root / "gui" / "web" / "index.html").write_text("<html></html>", encoding="utf-8")
            (root / "gui" / "macos" / "Package.swift").write_text("// swift\n", encoding="utf-8")
            (root / "rules" / "root_causes.yml").write_text("[]\n", encoding="utf-8")

            sensitive_dir = root / "private-proxy-package-2026-06-14"
            sensitive_dir.mkdir()
            (sensitive_dir / "cc-http.proxy-url").write_text(
                "http://real-user:real-secret@proxy.example.net:8000",
                encoding="utf-8",
            )
            (root / "Netfix-0.2.0.dmg").write_text("binary", encoding="utf-8")
            (root / "Netfix-0.2.0-macos.zip").write_text("binary", encoding="utf-8")
            (root / "dist").mkdir()
            (root / "dist" / "netfix-backend").write_text("binary", encoding="utf-8")
            (root / "gui" / "macos" / ".build").mkdir()
            (root / "gui" / "macos" / ".build" / "Netfix.app").write_text("bundle", encoding="utf-8")
            (root / ".netfix").mkdir()
            (root / ".netfix" / "last_report.json").write_text("{}", encoding="utf-8")

            result = create_source_export(root=root, out_dir=root / "open-source-export", make_zip=True)

            export_root = Path(result["export_root"])
            self.assertTrue(result["ok"])
            self.assertTrue((export_root / "README.md").exists())
            self.assertTrue((export_root / "LICENSE").exists())
            self.assertTrue((export_root / "SECURITY.md").exists())
            self.assertTrue((export_root / ".github" / "workflows" / "ci.yml").exists())
            self.assertTrue((export_root / "netfix.py").exists())
            self.assertTrue((export_root / "netfix" / "cli.py").exists())
            self.assertTrue((export_root / "tests" / "test_cli.py").exists())
            self.assertTrue((export_root / "docs" / "PRIVACY_POLICY_DRAFT.md").exists())
            self.assertTrue((export_root / "docs" / "EULA_DRAFT.md").exists())
            self.assertTrue((export_root / "docs" / "github" / "STAR_GUIDE.md").exists())
            self.assertTrue((export_root / "docs" / "github" / "SCREENSHOTS.md").exists())
            self.assertTrue((export_root / "cases" / "TEMPLATE.md").exists())
            self.assertTrue((export_root / "gui" / "web" / "index.html").exists())
            self.assertTrue((export_root / "gui" / "macos" / "Package.swift").exists())
            self.assertTrue((export_root / "rules" / "root_causes.yml").exists())
            self.assertTrue((export_root / "SOURCE-EXPORT-MANIFEST.json").exists())
            self.assertTrue((export_root / "SHA256SUMS.txt").exists())
            self.assertFalse((export_root / "private-proxy-package-2026-06-14").exists())
            self.assertFalse((export_root / "Netfix-0.2.0.dmg").exists())
            self.assertFalse((export_root / "Netfix-0.2.0-macos.zip").exists())
            self.assertFalse((export_root / "dist").exists())
            self.assertFalse((export_root / "gui" / "macos" / ".build").exists())
            self.assertFalse((export_root / ".netfix").exists())
            self.assertFalse((export_root / "docs" / "INTERNAL_PRODUCT_PROMPT_2099_01_01.md").exists())
            self.assertFalse((export_root / "docs" / "INTERNAL_MACRO_AUDIT_2099_01_01.md").exists())
            self.assertFalse((export_root / "docs" / "PROXY_DEPLOY_AUDIT_2026_06_29.md").exists())
            self.assertFalse((export_root / "cases" / "2026-06-29-private-case.md").exists())
            self.assertFalse((export_root / "output").exists())
            self.assertFalse((export_root / "final.md").exists())
            self.assertFalse((export_root / "document.md").exists())
            self.assertFalse((export_root / "HANDOFF.md").exists())
            self.assertFalse((export_root / "PRODUCT_STRATEGY.md").exists())
            self.assertEqual(audit(export_root, "workspace"), [])

            manifest = json.loads((export_root / "SOURCE-EXPORT-MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "netfix_source_export.v1")
            self.assertFalse(manifest["source_workspace_included_private_artifacts"])
            self.assertNotIn(str(root), json.dumps(manifest, ensure_ascii=False))
            self.assertEqual(manifest["source_root"], "<source-workspace>")
            self.assertNotIn("excluded_paths", manifest)
            self.assertGreater(manifest["excluded_counts_by_reason"]["sensitive_name"], 0)
            self.assertGreater(manifest["excluded_counts_by_reason"]["generated_release_artifact"], 0)
            self.assertGreater(manifest["excluded_counts_by_reason"]["build_or_runtime_directory"], 0)
            self.assertGreater(manifest["excluded_counts_by_reason"]["internal_docs"], 0)
            self.assertGreater(manifest["excluded_counts_by_reason"]["local_cases"], 0)
            manifest_text = json.dumps(manifest, ensure_ascii=False)
            self.assertNotIn("private-proxy-package-2026-06-14", manifest_text)
            self.assertNotIn("INTERNAL_PRODUCT_PROMPT", manifest_text)
            self.assertNotIn("2026-06-29-private-case", manifest_text)
            self.assertIn("README.md", manifest["files"])
            self.assertTrue(result["zip"])
            self.assertTrue(Path(result["zip"]).exists())

    def test_source_export_cli_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "netfix").mkdir()
            (root / "README.md").write_text("# Netfix\n", encoding="utf-8")
            (root / "netfix.py").write_text("print('netfix')\n", encoding="utf-8")

            proc = subprocess.run(
                [
                    "python3",
                    str(Path(__file__).resolve().parents[1] / "scripts" / "source_export.py"),
                    "--root",
                    str(root),
                    "--out-dir",
                    str(root / "out"),
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.loads(proc.stdout)
            self.assertTrue(data["ok"])
            self.assertTrue(Path(data["export_root"]).exists())

    def test_source_export_manifest_sanitizes_audit_finding_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Netfix\n", encoding="utf-8")
            (root / "netfix.py").write_text("print('netfix')\n", encoding="utf-8")
            private_path = root / "private" / "cc-http.proxy-url"
            private_path.parent.mkdir()
            private_path.write_text("redacted fixture", encoding="utf-8")
            finding = SimpleNamespace(
                severity="blocker",
                kind="secret-like-text",
                path=str(private_path),
                message=f"found private file under {root}",
                next_steps=[f"remove {private_path}"],
            )

            with patch("scripts.source_export.audit", return_value=[finding]):
                result = create_source_export(root=root, out_dir=root / "out", make_zip=False)

            self.assertFalse(result["ok"])
            export_root = Path(result["export_root"])
            manifest_text = (export_root / "SOURCE-EXPORT-MANIFEST.json").read_text(encoding="utf-8")
            self.assertNotIn(str(root), manifest_text)
            self.assertNotIn("cc-http.proxy-url", manifest_text)
            self.assertIn("<source-workspace>", manifest_text)
            self.assertIn("<private-proxy-config>", manifest_text)


if __name__ == "__main__":
    unittest.main()
