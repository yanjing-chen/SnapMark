#!/usr/bin/env bash
# BUILD MACHINE: Code01-Ver2-0 or GitHub Actions x86_64.
# Builds a standalone Flatpak bundle. Does not install it or touch user Runtime.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ "$(uname -m)" == x86_64 ]] || { echo 'C3_FLATPAK_REQUIRES_X86_64' >&2; exit 1; }
for tool in flatpak flatpak-builder; do
  command -v "$tool" >/dev/null || { echo "Install $tool separately before building" >&2; exit 1; }
done
# Installing GNOME Platform/SDK is explicit, not an implicit script side effect.
flatpak info org.gnome.Platform//50 >/dev/null || { echo 'Missing org.gnome.Platform//50 (flatpak install flathub org.gnome.Platform//50)' >&2; exit 1; }
flatpak info org.gnome.Sdk//50 >/dev/null || { echo 'Missing org.gnome.Sdk//50 (flatpak install flathub org.gnome.Sdk//50)' >&2; exit 1; }
python3 scripts/check-base-package.py snapmark
python3 -m unittest discover -s tests -q
mkdir -p dist build
flatpak-builder --force-clean --repo="$ROOT/build/c3-flatpak-repo" \
  "$ROOT/build/c3-flatpak" "$ROOT/flatpak/io.github.yanjingchen.SnapMark.yml"
flatpak build-bundle "$ROOT/build/c3-flatpak-repo" \
  "$ROOT/dist/SnapMark-x86_64.flatpak" io.github.yanjingchen.SnapMark stable
[[ -s "$ROOT/dist/SnapMark-x86_64.flatpak" ]] || exit 1
sha256sum "$ROOT/dist/SnapMark-x86_64.flatpak" > "$ROOT/dist/SnapMark-x86_64.flatpak.sha256"
echo 'C3_FLATPAK_BUNDLE_BUILT=PASS'
echo 'C3_FLATPAK_NO_INSTALL=YES'
