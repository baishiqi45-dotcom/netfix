"""Report redaction before logs, LLM prompts, and exports."""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import re
from typing import Any, Dict, Iterable, Tuple
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


RAW_DROP_KEYS = {
    "raw",
    "stdout",
    "stderr",
    "traceback",
    "technical",
    "command",
    "commands",
}

SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "subscription",
    "credential",
)

PROFILE_HOST_KEYS = {"address", "host", "hostname", "server", "url", "pac_url"}
URL_RE = re.compile(r"\b(?:https?|socks5h?)://[^\s'\"<>]+", re.IGNORECASE)
IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_\-]{24,}\b")
SECRET_WORD_RE = re.compile(
    r"\b[A-Za-z0-9_.:\-]*(?:password|passwd|secret|token|api[_-]?key)[A-Za-z0-9_.:\-]*\b",
    re.IGNORECASE,
)
NON_SECRET_TOKEN_WORD_RE = re.compile(r"^(?:max_.*tokens?|.*tokens?_field|.*completion_tokens?)$", re.IGNORECASE)


def _hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:length]


def _audit_inc(audit: Dict[str, int], key: str, amount: int = 1) -> None:
    audit[key] = audit.get(key, 0) + amount


def _path_contains(path: Tuple[str, ...], names: Iterable[str]) -> bool:
    needles = set(names)
    return any(part in needles for part in path)


def _redact_ip(match: re.Match[str], audit: Dict[str, int]) -> str:
    value = match.group(0)
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return value
    _audit_inc(audit, "ip")
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return "private_ipv4" if ip.version == 4 else "private_ipv6"
    return f"public_ipv{ip.version}_hash:{_hash(value)}"


def _redact_url(value: str, audit: Dict[str, int]) -> str:
    try:
        parsed = urlsplit(value)
    except Exception:
        return value
    if not parsed.scheme or not parsed.netloc:
        return value

    username = parsed.username
    password = parsed.password
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = parsed.netloc
    if username is not None or password is not None:
        _audit_inc(audit, "secret")
        user = quote(username or "user", safe="")
        netloc = f"{user}:***@{hostname}{port}"

    query_pairs = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=True):
        if any(part in key.lower() for part in SECRET_KEY_PARTS):
            _audit_inc(audit, "secret")
            query_pairs.append((key, "[redacted_secret]"))
        else:
            query_pairs.append((key, item))
    query = urlencode(query_pairs, doseq=True)
    return urlunsplit((parsed.scheme, netloc, parsed.path, query, ""))


def _redact_string(value: str, audit: Dict[str, int]) -> str:
    out = URL_RE.sub(lambda m: _redact_url(m.group(0), audit), value)
    if out == value:
        out = _redact_url(value, audit)
    def _secret_word(match: re.Match[str]) -> str:
        word = match.group(0)
        if NON_SECRET_TOKEN_WORD_RE.match(word):
            return word
        _audit_inc(audit, "secret")
        return "[redacted_secret]"

    out = SECRET_WORD_RE.sub(_secret_word, out)
    out = IP_RE.sub(lambda m: _redact_ip(m, audit), out)
    if EMAIL_RE.search(out):
        _audit_inc(audit, "email", len(EMAIL_RE.findall(out)))
        out = EMAIL_RE.sub("[redacted_email]", out)
    if UUID_RE.search(out):
        _audit_inc(audit, "uuid", len(UUID_RE.findall(out)))
        out = UUID_RE.sub("[redacted_uuid]", out)

    def _long_token(match: re.Match[str]) -> str:
        token = match.group(0)
        if token.startswith("public_ipv"):
            return token
        _audit_inc(audit, "secret")
        return f"token_hash:{_hash(token, 8)}"

    return LONG_TOKEN_RE.sub(_long_token, out)


def redact_text(value: str) -> str:
    """Redact secrets from a standalone text snippet."""
    audit: Dict[str, int] = {}
    return _redact_string(str(value), audit)


def _redact_value(value: Any, audit: Dict[str, int], path: Tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in value.items():
            key_l = str(key).lower()
            child_path = path + (key_l,)
            if key_l == "hostname" and path == ("meta",):
                _audit_inc(audit, "hostname")
                continue
            if key_l in RAW_DROP_KEYS:
                _audit_inc(audit, "raw_output")
                continue
            if any(part in key_l for part in SECRET_KEY_PARTS):
                _audit_inc(audit, "secret")
                out[key] = "[redacted_secret]"
                continue
            if key_l in PROFILE_HOST_KEYS and _path_contains(path, {"profiles", "active_profile"}):
                _audit_inc(audit, "profile_host")
                out[key] = f"profile_value_hash:{_hash(str(item))}"
                continue
            out[key] = _redact_value(item, audit, child_path)
        return out
    if isinstance(value, list):
        return [_redact_value(item, audit, path) for item in value]
    if isinstance(value, str):
        return _redact_string(value, audit)
    return value


def redact_report(report: Dict[str, Any], level: str = "balanced") -> Dict[str, Any]:
    """Return a redacted report and an audit summary."""
    audit: Dict[str, int] = {}
    source = copy.deepcopy(report)
    redacted = _redact_value(source, audit, ())
    if level == "strict":
        env = redacted.get("environment")
        if isinstance(env, dict):
            if "profiles" in env:
                _audit_inc(audit, "strict_profiles")
                env["profiles"] = []
            if "active_profile" in env:
                _audit_inc(audit, "strict_profiles")
                env["active_profile"] = None
    payload = json.dumps(redacted, ensure_ascii=False, sort_keys=True, default=str)
    return {
        "redacted_report": redacted,
        "redaction_audit": audit,
        "redacted_report_hash": _hash(payload, 16),
    }
