# Version 1.0 security review

The 1.0 release is checked with automated tests and a manual review of the boundaries
that can affect a charger, private data or the host system.

Automated release checks include:

- the full Python test suite with simulated BLE clients and temporary databases;
- Python bytecode compilation, Ruff, Bandit and JavaScript syntax checks;
- dependency vulnerability scanning with `pip-audit`;
- package build and clean virtual-environment installation;
- shell syntax checks and desktop/mobile Chromium smoke tests;
- profile import size/count/validation tests and diagnostics privacy tests.

Bandit's generic SQL-string rule (`B608`) is excluded after manual review. The flagged
queries interpolate only fixed column lists, placeholder counts or clauses selected by
the application; external values continue to use SQLite parameters. This exclusion does
not permit user-provided SQL identifiers or fragments.

Security controls in the application include same-origin WebSockets, optional scrypt
authentication, rate limiting, HttpOnly/SameSite cookies, restrictive browser headers,
bounded imports, output escaping, anonymized diagnostics and a systemd service account
with filesystem sandboxing. The PWA service worker never caches API, authentication or
charger-control responses.

Remaining deployment boundary: the default service listens on the local network over
HTTP so other household/workshop devices can reach it. It must not be forwarded directly
to the internet. Use the built-in login plus HTTPS or a trusted VPN across untrusted
networks.
