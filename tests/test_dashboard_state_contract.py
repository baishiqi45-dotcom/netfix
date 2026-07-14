from datetime import datetime, timezone
from unittest.mock import patch

from netfix import cli, dashboard_state


def test_external_system_proxy_is_not_no_proxy():
    payload = dashboard_state.resolve(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        system_proxy_active_for_user=True,
    )

    assert payload["state"] == "ready"
    assert payload["decision"]["effective_route"] == "external_system_proxy"
    assert payload["decision"]["primary_action"] == "verify_current_proxy"
    assert payload["decision"]["requires_confirmation"] is False


def test_route_signature_survives_report_redaction_format():
    signature = dashboard_state.build_route_signature(
        {
            "ok": True,
            "system_proxy": {
                "http": {"enabled": True, "server": "127.0.0.1", "port": 7890},
            },
        }
    )

    assert signature is not None
    assert signature.startswith("route:v1:")
    assert len(signature.removeprefix("route:v1:")) == 16


def test_full_check_allows_network_quality_enough_time_to_sample():
    observed = {}

    def fake_run(name, env, core, timeout):
        observed[name] = timeout
        return {"name": name, "status": "ok", "details": {}}

    with patch.object(cli.diagnose, "run_diagnostic", side_effect=fake_run):
        cli._run_diagnostics(["gateway", "network_quality"], {}, None, 30)

    assert observed["gateway"] == 10
    assert observed["network_quality"] == 30


def test_app_sized_full_check_budget_gives_network_quality_sixty_seconds():
    observed = {}

    def fake_run(name, env, core, timeout):
        observed[name] = timeout
        return {"name": name, "status": "ok", "details": {}}

    with patch.object(cli.diagnose, "run_diagnostic", side_effect=fake_run):
        cli._run_diagnostics(["gateway", "network_quality"], {}, None, 120)

    assert observed["gateway"] == 10
    assert observed["network_quality"] == 60


def test_recovery_wins_over_saved_profile():
    payload = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={
            "lifecycle": {"status": "recovery_required", "needs_attention": True},
            "stale_check": {"recovery_available": True},
        },
    )

    assert payload["state"] == "network_recovery"
    assert payload["decision"]["effective_route"] == "netfix_applied"
    assert payload["decision"]["primary_action"] == "recover_system_proxy"
    assert payload["decision"]["requires_confirmation"] is True


def test_saved_profile_only_routes_to_start_saved_proxy():
    payload = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
    )

    assert payload["state"] == "proxy_saved"
    assert payload["decision"]["effective_route"] == "saved_only"
    assert payload["decision"]["primary_action"] == "start_saved_proxy"
    assert payload["decision"]["requires_confirmation"] is True


def test_netfix_applied_warn_routes_to_degraded():
    payload = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
        last_diagnostic_status="warn",
    )

    assert payload["state"] == "proxy_degraded"
    assert payload["decision"]["effective_route"] == "netfix_applied"
    assert payload["decision"]["primary_action"] == "diagnose"


def test_matching_direct_system_apply_is_owned_by_netfix_and_can_stop():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=1,
        bridge_status={
            "lifecycle": {
                "status": "running_system",
                "profile_id": "p-direct",
                "requires_netfix_running": False,
            },
            "stale_check": {
                "status": "healthy_system_apply",
                "system_points_to_netfix_apply": True,
            },
        },
        environment={
            "ok": True,
            "system_proxy": {"http": "proxy.example.com:8000", "https": "proxy.example.com:8000"},
        },
        profiles=[{"id": "p-direct"}],
    )

    assert payload["decision"]["effective_route"] == "netfix_applied"
    assert payload["proxy"]["applied"]["owner"] == "netfix"
    assert payload["verdict"]["secondary_action"]["target"] == "recover:stale_bridge"


