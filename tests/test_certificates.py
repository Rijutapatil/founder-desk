"""Pinned intermediate certificates.

Some government hosts serve only their leaf certificate and omit the
intermediate, so a normal trust store cannot build the chain. The response is to
supply the missing link, never to lower the bar - so these tests exist to prove
the bar was not lowered.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sources.loader import CERT_DIR, load_allowlist

cryptography = pytest.importorskip("cryptography")
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives.serialization import Encoding  # noqa: E402

# Committed fingerprint. A substituted certificate fails the build rather than
# being trusted silently - which is the entire point of pinning it.
EXPECTED = {
    "globalsign-gcc-r6-alphassl-ca-2025.pem": (
        "a883559231f8388daf35ce41c8101040ae8fd9b656434247b9475af592cc08ca"
    ),
}


def _certs():
    return [e for e in load_allowlist().entries if e.ca_bundle]


def test_verify_false_appears_nowhere_in_the_ingest_path() -> None:
    """The rule this whole mechanism exists to avoid breaking.

    Disabling certificate verification would collect these sources in one line.
    It is refused because a tampered response would then be indistinguishable
    from a real one, and this text is quoted as law.
    """
    import ast
    import pathlib

    # Parsed, not grepped: a substring search matches this module's own prose
    # about not doing it, which would make the test pass or fail for the wrong
    # reason. The AST sees only real keyword arguments.
    for path in pathlib.Path("ingest").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "verify":
                    continue
                assert not (
                    isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                ), f"{path}:{node.lineno} disables TLS verification"


def test_every_pinned_certificate_matches_its_fingerprint() -> None:
    import hashlib

    for entry in _certs():
        path = entry.ca_bundle_path
        assert path is not None and path.exists()
        cert = x509.load_pem_x509_certificate(path.read_bytes())
        digest = hashlib.sha256(cert.public_bytes(encoding=Encoding.DER)).hexdigest()
        assert digest == EXPECTED[entry.ca_bundle], f"{entry.ca_bundle} does not match its pin"


def test_pinned_certificates_are_intermediates_not_self_signed() -> None:
    """An intermediate chains up to a root in the normal trust store.

    A self-signed certificate here would mean the chain terminates at something
    this repo supplied, which is trust-on-first-use rather than verification.
    """
    for entry in _certs():
        cert = x509.load_pem_x509_certificate(entry.ca_bundle_path.read_bytes())  # type: ignore[union-attr]
        assert cert.issuer != cert.subject, f"{entry.ca_bundle} is self-signed"
        assert "GlobalSign Root" in cert.issuer.rfc4514_string()


def test_pinned_certificates_are_not_close_to_expiry() -> None:
    """Fails 90 days ahead, so the rotation is scheduled rather than discovered."""
    for entry in _certs():
        cert = x509.load_pem_x509_certificate(entry.ca_bundle_path.read_bytes())  # type: ignore[union-attr]
        remaining = cert.not_valid_after_utc - datetime.now(UTC)
        assert remaining > timedelta(days=90), (
            f"{entry.ca_bundle} expires {cert.not_valid_after_utc:%Y-%m-%d}; rotate it"
        )


def test_a_missing_certificate_file_is_a_validation_error() -> None:
    from agent.schema import AuthorityTier
    from sources.loader import SourceEntry

    with pytest.raises(ValueError, match="not found"):
        SourceEntry(
            id="x",
            publisher="P",
            title="T",
            url="https://esic.gov.in/x",
            authority_tier=AuthorityTier.GUIDANCE,
            license="GODL-India",
            refresh_days=30,
            ca_bundle="does-not-exist.pem",
        )


def test_certificates_directory_holds_only_what_is_referenced() -> None:
    referenced = {e.ca_bundle for e in _certs()}
    on_disk = {p.name for p in CERT_DIR.glob("*.pem")}
    assert on_disk == referenced, f"unreferenced certificates: {on_disk - referenced}"
