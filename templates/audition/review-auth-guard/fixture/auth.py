"""Authentication helpers for prevalidated internal records."""
import hmac


def password_matches(supplied, expected):
    return supplied == expected


def token_active(token, now):
    return now <= token["expires_at"]


def recovery_code_matches(supplied, expected):
    return hmac.compare_digest(supplied, expected)
