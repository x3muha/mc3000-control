# Security policy

Security reports should be submitted through a private
[GitHub security advisory](https://github.com/x3muha/mc3000-control/security/advisories/new).
Do not include credentials, database files, backups, Bluetooth addresses, device serial
numbers or private battery notes in a public issue.

The current major release receives security fixes. Reports should include the affected
version, impact, reproducible steps and an anonymized diagnostics bundle where useful.
Please allow reasonable time for investigation before public disclosure.

MC3000 Control is intended for a trusted local network. Do not expose its HTTP service
directly to the internet. Use the built-in login together with HTTPS or a trusted VPN
when traffic crosses an untrusted network.
