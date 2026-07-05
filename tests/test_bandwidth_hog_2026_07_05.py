"""Tests for the bandwidth-hog layer diagnostic (P0-C, 2026-07-05)."""
from __future__ import annotations

import sys
import unittest
import unittest.mock as mock
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from netfix.layers import bandwidth
from netfix import diagnose
from netfix.cli import _LAYER_DIAGNOSTICS
from netfix import reasoner, explain


def _make_row(process: str, tx_bytes: int, rx_bytes: int = 0) -> Dict[str, Any]:
    return {"process": process, "tx_bytes": tx_bytes, "rx_bytes": rx_bytes}


class TestAggregateAndClassify(unittest.TestCase):
    def test_aggregation_sums_per_process(self):
        agg = bandwidth._aggregate_by_process([
            _make_row("BaiduNetdisk", 1000),
            _make_row("BaiduNetdisk", 2000),
        ])
        self.assertEqual(agg["BaiduNetdisk"]["tx_bytes"], 3000)

    def test_classify_upload_vs_download(self):
        self.assertEqual(bandwidth._classify_process("BaiduNetdisk"), "upload")
        self.assertEqual(bandwidth._classify_process("OneDrive"), "upload")
        self.assertEqual(bandwidth._classify_process("qBittorrent"), "download")
        self.assertEqual(bandwidth._classify_process("QQMusic"), "download")
        self.assertEqual(bandwidth._classify_process("Docker"), "upload")


class TestHogExtraction(unittest.TestCase):
    def test_diagnostic_is_registered_and_in_doctor_suite(self):
        self.assertIn("bandwidth_hog", _LAYER_DIAGNOSTICS)
        with mock.patch.object(bandwidth, "_sample_nettop", return_value=([], None)):
            result = diagnose.run_diagnostic("bandwidth_hog", {}, None, timeout=2)
        self.assertEqual(result["name"], "bandwidth_hog")
        self.assertNotEqual(result["status"], "error")

    def test_nettop_parser_uses_delta_sample_not_initial_cumulative(self):
        stdout = """
,bytes_in,bytes_out,
xray.111,70000000,70000000,
netdisk_service.222,0,9000000,
,bytes_in,bytes_out,
xray.111,1000,1000,
netdisk_service.222,0,250000,
"""
        rows = bandwidth._parse_nettop_table(stdout)
        by_process = {row["process"]: row for row in rows}
        self.assertEqual(by_process["xray.111"]["tx_bytes"], 1000)
        self.assertEqual(by_process["netdisk_service.222"]["tx_bytes"], 250000)

    def test_upload_hog_above_threshold(self):
        # 8 Mbps sustained upload → 8000 kbps
        agg = {
            "BaiduNetdisk": {"rx_bytes": 0, "tx_bytes": 1_000_000},
            "Docker": {"rx_bytes": 0, "tx_bytes": 50_000},
        }
        candidates = bandwidth._candidate_hogs(agg)
        flagged = [c for c in candidates if c["is_hog"]]
        self.assertTrue(any(c["label"] == "百度网盘" and c["direction"] == "upload" for c in flagged))

    def test_low_traffic_is_not_a_hog(self):
        agg = {"BaiduNetdisk": {"rx_bytes": 0, "tx_bytes": 5_000}}
        candidates = bandwidth._candidate_hogs(agg)
        self.assertFalse(any(c["is_hog"] for c in candidates))

    def test_download_hog_is_flagged(self):
        # 30 Mbps sustained download
        agg = {"qBittorrent": {"rx_bytes": 3_750_000, "tx_bytes": 0}}
        candidates = bandwidth._candidate_hogs(agg)
        flagged = [c for c in candidates if c["is_hog"]]
        self.assertTrue(any(c["label"] == "qBittorrent" for c in flagged))


class TestSummarize(unittest.TestCase):
    def test_upload_saturated_returns_red_headline(self):
        agg = {"BaiduNetdisk": {"rx_bytes": 0, "tx_bytes": 1_000_000}}
        candidates = bandwidth._candidate_hogs(agg)
        summary = bandwidth._summarize(candidates[: bandwidth._MAX_HOGS])
        self.assertEqual(summary["reason"], "upload_saturated")
        self.assertIn("后台上传", summary["headline"])
        # The friendly label should also be in the next_step text.
        self.assertIn("OneDrive", summary["next_step"])  # default fallback hint

    def test_no_hog_returns_friendly_message(self):
        summary = bandwidth._summarize([])
        self.assertEqual(summary["reason"], "no_significant_hog")


class TestReasonerPreference(unittest.TestCase):
    def test_upload_congestion_outranks_ipv6(self):
        diagnostics = [
            {
                "name": "network_quality",
                "status": "warn",
                "details": {"responsiveness_rpm": 30, "base_rtt_ms": 80},
            },
            {
                "name": "bandwidth_hog",
                "status": "warn",
                "details": {
                    "reason": "upload_saturated",
                    "top_processes": [
                        {"label": "百度网盘", "direction": "upload", "is_hog": True, "rate_kbps": 8000}
                    ],
                },
            },
            {
                "name": "ipv6_leak",
                "status": "warn",
                "details": {"leak_confirmed": True},
            },
        ]
        causes = reasoner.reason({}, diagnostics)
        ids = [c["id"] for c in causes]
        self.assertIn("upload-congestion", ids)
        self.assertIn("ipv6-exposed", ids)
        self.assertLess(ids.index("upload-congestion"), ids.index("ipv6-exposed"))

    def test_standalone_hog_still_reported(self):
        diagnostics = [
            {
                "name": "bandwidth_hog",
                "status": "warn",
                "details": {
                    "reason": "upload_saturated",
                    "top_processes": [
                        {"label": "OneDrive", "direction": "upload", "is_hog": True, "rate_kbps": 3000}
                    ],
                },
            },
        ]
        causes = reasoner.reason({}, diagnostics)
        ids = [c["id"] for c in causes]
        self.assertIn("bandwidth-hog-detected", ids)


class TestExplainUploadCongestion(unittest.TestCase):
    def test_explain_translates_upload_congestion(self):
        report = {
            "diagnostics": [],
            "root_causes": [
                {
                    "id": "upload-congestion",
                    "description": "网络被后台上传挤满",
                    "confidence": 0.95,
                    "manual_steps": ["暂停百度网盘上传"],
                }
            ],
            "fixes": [],
            "manual_steps": [],
        }
        result = explain.explain_report(report, rules={"fixes": {}})
        # The friendly explanation should call out network is being squeezed by background sync/uploaders.
        self.assertIn("网盘", result["explanation"])
        self.assertIn("实时应用", result["explanation"])
        # The user-provided manual step should appear in manual_steps.
        all_manual_text = " ".join(
            step.get("description", "") if isinstance(step, dict) else str(step)
            for step in result["manual_steps"]
        )
        self.assertIn("百度网盘", all_manual_text)
        self.assertEqual(result["headline"], "不是断网，是后台上传把网络挤满了")


class TestBandwidthDiagnosticOnNonDarwin(unittest.TestCase):
    def test_unknown_status_when_sampler_unavailable(self, monkeypatch=None):
        with mock.patch.object(bandwidth, "_sample_nettop", return_value=(None, "nettop_unavailable")):
            diagnostic = bandwidth.bandwidth_hog({}, None, timeout=2)
        self.assertEqual(diagnostic["status"], "unknown")
        self.assertEqual(diagnostic["details"]["reason"], "nettop_unavailable")
        self.assertEqual(diagnostic["details"]["sampler"], "nettop")


if __name__ == "__main__":
    unittest.main()
