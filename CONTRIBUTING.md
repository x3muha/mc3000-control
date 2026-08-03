# Contributing

Contributions, protocol observations and compatibility reports are welcome.

1. Open an issue for changes that affect BLE writes, profile validation, storage
   migrations or the public API.
2. Create a focused branch and keep unrelated changes separate.
3. Install the development dependencies with `python -m pip install -e '.[test]'`.
4. Run `python -m pytest -q`, the JavaScript syntax checks from
   [tests/README.md](tests/README.md), and `bash -n install.sh deploy/*.sh`.
5. Describe the tested MC3000 hardware/firmware and Linux/BlueZ version in the pull
   request. Never post Bluetooth addresses, serial numbers, passwords, databases or
   battery notes.
6. Keep user-facing documentation and interface text in sync in German and English.
   Update the matching `.md` files or translation keys together in the same change.
7. When dependencies change, install `.[audit]`, regenerate
   `THIRD_PARTY_NOTICES.md` with `python scripts/third_party_notices.py --write`,
   and verify it with `--check` before opening the pull request.

Tests use temporary databases and simulated BLE clients. Hardware testing must be
explicit, supervised and performed with suitable cells and safe charger settings.

By submitting a contribution, you agree that it is licensed under the project's MIT
license.
