import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.release_audit import audit, main


class TestReleaseAudit(unittest.TestCase):
    def test_workspace_flags_proxy_artifact_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "private-proxy-package-2026-06-14").mkdir()
            (root / "private-proxy-package-2026-06-14" / "private.proxy-url").write_text(
                "http://user:pass@example.com:8000",
                encoding="utf-8",
            )
            findings = audit(root, "workspace")
        sensitive = next(item for item in findings if item.kind == "sensitive-filename")
        self.assertTrue(sensitive.next_steps)
        self.assertTrue(any("rotate" in step.lower() for step in sensitive.next_steps))

    def test_workspace_flags_git_tracked_release_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = Mock(returncode=0, stdout="Netfix-0.2.0.dmg\nNetfix-0.2.0-macos.zip\n")
            with patch("scripts.release_audit.subprocess.run", return_value=proc) as run:
                findings = audit(root, "workspace")

        tracked = [item for item in findings if item.kind == "tracked-release-artifact"]
        self.assertEqual({item.path for item in tracked}, {"Netfix-0.2.0.dmg", "Netfix-0.2.0-macos.zip"})
        self.assertTrue(all("git rm --cached" in " ".join(item.next_steps) for item in tracked))
        run.assert_called_once()

    def test_workspace_skips_generated_build_and_export_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated = root / "gui" / "macos" / ".build" / "release-export" / "Netfix-0.2.0-macos"
            generated.mkdir(parents=True)
            (generated / "README-FIRST.md").write_text(
                "http://real-user:real-password@example.com:8000",
                encoding="utf-8",
            )
            (root / "open-source-export" / "Netfix-0.2.0-source").mkdir(parents=True)
            (root / "open-source-export" / "Netfix-0.2.0-source" / "private.proxy-url").write_text(
                "http://real-user:real-password@example.com:8000",
                encoding="utf-8",
            )
            with patch("scripts.release_audit._git_tracked_release_artifacts", return_value=[]):
                findings = audit(root, "workspace")

        self.assertEqual(findings, [])

    def test_cli_text_output_prints_next_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "private.proxy-url").write_text("http://real-user:real-password@example.com:8000", encoding="utf-8")
            with patch("scripts.release_audit._git_tracked_release_artifacts", return_value=[]), \
                    patch("sys.stderr") as stderr:
                code = main(["--root", str(root), "--scope", "workspace", "--warn-only"])

        self.assertEqual(code, 0)
        output = "".join(str(call.args[0]) for call in stderr.write.call_args_list)
        self.assertIn("next:", output)

    def test_bundle_requires_core_files_and_rejects_sensitive_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Contents" / "MacOS").mkdir(parents=True)
            (root / "Contents" / "Resources" / "netfix").mkdir(parents=True)
            (root / "Contents" / "Resources" / "rules").mkdir(parents=True)
            (root / "Contents" / "Resources" / "gui" / "web").mkdir(parents=True)
            (root / "Contents" / "MacOS" / "Netfix").write_text("bin", encoding="utf-8")
            (root / "Contents" / "Resources" / "netfix.py").write_text("print(1)", encoding="utf-8")
            (root / "Contents" / "Resources" / "gui" / "web" / "index.html").write_text("<html></html>", encoding="utf-8")
            (root / "Contents" / "Resources" / "PrivacyInfo.xcprivacy").write_text("<plist/>", encoding="utf-8")
            (root / "Contents" / "Resources" / "release-manifest.json").write_text("{}", encoding="utf-8")
            self.assertEqual(audit(root, "bundle"), [])

            (root / "Contents" / "Resources" / "cc-http.proxy-url").write_text("x", encoding="utf-8")
            findings = audit(root, "bundle")
        self.assertTrue(any(item.kind == "sensitive-filename" for item in findings))

    def test_bundle_requires_web_console_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Contents" / "MacOS").mkdir(parents=True)
            (root / "Contents" / "Resources" / "netfix").mkdir(parents=True)
            (root / "Contents" / "Resources" / "rules").mkdir(parents=True)
            (root / "Contents" / "MacOS" / "Netfix").write_text("bin", encoding="utf-8")
            (root / "Contents" / "Resources" / "netfix.py").write_text("print(1)", encoding="utf-8")
            (root / "Contents" / "Resources" / "PrivacyInfo.xcprivacy").write_text("<plist/>", encoding="utf-8")
            (root / "Contents" / "Resources" / "release-manifest.json").write_text("{}", encoding="utf-8")

            findings = audit(root, "bundle")

        self.assertTrue(any(item.path == "Contents/Resources/gui/web/index.html" for item in findings))


if __name__ == "__main__":
    unittest.main()