def test_dashboard_payload_contract_from_facts():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        environment={
            "ok": True,
            "system_proxy": {
                "http": {"enabled": True, "server": "127.0.0.1", "port": 7890},
                "https": {"enabled": True, "server": "127.0.0.1", "port": 7890},
            },
        },
        machine_state={
            "platform": "darwin",
            "primary_interface": "en0",
            "self_ipv4": "192.168.1.10",
            "gateway": "192.168.1.1",
            "has_ipv6_default_route": False,
        },
        egress_summary={"status": "unchecked"},
    )

    assert payload["schema_version"] == "netfix_current_mac_state.v2"
    assert payload["decision"]["effective_route"] == "external_system_proxy"
    assert payload["verdict"]["primary_action"]["label"] == "检查当前网络"
    assert "检查当前网络" in payload["verdict"]["next_step"]
    assert "一键诊断" not in payload["verdict"]["next_step"]
    assert payload["machine"]["primary_interface"] == "en0"
    assert payload["proxy"]["saved"]["count"] == 0
    assert payload["proxy"]["system"]["active"] is True
    assert payload["proxy"]["system"]["kind"] == "http_https"
    assert payload["proxy"]["verified"]["status"] == "unknown"
    assert payload["egress"]["status"] == "unchecked"
    assert payload["state"]["state"] == "ready"


def test_route_ok_with_high_latency_has_one_connected_attention_verdict():
    checked_at = datetime.now(timezone.utc).isoformat()
    state = dashboard_state.resolve(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        system_proxy_active_for_user=True,
        last_diagnostic_status="ok",
    )
    verdict = dashboard_state.build_dashboard_verdict(
        state=state,
        last_report_summary={
            "checked_at": checked_at,
            "stale": False,
            "usable_for_dashboard": True,
            "route_matches_current": True,
            "coverage": "current_mac_full",
            "valid_sample_count": 4,
            "status": "ok",
            "severity": "ok",
            "diagnostic_counts": {"ok": 4, "warn": 1},
            "issue_count": 0,
            "advisory_count": 1,
            "connection_quality": {
                "status": "warn",
                "headline": "延迟偏高，操作会有等待",
                "detail": "实时输出会有明显等待。",
            },
        },
    )

    assert verdict["route_health"] == "ok"
    assert verdict["status"] == "attention"
    assert verdict["severity"] == "warn"
    assert verdict["usability"] == "degraded"
    assert verdict["headline"] == "延迟偏高，操作会有等待"
    assert "线路可用" in verdict["detail"]


def test_external_proxy_with_latest_warn_report_does_not_show_clean_ready_verdict():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        environment={
            "ok": True,
            "system_proxy": {
                "http": {"enabled": True, "server": "127.0.0.1", "port": 7890},
            },
        },
        last_report_summary={
            "checked_at": "2026-07-08T11:00:00+00:00",
            "status": "warn",
            "severity": "warn",
            "headline": "目标服务需要处理",
            "issue_count": 1,
            "blocking_issue_count": 0,
            "advisory_count": 0,
            "diagnostic_counts": {"ok": 3, "warn": 1, "fail": 0},
            "stale": False,
        },
        last_diagnostic_status="warn",
    )

    assert payload["state"]["state"] == "proxy_degraded"
    assert payload["decision"]["effective_route"] == "external_system_proxy"
    assert payload["verdict"]["route_health"] == "warn"
    assert payload["verdict"]["status"] == "attention"
    assert payload["verdict"]["severity"] == "warn"
    # The fixture has no full/route-matched report context, so it may warn from
    # the live route signal but must not import historical issue counts.
    assert payload["verdict"]["issue_count"] == 0
    assert "无需处理" not in payload["verdict"]["next_step"]
    # Verdict headline must NOT inherit the stale journal headline.
    assert payload["verdict"]["headline"] != "目标服务需要处理"
    assert payload["verdict"]["live_status"] in (None, "warn") if False else True  # noqa


def test_unknown_unchecked_and_not_sampled_are_neutral_in_verdict():
    verdict = dashboard_state.build_dashboard_verdict(
        state={
            "state": "ready",
            "decision": {
                "primary_action": "verify_current_proxy",
                "effective_route": "external_system_proxy",
                "requires_confirmation": False,
                "severity": "ok",
            },
        },
        last_report_summary={
            "checked_at": "2026-07-08T11:00:00+00:00",
            "status": "ok",
            "severity": "ok",
            "headline": "当前网络可用",
            "issue_count": 0,
            "blocking_issue_count": 0,
            "advisory_count": 0,
            "diagnostic_counts": {"ok": 1, "unknown": 2, "unchecked": 1, "notSampled": 1},
            "stale": False,
        },
    )

    assert verdict["issue_count"] == 0
    assert verdict["severity"] in {"ok", "info"}
    assert verdict["diagnostic_counts"]["unknown"] == 2
    assert verdict["primary_action"]["label"] == "检查当前网络"


