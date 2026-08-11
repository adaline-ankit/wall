# Security notes

## Dependency audit

The release gate uses `pip-audit` against the project dependency graph.

```bash
pip-audit . --ignore-vuln PYSEC-2026-3552
```

As of 2026-08-11, `cryptography` 49.0.0 is the newest stable PyPI release. The audit reports
`PYSEC-2026-3552`, a PKCS#7 RSA-decryption oracle fixed only in the unreleased 50.0.0 line. Wall
does not import or call any PKCS#7, RSA, certificate, or S/MIME API; encrypted sync uses only
`Scrypt` and `AESGCM`. The vulnerable path is therefore unreachable in Wall. This exception should
be removed as soon as cryptography 50 reaches a stable PyPI release, and reviewed no later than
2026-09-30.

No other known vulnerabilities were reported in the resolved production dependency graph.

## Local dashboard boundary

The dashboard has no authentication and binds to loopback by default. `wall serve` refuses a
non-loopback host unless the operator passes `--allow-network`; that flag is an acknowledgement, not
an access-control layer. Use an authenticated reverse proxy and transport encryption for any shared
deployment. API responses carry a restrictive content security policy, anti-framing, MIME-sniffing,
referrer, permissions, and no-store headers.
