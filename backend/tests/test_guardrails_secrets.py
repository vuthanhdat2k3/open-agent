from app.core.guardrails.secrets import REDACTION, scan_and_redact


def test_secret_scanner_redacts_aws_key_and_jwt() -> None:
    aws_key = "AKIA1234567890ABCDEF"
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    clean, findings = scan_and_redact(f"aws={aws_key} token={jwt}")

    assert aws_key not in clean
    assert jwt not in clean
    assert clean.count(REDACTION) >= 2
    assert {f.kind for f in findings} >= {"aws_access_key", "jwt"}


def test_secret_scanner_redacts_generic_api_key_value() -> None:
    secret = "sk_live_abcdefghijklmnopqrstuvwxyz123456"
    clean, findings = scan_and_redact(f"api_key={secret}")

    assert secret not in clean
    assert REDACTION in clean
    assert findings

