import ssl

from app.scraper import _TTIPAB_INTERMEDIATE_CERT, _ttipab_ssl_context


def test_ttipab_tls_context_verifies_certificates_and_hostname():
    context = _ttipab_ssl_context()

    assert _TTIPAB_INTERMEDIATE_CERT.is_file()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
