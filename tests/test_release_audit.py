import tempfile
import unittest
from pathlib import Path

from scripts.release_audit import audit


class TestReleaseAudit(unittest.TestCase):
    def test_workspace_flags_proxy_artifact_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "iphone-v2rayn-package-2026-06-14").mkdir()
            (root / "iphone-v2rayn-package-2026-06-14" / "cc-http.proxy-url").write_text(
                "http://user:pass@example.com:8000",
                encoding="utf-8",
            )
            findings = audit(root, "workspace")
        self.assertTrue(any(item.kind == "sensitive-filename" for item in findings))

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
