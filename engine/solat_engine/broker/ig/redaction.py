"""
Redaction utilities for IG API interactions.

Ensures sensitive data (tokens, credentials) never appears in logs or API responses.
"""

import re
from typing import Any

# Patterns that indicate sensitive headers
SENSITIVE_HEADER_PATTERNS = {
    "cst",
    "x-security-token",
    "authorization",
    "x-ig-api-key",
}

# Patterns that indicate sensitive body fields
SENSITIVE_BODY_PATTERNS = {
    "password",
    "identifier",
    "apikey",
    "api_key",
    "token",
    "secret",
    "credential",
}

# Redaction placeholder
REDACTED = "[REDACTED]"


def is_sensitive_header(header_name: str) -> bool:
    """Check if a header name is sensitive."""
    lower_name = header_name.lower()
    return any(pattern in lower_name for pattern in SENSITIVE_HEADER_PATTERNS)


def is_sensitive_field(field_name: str) -> bool:
    """Check if a field name is sensitive."""
    lower_name = field_name.lower()
    return any(pattern in lower_name for pattern in SENSITIVE_BODY_PATTERNS)


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """
    Redact sensitive values from headers dict.

    Args:
        headers: Original headers dict

    Returns:
        New dict with sensitive values replaced by [REDACTED]
    """
    return {
        k: REDACTED if is_sensitive_header(k) else v
        for k, v in headers.items()
    }


def redact_dict(data: dict[str, Any], depth: int = 0) -> dict[str, Any]:
    """
    Recursively redact sensitive values from a dict.

    Args:
        data: Original dict
        depth: Current recursion depth (to prevent infinite recursion)

    Returns:
        New dict with sensitive values replaced by [REDACTED]
    """
    if depth > 10:
        return data

    result: dict[str, Any] = {}
    for key, value in data.items():
        if is_sensitive_field(key):
            result[key] = REDACTED
        elif isinstance(value, dict):
            result[key] = redact_dict(value, depth + 1)
        elif isinstance(value, list):
            result[key] = [
                redact_dict(item, depth + 1) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def redact_url(url: str) -> str:
    """
    Redact any credentials that might be in a URL.

    Args:
        url: Original URL

    Returns:
        URL with any embedded credentials redacted
    """
    # Pattern to match credentials in URLs like http://user:pass@host
    pattern = r"(https?://)([^:]+):([^@]+)@"
    return re.sub(pattern, rf"\1{REDACTED}:{REDACTED}@", url)


def safe_log_request(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a safe-to-log representation of an HTTP request.

    Args:
        method: HTTP method
        url: Request URL
        headers: Request headers
        body: Request body

    Returns:
        Dict safe for logging
    """
    return {
        "method": method,
        "url": redact_url(url),
        "headers": redact_headers(headers) if headers else None,
        "body": redact_dict(body) if body else None,
    }


def safe_log_response(
    status_code: int,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a safe-to-log representation of an HTTP response.

    Args:
        status_code: Response status code
        headers: Response headers
        body: Response body

    Returns:
        Dict safe for logging
    """
    return {
        "status_code": status_code,
        "headers": redact_headers(headers) if headers else None,
        "body": redact_dict(body) if body else None,
    }