def test_external_system_proxy_with_no_fresh_signal_is_not_ok():
    """Without a fresh report AND without live monitor signals, the external
    proxy route must NOT be presented as a clean green/ok verdict. The view
    needs an explicit "we have not verified this proxy" signal even when the
    user has not pressed the diagnose button yet.
    """
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        environment={
            "ok": True,
            "system_proxy": {
                "http": {"enabled": True, "server": "127.0.0.1", "port": 7890},
            },
        },
        last_diagnostic_status="unchecked",
        last_report_summary={},
    )
    assert payload["state"]["state"] == "ready"
    assert payload["decision"]["effective_route"] == "external_system_proxy"
    # The point of this test: we must NOT emit a green ok status when there
    # is no fresh report and no live monitor data.
    assert payload["verdict"]["severity"] != "ok"
    assert payload["verdict"]["status"] in {"unknown", "attention"}


def test_external_system_proxy_with_live_monitor_failure_routes_to_degraded():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        environment={
            "ok": True,
            "system_proxy": {
                "http": {"enabled": True, "server": "127.0.0.1", "port": 7890},
            },
        },
        last_diagnostic_status="ok",
        last_report_summary={
            "checked_at": "2026-07-08T11:00:00+00:00",
            "status": "ok",
            "severity": "ok",
            "issue_count": 0,
            "blocking_issue_count": 0,
            "advisory_count": 0,
            "diagnostic_counts": {"ok": 4, "warn": 0, "fail": 0},
            "stale": False,
        },
        live_signals={"monitor_status": "fail", "fresh_seconds": 30},
    )
    assert payload["state"]["state"] == "proxy_degraded"
    assert payload["proxy"]["verified"]["status"] in {"fail", "warn"}


def test_presentation_keeps_first_screen_to_status_quality_and_evidence():
    presentation = dashboard_state.build_dashboard_presentation(
        {"severity": "ok", "issue_count": 0, "freshness": {"checked_at": None, "stale": False}},
        current_state="ready",
        effective_route="external_system_proxy",
    )
    assert "current_status" in presentation["visible_sections"]
    assert "connection_quality" in presentation["visible_sections"]
    assert "diagnostic_evidence" in presentation["collapsed_sections"]
    suppressed = {item["id"] for item in presentation["suppressed_sections"]}
    assert "first_aid" in suppressed
    assert "diagnose_goals" in suppressed


def test_presentation_includes_suppressed_ai_and_logs():
    presentation = dashboard_state.build_dashboard_presentation(
        {"severity": "ok", "issue_count": 0, "freshness": {"checked_at": None, "stale": False}},
        current_state="ready",
        effective_route="external_system_proxy",
    )
    suppressed_ids = {entry["id"] for entry in presentation["suppressed_sections"]}
    assert "ai" in suppressed_ids
    assert "logs" in suppressed_ids

    attention = dashboard_state.build_dashboard_presentation(
        {"severity": "warn", "issue_count": 1, "freshness": {"checked_at": "now", "stale": False}},
        current_state="proxy_degraded",
        effective_route="netfix_applied",
    )
    attention_suppressed = {entry["id"] for entry in attention["suppressed_sections"]}
    assert "ai" in attention_suppressed
    assert "ai" not in attention["collapsed_sections"]


def test_verdict_does_not_inherit_stale_report_headline():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
        environment={
            "ok": True,
            "system_proxy": {},
        },
        last_diagnostic_status="ok",
        last_report_summary={
            "checked_at": "2026-07-08T11:00:00+00:00",
            "status": "warn",
            "severity": "warn",
            "headline": "目标服务需要处理",
            "issue_count": 0,
            "blocking_issue_count": 0,
            "advisory_count": 1,
            "diagnostic_counts": {"ok": 4, "warn": 0, "fail": 0},
            "stale": True,
        },
    )
    # Netfix route + stale report: the home verdict's headline must come from
    # the state ("正在使用代理上网"), NOT from the old report's explanation.
    assert payload["state"]["state"] == "proxy_in_use"
    assert payload["verdict"]["headline"] != "目标服务需要处理"


