# Clipboard image monitoring (1.1.2)

- Remains native GTK4/GDK, no Shell extension and no additional service.
- `GdkClipboard.changed` fires for owner changes, including text. SnapMark
  checks **metadata only** (`get_formats`) then returns for text, URLs and
  `text/html`; no text-read method is ever called.
- When format metadata advertises `image/*` or a GDK Texture object, SnapMark
  asynchronously reads the texture, reencodes to a bounded PNG in memory,
  and refreshes the existing 0–3600 s quick action lifetime. Image clipboard
  owners may offer PNG, JPEG, TIFF, WebP, etc.; unsupported conversions are
  ignored. Images embedded as HTML without actual image MIME are not decoded.
- There is **no timer-based clipboard polling**. Empty/transitioning content
  receives at most two short (~180 ms) metadata rechecks after a changed event.
- The screenshot folder watcher and the validated GNOME 51 single-tray
  registration are unchanged. Enabling/disabling clipboard monitoring does not
  change screenshot-file detection.
- Copying an image only enables the existing tray shortcut. Clicking opens the
  editor, **not** OCR; OCR requires a second explicit click and uses local Ollama.
- Clipboard images are not persisted as screenshot history. The user can save
  the image in the editor if desired.
- GNOME clipboard history extensions demonstrate event-driven owner changes,
  but this code independently uses documented GTK4 APIs; no external extension
  source code is imported.

## Hand-on validation on GNOME 51 / Wayland

1. Launch after logout or after quitting an older SnapMark; tray must show
   exactly one icon, and quick action must begin disabled.
2. Copy an actual image from a webpage (right-click -> Copy Image). Tray action
   activates and opens editor; screenshot pixels remain unannotated.
3. Click OCR explicitly and confirm local Ollama result.
4. Copy text and a link; no new image should be read, no automatic OCR.
5. Wait for quick-action expiry, then copy a fresh image: it reactivates.
6. Disable the image monitor in Preferences. A new copied image should NOT
   enable an expired shortcut; GNOME screenshots saved in monitored folders
   must continue working.
7. Re-enable. Copy a new image to reactivate.
8. Restart and ensure no old clipboard image activates the shortcut.

## Reconciliation update (clipboard-fix patch)

`GdkClipboard.changed` remains the passive notification path, but it is no
longer the only way the quick action can become usable. Following the pattern
used by GNOME clipboard-history extensions (an owner-change event is a hint;
the real state comes from reading advertised mimetypes and requesting the
stream), the application now reconciles on explicit, user-triggered points:

- once ~350 ms after startup, once ~150 ms after a window is presented;
- when the tray menu opens (`AboutToShow` / `AboutToShowGroup`);
- when the quick action is clicked.

A second read path uses `Gdk.Clipboard.read_async(mime_types)` →
`read_finish()` → chunked `Gio.InputStream.read_bytes_async()`, so
`image/jpeg`, `image/webp`, TIFF, etc. payloads no longer depend on GDK
converting them to a single Texture. Payloads are normalized to a bounded PNG,
de-duplicated by SHA-256, then cached and signalled to the dbusmenu host.

There is still **no background timer polling**: rechecks only happen after one
of the explicit events above, at most two short (~180 ms) retries each.
Text, HTML, URI lists and copied-file lists are still never read.

The tray quick action is intentionally always clickable. On Wayland a
background client cannot know whether the clipboard holds an image, so a grey
item is wrong more often than not. Clicking acquires focus (which makes Mutter
deliver the pending selection offer), probes, and loads the image into the
editor window that was just presented. See `CLIPBOARD-ANALYSIS-AND-FIX.md`
for the full rationale and the remaining Wayland limitation.
