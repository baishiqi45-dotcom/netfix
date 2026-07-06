"""Tests for P1 network activity insights and lag timeline."""
from __future__ import annotations

from unittest.mock import patch

from netfix import network_monitor_service


def _reset_state():
    network_monitor_service.stop(persist=False)
    with network_monitor_service._LOCK:
        network_monitor_service._STATE.update({
            "running": False,
            "run_count": 0,
            "last_sample": None,
            "last_event": None,
            "last_error": None,
            "consecutive_hog_count": 0,
            "last_lag_event_at": 0.0,
        })


def _settings(whitelist=None):
    return {
        "enabled": False,
        "interval": 300,
        "lag_event_cooldown_s": 60,
        "process_whitelist": whitelist or [],
    }


def _upload_hog(label="百度网盘", process="netdisk_service.123"):
    return {
        "name": "bandwidth_hog",
        "status": "warn",
        "details": {
            "reason": "upload_saturated",
            "top_processes": [
                {
                    "process": process,
                    "label": label,
                    "direction": "upload",
                    "rate_kbps": 8000,
                    "is_hog": True,
                }
            ],
        },
    }


def test_single_hog_with_good_quality_does_not_record_lag_event():
    _reset_state()
    quality = {"status": "ok", "details": {"responsiveness_rpm": 500, "base_rtt_ms": 40}}
    with patch("netfix.network_monitor_service.settings.get_network_activity_settings", return_value=_settings()), \
         patch("netfix.network_monitor_service.bandwidth.bandwidth_hog", return_value=_upload_hog()), \
         patch("netfix.network_monitor_service._latest_network_quality", return_value=quality), \
         patch("netfix.network_monitor_service.logs.append_event") as append_event:
        result = network_monitor_service.run_once(record_event=True)

    assert result["ok"]
    assert result["activity"]["state"] == "busyUpload"
    append_event.assert_not_called()


def test_consecutive_hog_records_lag_event_even_without_bad_quality():
    _reset_state()
    quality = {"status": "ok", "details": {"responsiveness_rpm": 500, "base_rtt_ms": 40}}
    with patch("netfix.network_monitor_service.settings.get_network_activity_settings", return_value=_settings()), \
         patch("netfix.network_monitor_service.bandwidth.bandwidth_hog", return_value=_upload_hog()), \
         patch("netfix.network_monitor_service._latest_network_quality", return_value=quality), \
         patch("netfix.network_monitor_service.logs.append_event") as append_event:
        network_monitor_service.run_once(record_event=True)
        network_monitor_service.run_once(record_event=True)

    append_event.assert_called_once()
    event = append_event.call_args.args[0]
    assert event["type"] == "lag_event"
    assert event["reason_code"] == "upload_saturated"
    assert "百度网盘" in event["suspected_cause"]


def test_process_whitelist_suppresses_lag_event():
    _reset_state()
    quality = {"status": "warn", "details": {"responsiveness_rpm": 30, "base_rtt_ms": 80}}
    whitelist = [{"match": "zoom", "label": "Zoom", "enabled": True}]
    with patch("netfix.network_monitor_service.settings.get_network_activity_settings", return_value=_settings(whitelist)), \
         patch("netfix.network_monitor_service.bandwidth.bandwidth_hog", return_value=_upload_hog(label="Zoom", process="zoom.us.42")), \
         patch("netfix.network_monitor_service._latest_network_quality", return_value=quality), \
         patch("netfix.network_monitor_service.logs.append_event") as append_event:
        result = network_monitor_service.run_once(record_event=True)

    assert result["ok"]
    assert result["activity"]["state"] == "quiet"
    assert result["activity"]["top_processes"][0]["ignored"] is True
    append_event.assert_not_called()


def test_dashboard_insights_returns_compact_shape():
    _reset_state()
    with patch("netfix.network_monitor_service.run_once", return_value={"ok": True}), \
         patch("netfix.network_monitor_service.logs.load_lag_timeline", return_value={"ok": True, "events": []}), \
         patch("netfix.network_monitor_service.logs.load_proxy_health_trend", return_value={"ok": True, "samples": [], "state": "unknown"}):
        result = network_monitor_service.dashboard_insights(sample=True)

    assert result["ok"]
    assert result["network_activity"]["state"] == "notSampled"
    assert result["lag_events"] == []
    assert result["proxy_health_trend"]["state"] == "unknown"
    assert result["primary_insight"]["state"] == "notSampled"
    assert result["primary_insight"]["action"] == "开始检查"


def test_dashboard_primary_insight_prioritizes_active_upload_hog():
    _reset_state()
    activity = network_monitor_service._summarize_activity(_upload_hog(), [])
    with network_monitor_service._LOCK:
        network_monitor_service._STATE["last_sample"] = activity

    with patch("netfix.network_monitor_service.run_once", return_value={"ok": True}), \
         patch("netfix.network_monitor_service.logs.load_lag_timeline", return_value={"ok": True, "events": []}), \
         patch("netfix.network_monitor_service.logs.load_proxy_health_trend", return_value={"ok": True, "samples": [], "state": "stable"}):
        result = network_monitor_service.dashboard_insights(sample=True)

    insight = result["primary_insight"]
    assert insight["state"] == "busyUpload"
    assert insight["severity"] == "warn"
    assert "百度网盘" in insight["detail"]
    assert insight["headline"] == "检测到上行流量较高"
    assert insight["action"] == "暂停后复查"


def test_dashboard_primary_insight_uses_proxy_trend_when_activity_is_quiet():
    _reset_state()
    with network_monitor_service._LOCK:
        network_monitor_service._STATE["last_sample"] = {
            "schema_version": "netfix_network_activity.v1",
            "state": "quiet",
            "status": "ok",
            "reason": "no_significant_hog",
            "headline": "后台网络活动平稳",
            "top_processes": [],
            "privacy_note": "只看 App 名称、上传/下载方向和粗略速度；不看网址、远端 IP 或内容。",
            "sampled_at": "2026-07-06T00:00:00Z",
        }

    trend = {"ok": True, "samples": [{"status": "fail", "error": "auth failed"}], "state": "authFailing"}
    with patch("netfix.network_monitor_service.run_once", return_value={"ok": True}), \
         patch("netfix.network_monitor_service.logs.load_lag_timeline", return_value={"ok": True, "events": []}), \
         patch("netfix.network_monitor_service.logs.load_proxy_health_trend", return_value=trend):
        result = network_monitor_service.dashboard_insights(sample=True)

    insight = result["primary_insight"]
    assert insight["state"] == "authFailing"
    assert insight["headline"] == "代理账号需要确认"
    assert insight["action"] == "检查代理账号"