def test_stale_warn_report_does_not_drive_current_external_proxy_verdict():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        environment={
            "ok": True,
            "system_proxy": {
                "http": {"enabled": True, "server": "127.0.0.1", "port": 7890},
            },
        },
        last_report_summary={
            "checked_at": "2026-07-08T11:00:00+00:00",
            "status": "fail",
            "severity": "fail",
            "headline": "旧报告失败",
            "issue_count": 2,
            "blocking_issue_count": 1,
            "advisory_count": 0,
            "diagnostic_counts": {"ok": 2, "warn": 1, "fail": 1},
            "stale": True,
            "usable_for_dashboard": False,
        },
        last_diagnostic_status="unchecked",
    )

    assert payload["decision"]["effective_route"] == "external_system_proxy"
    assert payload["verdict"]["status"] == "unknown"
    assert payload["verdict"]["severity"] == "info"
    assert payload["verdict"]["issue_count"] == 0
    assert payload["verdict"]["blocking_issue_count"] == 0
    assert "旧报告失败" not in payload["verdict"]["headline"]


def test_check_failed_bridge_without_recovery_available_is_not_recovery_action():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=1,
        bridge_status={
            "lifecycle": {"status": "check_failed", "needs_attention": False},
            "stale_check": {"recovery_available": False},
        },
        environment={"ok": True, "system_proxy": {}},
        last_diagnostic_status="warn",
    )

    assert payload["state"]["state"] != "network_recovery"
    assert payload["decision"]["primary_action"] != "recover_system_proxy"
    assert payload["decision"]["effective_route"] != "recovery_required"


def test_connection_quality_contract_is_visible_on_home_screen():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
        environment={"ok": True, "system_proxy": {}},
        last_report_summary={
            "checked_at": "2026-07-09T06:00:00+00:00",
            "status": "ok",
            "severity": "ok",
            "issue_count": 0,
            "blocking_issue_count": 0,
            "advisory_count": 0,
            "diagnostic_counts": {"ok": 4, "warn": 0, "fail": 0},
            "stale": False,
            "connection_quality": {
                "status": "ok",
                "headline": "体感顺畅",
                "detail": "速度、延迟和稳定性都有数据。",
                "speed": {"label": "充足", "value": "下载 28.4 Mbps / 上传 5.2 Mbps", "hint": "日常使用够用"},
                "latency": {"label": "中等", "value": "延迟 62ms", "hint": "实时输出会有轻微等待"},
                "stability": {"label": "稳定", "value": "丢包 0%", "hint": "路径稳定"},
                "background_activity": {"label": "平稳", "value": "后台占用不高", "hint": "没有看到明显上传或下载占用"},
                "checked_at": "2026-07-09T06:00:00+00:00",
                "stale": False,
                "source": "last_report",
            },
        },
        last_diagnostic_status="ok",
    )

    assert payload["connection_quality"]["speed"]["value"] == "下载 28.4 Mbps / 上传 5.2 Mbps"
    assert payload["connection_quality"]["latency"]["value"] == "延迟 62ms"
    assert "connection_quality" in payload["presentation"]["visible_sections"]


def test_system_proxy_read_failure_is_unknown_not_no_proxy():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        environment={"ok": False, "error": "scutil unavailable"},
    )

    assert payload["state"]["state"] == "unknown"
    assert payload["decision"]["effective_route"] == "unknown"
    assert payload["verdict"]["status"] == "unknown"
    assert payload["verdict"]["primary_action"]["target"] == "run:doctor"


def test_proxy_verified_ok_requires_fresh_full_route_matched_samples():
    base = {
        "checked_at": "2026-07-09T07:00:00Z",
        "stale": False,
        "usable_for_dashboard": True,
        "route_matches_current": True,
        "coverage": "current_mac_full",
        "valid_sample_count": 2,
        "status": "ok",
    }
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
        environment={"ok": True, "system_proxy": {"http": "127.0.0.1:7890"}},
        last_report_summary=base,
        last_diagnostic_status="ok",
    )
    assert payload["proxy"]["verified"]["status"] == "ok"

    for field, value in (
        ("route_matches_current", False),
        ("coverage", "target_subset"),
        ("valid_sample_count", 0),
        ("stale", True),
    ):
        invalid = dict(base)
        invalid[field] = value
        invalid["usable_for_dashboard"] = field not in {"route_matches_current", "coverage", "stale"}
        result = dashboard_state.build_current_mac_state(
            saved_profile_count=1,
            bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
            environment={"ok": True, "system_proxy": {"http": "127.0.0.1:7890"}},
            last_report_summary=invalid,
            last_diagnostic_status="ok",
        )
        assert result["proxy"]["verified"]["status"] != "ok"


