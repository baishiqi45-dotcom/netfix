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
