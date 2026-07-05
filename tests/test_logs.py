import json
import tempfile
from pathlib import Path

from netfix import logs


def test_append_event_redacts_secrets_before_persisting():
    original_events = logs.EVENTS_FILE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            logs.EVENTS_FILE = Path(tmp) / "events.jsonl"
            secret_url = "http://user:demo-password@proxy.example.com:8000"
            result = logs.append_event(
                {
                    "type": "proxy_monitor",
                    "stderr": f"failed {secret_url} sk-live-secret-token-1234567890abc",
                    "_secret": {"password": "demo-password"},
                },
                apply_retention=False,
            )

            text = logs.EVENTS_FILE.read_text(encoding="utf-8")
            encoded = json.dumps(result, ensure_ascii=False)
            assert result["ok"]
            assert "demo-password" not in text
            assert "demo-password" not in encoded
            assert "sk-live-secret-token" not in text
            assert "sk-live-secret-token" not in encoded
            assert "stderr" not in text
    finally:
        logs.EVENTS_FILE = original_events


def test_load_events_redacts_legacy_plaintext_events():
    original_events = logs.EVENTS_FILE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            logs.EVENTS_FILE = Path(tmp) / "events.jsonl"
            secret_url = "http://user:demo-password@proxy.example.com:8000"
            logs.EVENTS_FILE.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-07-01T00:00:00+00:00",
                        "type": "legacy",
                        "message": f"failed {secret_url} sk-live-secret-token-1234567890abc",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = logs.load_events(hours=None)
            encoded = json.dumps(result, ensure_ascii=False)
            assert "demo-password" not in encoded
            assert "sk-live-secret-token" not in encoded
            assert "user:***@" in encoded
    finally:
        logs.EVENTS_FILE = original_events


def test_proxy_health_trend_strips_urls_from_legacy_events():
    original_events = logs.EVENTS_FILE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            logs.EVENTS_FILE = Path(tmp) / "events.jsonl"
            logs.EVENTS_FILE.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-07-01T00:00:00+00:00",
                        "type": "proxy_monitor",
                        "status": "ok",
                        "proxy_check": {
                            "profile_id": "p1",
                            "status": "ok",
                            "auth": "not_required",
                            "target": "https://www.gstatic.com/generate_204",
                            "checked_via": "http://proxy.example.com:8000",
                            "latency_ms": 120,
                            "http_code": 204,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = logs.load_proxy_health_trend(limit=10)
            encoded = json.dumps(result, ensure_ascii=False)
            assert result["ok"]
            assert result["samples"][0]["latency_ms"] == 120
            assert "gstatic" not in encoded
            assert "proxy.example.com" not in encoded
            assert "checked_via" not in encoded
            assert "target" not in encoded
    finally:
        logs.EVENTS_FILE = original_events


def test_proxy_health_trend_categorizes_error_without_host_leak():
    original_events = logs.EVENTS_FILE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            logs.EVENTS_FILE = Path(tmp) / "events.jsonl"
            logs.EVENTS_FILE.write_text(
                json.dumps(
                    {
                        "timestamp": "2026-07-01T00:00:00+00:00",
                        "type": "proxy_monitor",
                        "status": "fail",
                        "proxy_check": {
                            "profile_id": "p1",
                            "status": "fail",
                            "error": "connect to proxy.example.com:8000 timed out",
                            "latency_ms": 0,
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = logs.load_proxy_health_trend(limit=10)
            encoded = json.dumps(result, ensure_ascii=False)
            assert result["ok"]
            assert result["samples"][0]["error"] == "timeout"
            assert "proxy.example.com" not in encoded
            assert "8000" not in encoded
    finally:
        logs.EVENTS_FILE = original_events
