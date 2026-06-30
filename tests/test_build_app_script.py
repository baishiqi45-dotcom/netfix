from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_APP = ROOT / "gui" / "macos" / "build_app.sh"
BUILD_BACKEND = ROOT / "scripts" / "build_backend_binary.sh"
NETFIX_WRAPPER = ROOT / "netfix.py"


def test_build_app_keeps_unsigned_local_candidate_runnable():
    script = BUILD_APP.read_text(encoding="utf-8")

    skip_ad_hoc_app_sign = script.index('echo "Skipping ad-hoc app bundle signing for local runnable candidate."')
    backend_runtime_check = script.index('if ! "${BACKEND_IN_BUNDLE}" --version >/dev/null 2>&1; then')
    bundle_audit = script.index('echo "Auditing app bundle..."')

    assert skip_ad_hoc_app_sign < backend_runtime_check < bundle_audit
    assert "Skipping app bundle code-sign verification for unsigned local candidate." in script
    assert "Re-signing bundled backend after copy" in script
    assert '"${BACKEND_IN_BUNDLE}" --version >/dev/null' in script


def test_backend_binary_build_keeps_idna_codec_for_https_checks():
    script = BUILD_BACKEND.read_text(encoding="utf-8")
    wrapper = NETFIX_WRAPPER.read_text(encoding="utf-8")

    assert '--hidden-import "encodings.idna"' in script
    assert "import encodings.idna" in wrapper