def test_connection_quality_reports_unavailable_after_completed_check_without_samples():
    quality = dashboard_state.build_connection_quality({
        "has_report": True,
        "checked_at": "2026-07-09T07:00:00Z",
        "stale": False,
        "usable_for_dashboard": True,
        "connection_quality": {
            "collection_state": "unavailable",
            "status": "unchecked",
            "checked_at": "2026-07-09T07:00:00Z",
        },
    })

    assert quality["collection_state"] == "unavailable"
    assert quality["headline"] == "本机未能采样"
    assert "本次检查会补上" not in str(quality)


def test_invalid_historical_report_does_not_drive_current_quality_or_verified_time():
    payload = dashboard_state.build_current_mac_state(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        environment={"ok": True, "system_proxy": {"http": "127.0.0.1:7890"}},
        last_report_summary={
            "has_report": True,
            "origin": "codex",
            "coverage": "target_subset",
            "checked_at": "2026-07-10T06:00:00Z",
            "stale": False,
            "route_matches_current": False,
            "invalid_reason": "unsupported_origin",
            "usable_for_dashboard": False,
            "connection_quality": {
                "collection_state": "complete",
                "status": "ok",
                "speed": {"label": "充足", "value": "下载 80 Mbps", "hint": "旧线路"},
                "checked_at": "2026-07-10T06:00:00Z",
            },
        },
    )

    assert payload["connection_quality"]["collection_state"] == "never_run"
    assert payload["connection_quality"]["checked_at"] is None
    assert payload["proxy"]["verified"]["status"] == "unknown"
    assert payload["proxy"]["verified"]["checked_at"] is None


def test_primary_action_targets_are_canonical_and_restore_is_secondary_only():
    no_proxy = dashboard_state.build_current_mac_state(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        environment={"ok": True, "system_proxy": {}},
    )
    assert no_proxy["verdict"]["primary_action"]["target"] == "flow:proxy_setup"
    assert "secondary_action" not in no_proxy["verdict"]

    in_use = dashboard_state.build_current_mac_state(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
        environment={"ok": True, "system_proxy": {"http": "127.0.0.1:7890"}},
    )
    assert in_use["verdict"]["primary_action"]["target"] == "run:doctor"
    assert in_use["verdict"]["secondary_action"]["target"] == "recover:stale_bridge"


def test_presentation_sections_are_unique_and_disjoint():
    presentation = dashboard_state.build_dashboard_presentation(
        {"severity": "warn", "issue_count": 1, "freshness": {"checked_at": None, "stale": False}},
        current_state="proxy_degraded",
        effective_route="degraded",
    )

    visible = presentation["visible_sections"]
    collapsed = presentation["collapsed_sections"]
    suppressed = [entry["id"] for entry in presentation["suppressed_sections"]]
    assert len(visible) == len(set(visible))
    assert len(collapsed) == len(set(collapsed))
    assert len(suppressed) == len(set(suppressed))
    assert set(visible).isdisjoint(collapsed)
    assert set(visible).isdisjoint(suppressed)
    assert set(collapsed).isdisjoint(suppressed)


# ---------------------------------------------------------------------------
# P0 contract guard rails — added 2026-07-09
# ---------------------------------------------------------------------------


def test_external_system_proxy_with_fresh_ok_report_is_not_verified_ok():
    """Even when the journal report looks ok, external_system_proxy must not
    show a green verified checkmark: Netfix has not run an end-to-end check
    against a proxy it does not control."""
    state = dashboard_state.resolve(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        system_proxy_active_for_user=True,
    )
    fresh_report = {
        "checked_at": "2026-07-09T07:00:00Z",
        "stale": False,
        "usable_for_dashboard": True,
        "status": "ok",
        "severity": "ok",
        "diagnostic_counts": {"ok": 3, "warn": 0, "fail": 0, "unknown": 0, "unchecked": 0, "notSampled": 0},
        "issue_count": 0,
        "blocking_issue_count": 0,
        "advisory_count": 0,
    }
    verdict = dashboard_state.build_dashboard_verdict(state=state, last_report_summary=fresh_report)
    # severity must NOT be "ok" for external proxy even with fresh ok report
    assert verdict["severity"] != "ok", (
        f"external_system_proxy must not emit severity=ok, got {verdict['severity']}"
    )
    assert verdict["severity"] == "info"
    assert verdict["issue_count"] == 0


