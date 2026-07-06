import Foundation

/// Compact, privacy-preserving data used by the home screen.
/// Backed by GET /dashboard/insights.
struct DashboardInsightsResponse: Codable {
    let ok: Bool?
    let primaryInsight: DashboardPrimaryInsight?
    let networkActivity: NetworkActivitySummary?
    let lagEvents: [LagEventSummary]
    let proxyHealthTrend: ProxyHealthTrend?
    let monitor: NetworkActivityMonitorState?

    enum CodingKeys: String, CodingKey {
        case ok
        case primaryInsight = "primary_insight"
        case networkActivity = "network_activity"
        case lagEvents = "lag_events"
        case proxyHealthTrend = "proxy_health_trend"
        case monitor
    }
}

struct DashboardPrimaryInsight: Codable {
    let state: String?
    let severity: String?
    let headline: String?
    let detail: String?
    let action: String?
}

struct NetworkActivityMonitorState: Codable {
    let running: Bool?
    let interval: Int?
    let lastSampleAt: String?

    enum CodingKeys: String, CodingKey {
        case running
        case interval
        case lastSampleAt = "last_sample_at"
    }
}

struct NetworkActivitySummary: Codable {
    let state: String?
    let headline: String?
    let detail: String?
    let topProcesses: [NetworkActivityProcess]
    let privacyNote: String?
    let sampledAt: String?

    enum CodingKeys: String, CodingKey {
        case state
        case headline
        case detail
        case topProcesses = "top_processes"
        case privacyNote = "privacy_note"
        case sampledAt = "sampled_at"
    }
}

struct NetworkActivityProcess: Codable, Identifiable {
    let process: String?
    let label: String?
    let direction: String?
    let rateKbps: Double?
    let rateBucket: String?
    let ignored: Bool?

    enum CodingKeys: String, CodingKey {
        case process
        case label
        case direction
        case rateKbps = "rate_kbps"
        case rateBucket = "rate_bucket"
        case ignored
    }

    var id: String {
        [process, label, direction].compactMap { $0 }.joined(separator: "|")
    }

    var displayName: String {
        let raw = (label?.isEmpty == false ? label : process) ?? "未知 App"
        return raw.isEmpty ? "未知 App" : raw
    }
}

struct LagEventSummary: Codable, Identifiable {
    let id: String?
    let timestamp: String?
    let headline: String?
    let suspectedCause: String?
    let evidence: LagEventEvidence?

    enum CodingKeys: String, CodingKey {
        case id
        case timestamp
        case headline
        case suspectedCause = "suspected_cause"
        case evidence
    }

    var stableID: String {
        id ?? [timestamp, headline, suspectedCause].compactMap { $0 }.joined(separator: "|")
    }
}

struct LagEventEvidence: Codable {
    let responsivenessRPM: Int?
    let baseRTTMs: Int?
    let topProcesses: [NetworkActivityProcess]?

    enum CodingKeys: String, CodingKey {
        case responsivenessRPM = "responsiveness_rpm"
        case baseRTTMs = "base_rtt_ms"
        case topProcesses = "top_processes"
    }
}

struct ProxyHealthTrend: Codable {
    let samples: [ProxyHealthSample]
    let okCount: Int?
    let warnCount: Int?
    let failCount: Int?
    let medianLatencyMs: Int?
    let profileId: String?

    enum CodingKeys: String, CodingKey {
        case samples
        case okCount = "ok_count"
        case warnCount = "warn_count"
        case failCount = "fail_count"
        case medianLatencyMs = "median_latency_ms"
        case profileId = "profile_id"
    }
}

struct ProxyHealthSample: Codable, Identifiable {
    let timestamp: String?
    let status: String?
    let latencyMs: Int?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case timestamp
        case status
        case latencyMs = "latency_ms"
        case error
    }

    var id: String {
        [timestamp, status, error].compactMap { $0 }.joined(separator: "|")
    }
}

struct NetworkActivitySettingsResponse: Codable {
    let ok: Bool?
    let settings: NetworkActivitySettings
}

struct NetworkActivitySettingsSaveResponse: Codable {
    let ok: Bool?
    let settings: NetworkActivitySettings
}

struct NetworkActivitySettings: Codable {
    let enabled: Bool
    let interval: Int
    let lagEventCooldownSeconds: Int?
    let processWhitelist: [NetworkActivityIgnoreRule]
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case enabled
        case interval
        case lagEventCooldownSeconds = "lag_event_cooldown_s"
        case processWhitelist = "process_whitelist"
        case updatedAt = "updated_at"
    }
}

struct NetworkActivityIgnoreRule: Codable, Identifiable, Equatable {
    var match: String
    var label: String?
    var reason: String?
    var enabled: Bool?

    var id: String { match }

    var displayLabel: String {
        if let label, !label.isEmpty { return label }
        return match
    }

    func apiBody() -> [String: Any] {
        [
            "match": match,
            "label": label ?? match,
            "reason": reason ?? "user_ignored",
            "enabled": enabled ?? true,
        ]
    }
}
