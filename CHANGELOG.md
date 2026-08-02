# Changelog

All notable changes are documented here. The project uses semantic versioning from
version 1.0.0 onward.

## Unreleased

- Harden manual catalog downloads with an HTTPS source allowlist, protected XML
  parsing and bounded decompression of XLSX members.
- Rename the visible product to Open MC3000 Control, with OMC as its compact and
  installed-app name, while retaining compatible service, package and data paths.
- Add a local cell catalog with explicitly manual imports from BetterBat/Zenodo,
  Second Life Storage and Lygte, per-source status and failure-safe refreshes.
- Add local model search and deliberate catalog-to-record field transfer without
  changing charger programs, protection flags or hardware state.
- Extend battery records and PDF sheets with weight, voltage range, current limits,
  cycle life, dimensions, technical notes, preserved source fields and source URLs.

## 1.0.0 - 2026-08-01

- Stable multi-charger BLE control, profiles, battery records, program history, charts,
  reports, backups and optional authentication.
- Read-only interactive demo with representative sample data.
- German and English web interface plus English project documentation.
- Portable JSON import and export for profile libraries.
- Anonymized diagnostics bundle without databases or personal device metadata.
- Installable progressive web app with an offline application shell; API and control
  responses are never cached.
- Automated tests for Python 3.11 through 3.13, JavaScript, shell scripts and packaging.
- Security headers, WebSocket origin checking, login rate limiting and bounded imports.