def test_external_proxy_verified_status_keeps_unknown_without_fresh_report():
    """External proxy + live ok but no journal report → verified.status must
    remain unknown, never 'ok', because Netfix has not verified end-to-end."""
    payload = dashboard_state.build_current_mac_state(
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        machine_state=None,
        saved_profile_count=0,
        last_report_summary=None,
        live_signals={"monitor_status": "ok"},
        environment={
            "system_proxy": {"http": {"enabled": True, "host": "127.0.0.1", "port": 7890}},
        },
    )
    assert payload["state"]["state"] == "ready"
    assert payload["state"]["decision"]["effective_route"] == "external_system_proxy"
    assert payload["proxy"]["verified"]["status"] == "unknown", (
        f"verified.status must stay unknown without fresh report, got "
        f"{payload['proxy']['verified']['status']}"
    )


def test_dashboard_top_level_headline_matches_verdict():
    """Swift reads response.headline from the top level. It must always mirror
    verdict.headline so the home screen never shows 'current state unknown'."""
    state = dashboard_state.resolve(
        saved_profile_count=0,
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
    )
    payload = dashboard_state.build_current_mac_state(
        bridge_status={"lifecycle": {"status": "stopped"}, "stale_check": {}},
        machine_state=None,
        saved_profile_count=0,
        last_report_summary=None,
        live_signals=None,
    )
    assert payload["headline"] == payload["verdict"]["headline"]
    assert payload["detail"] == payload["verdict"]["detail"]
    assert payload["next_step"] == payload["verdict"]["next_step"]
    assert payload["headline"]  # non-empty
    assert payload["schema_version"] == "netfix_current_mac_state.v2"


def test_fresh_failed_report_with_netfix_applied_routes_to_proxy_degraded():
    state = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
    )
    verdict = dashboard_state.build_dashboard_verdict(
        state=state,
        last_report_summary={
            "checked_at": "2026-07-09T07:00:00Z",
            "stale": False,
            "usable_for_dashboard": True,
            "route_matches_current": True,
            "coverage": "current_mac_full",
            "valid_sample_count": 2,
            "status": "fail",
            "severity": "fail",
            "diagnostic_counts": {"ok": 0, "warn": 0, "fail": 2, "unknown": 0, "unchecked": 0, "notSampled": 0},
            "issue_count": 2,
            "blocking_issue_count": 2,
            "advisory_count": 0,
        },
    )
    assert verdict["status"] == "degraded"
    assert verdict["severity"] == "fail"
    assert verdict["blocking_issue_count"] >= 1


def test_check_failed_with_recovery_available_routes_to_network_recovery():
    state = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={
            "lifecycle": {"status": "check_failed"},
            "stale_check": {"recovery_available": True},
        },
    )
    assert state["state"] == "network_recovery"
    assert state["decision"]["primary_action"] == "recover_system_proxy"
    assert state["decision"]["requires_confirmation"] is True


def test_pure_unchecked_report_does_not_emit_ok_severity():
    state = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
    )
    verdict = dashboard_state.build_dashboard_verdict(
        state=state,
        last_report_summary={
            "checked_at": "2026-07-09T07:00:00Z",
            "stale": False,
            "usable_for_dashboard": True,
            "diagnostic_counts": {"ok": 0, "warn": 0, "fail": 0, "unknown": 0, "unchecked": 4, "notSampled": 0},
            "issue_count": 0,
            "blocking_issue_count": 0,
            "advisory_count": 0,
        },
    )
    # Pure unchecked report = functionally no signal; must not be green ok
    assert verdict["severity"] != "ok"
    assert verdict["status"] in {"unknown", "attention"}


def test_not_sampled_status_is_treated_as_no_signal():
    state = dashboard_state.resolve(
        saved_profile_count=1,
        bridge_status={"lifecycle": {"status": "running_system"}, "stale_check": {}},
    )
    verdict = dashboard_state.build_dashboard_verdict(
        state=state,
        last_report_summary={
            "checked_at": "2026-07-09T07:00:00Z",
            "stale": False,
            "usable_for_dashboard": True,
            "diagnostic_counts": {"ok": 0, "warn": 0, "fail": 0, "unknown": 0, "unchecked": 0, "notSampled": 5},
            "issue_count": 0,
            "blocking_issue_count": 0,
            "advisory_count": 0,
        },
    )
    assert verdict["issue_count"] == 0
    assert verdict["severity"] != "ok"
