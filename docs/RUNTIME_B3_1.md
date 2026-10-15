# SnapMark B3-1 — Runtime 1.0.0 preflight (read-only)

**Code01 (Ryzen 7 6800H), base: v0.6.0-B2-C2 after model-query fix.**

- Detects expected user-installed launcher, Python service and systemd unit **by existence only**.
- Existing Runtime remains active and unchanged. Unreachable /health does not imply uninstalled.
- Only after clicking **Check 1.0.0**, queries official GitHub release **metadata** using HTTPS GET, pinned to `local-ai-runtime-v1.0.0`.
- Compares the installed service's reported `runtime_version` with 1.0.0 when both are strict release versions.
- Lists whether metadata is available and whether an update appears possible. **It does not verify archives, download them, install, upgrade, stop/start, rollback, uninstall or change a model.**
- Official release source commit: `cb10db5f8bb1bf0590c245001e268d1f7cc60fa0`; later main commits need not match it.
- The release is not treated as verified merely because GitHub reports assets; B3-2 must match archive checksums and validate an isolated upgrade and rollback before enabling any action.
- Broken network, GitHub HTTP errors or API rate limits only update the preflight status; SnapMark's existing Runtime connection and OCR settings continue working.

Testing: `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -q`.
B3-1 should be validated on Code01 GNOME Wayland with Runtime 0.8.0 **left running**.
