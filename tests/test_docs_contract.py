import re
from pathlib import Path

from netfix.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]


def _read_docs(*names: str) -> str:
    return "\n".join((ROOT / name).read_text(encoding="utf-8") for name in names)


def test_documented_cli_aliases_are_real_parser_commands():
    parser = build_parser()

    assert parser.parse_args(["check", "--json"]).command == "triage"
    assert parser.parse_args(["full-check", "--json"]).command == "doctor"
    args = parser.parse_args(["guide", "--query", "MTU"])
    assert args.command == "kb"
    assert args.query == "MTU"


def test_public_docs_do_not_advertise_removed_llm_cli_or_wrong_http_paths():
    text = _read_docs("AGENTS.md", "docs/developer/interfaces.md")

    assert "explain --provider" not in text
    assert "/llm/explain" not in text
    assert "POST /llm/providers" not in text
    assert "GET /llm/providers" in text
    assert "POST /explain_llm" in text
    assert "POST /settings/llm" in text


def test_readme_openings_only_promise_the_p0_proxy_flow():
    zh = (ROOT / "README.md").read_text(encoding="utf-8").split("\n## ", 1)[0]
    en = (ROOT / "README.en.md").read_text(encoding="utf-8").split("\n## ", 1)[0]

    for term in ["已有", "HTTP", "SOCKS", "粘贴", "验证", "启用", "停止", "恢复"]:
        assert term in zh
    for term in ["existing", "HTTP", "SOCKS", "paste", "verify", "enable", "stop", "restore"]:
        assert term.lower() in en.lower()
    for forbidden in ["Codex", "ChatGPT", "诊断", "AI", "重启"]:
        assert forbidden not in zh
    for forbidden in ["Codex", "ChatGPT", "diagnos", "restart"]:
        assert forbidden.lower() not in en.lower()
    assert not re.search(r"\bAI\b", en)


def test_readmes_keep_developer_interfaces_and_removed_promises_out_of_user_docs():
    zh = (ROOT / "README.md").read_text(encoding="utf-8")
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    combined = zh + "\n" + en

    for forbidden in ["python3 netfix", "GET /health", "POST /run", "MCP", "codex mcp"]:
        assert forbidden not in combined
    assert "一键诊断" not in zh
    assert "one-click diagnosis" not in en.lower()
    assert "重启 Mac" not in zh
    assert "restart your Mac" not in en.lower()
    assert "docs/developer/interfaces.md" in zh
    assert "docs/developer/interfaces.md" in en


def test_developer_interfaces_are_documented_below_the_readmes():
    text = (ROOT / "docs" / "developer" / "interfaces.md").read_text(encoding="utf-8")

    for required in [
        "## CLI",
        "python3 netfix.py codex --json",
        "## HTTP API",
        "GET /health",
        "POST /run",
        "## MCP",
        "python3 -m netfix.mcp_server",
    ]:
        assert required in text


def test_p0_release_candidate_contract_is_synced_across_owner_docs():
    zh = (ROOT / "README.md").read_text(encoding="utf-8")
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    matrix = (ROOT / "docs" / "developer" / "capability-matrix.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "未签名、未公证" in zh
    assert "not Developer ID signed and not notarized" in en
    for text in [matrix, agents]:
        for required in [
            "netfix-backend",
            "pyproject.toml",
            "git_sha",
            "dirty",
            "source_fingerprint",
            "backend_sha256",
            "app_executable_sha256",
            "build_id",
            "built_at",
            "version",
        ]:
            assert required in text
    assert "one-click diagnosis" not in matrix.lower()
    assert "一键诊断" not in matrix


def test_capability_matrix_uses_v2_schema():
    text = (ROOT / "docs" / "developer" / "capability-matrix.md").read_text(encoding="utf-8")
    assert "netfix_current_mac_state.v2" in text
    # The stale v1 string must not appear; if a new version is shipped, the
    # test must be updated in lock-step.
    assert "netfix_current_mac_state.v1" not in text


def test_agents_doc_lists_all_confirmation_phrases():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    required = [
        "APPLY_SYSTEM_FIX",
        "TEST_LLM_PROVIDER",
        "TEST_LLM_CHAIN",
        "APPLY_PROXY_PROFILE",
        "ROLLBACK_PROXY_PROFILE",
        "RESTORE_STALE_PROXY_BRIDGE",
        "RESTART_STALE_PROXY_BRIDGE",
        "IMPORT_DEEPSEEK_SIDECAR_KEY",
        "DELETE_NETFIX_LOCAL_DATA",
    ]
    missing = [phrase for phrase in required if phrase not in text]
    assert not missing, f"AGENTS.md confirmation table missing: {missing}"
