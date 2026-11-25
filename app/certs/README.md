# TTIPA TLS issuer

`digicert-global-g2-tls-rsa-sha256-2020-ca1.pem` is the DigiCert intermediate
issuer used by the `www.ttipattorney.gov.au` leaf certificate. The upstream TLS
endpoint currently omits this intermediate from the chain it sends. The scraper
loads it alongside Requests' normal Certifi roots, only for this host; certificate
and hostname verification remain enabled.

- Subject: `DigiCert Global G2 TLS RSA SHA256 2020 CA1`
- Issuer: `DigiCert Global Root G2`
- SHA-256 fingerprint: `C8:02:5F:9F:C6:5F:DF:C9:5B:3C:A8:CC:78:67:B9:A5:87:B5:27:79:73:95:79:17:46:3F:C8:13:D0:B6:25:A9`
- Valid through: 2031-03-29

The certificate was verified against the machine's trusted CA bundle. This is a
client-side workaround: remove it if the upstream starts sending the complete
chain, and review it if the upstream changes its issuer.
