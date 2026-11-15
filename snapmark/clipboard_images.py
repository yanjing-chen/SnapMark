"""Lightweight, image-only clipboard MIME metadata detection.

This module does not read clipboard payloads. GDK changed events may represent
text, HTML, URLs, or images. Only an advertised image format can initiate an
asynchronous image read. No timer, GNOME extension or persistent history.
"""


def clipboard_image_state(formats, texture_gtype=None):
    """Return 'image', 'empty' (briefly transitioning), or 'other'.

    An actual image MIME type is required across process boundaries; a GDK
    Texture GType supports in-process texture clipboard providers. Text/HTML
    that merely embeds an image URL is not an actual clipboard image.
    """
    if formats is None:
        return 'empty'
    if texture_gtype is not None and formats.contain_gtype(texture_gtype):
        return 'image'
    mimes = formats.get_mime_types() or ()
    if any(str(mime).lower().startswith('image/') for mime in mimes):
        return 'image'
    # Works with GTK 4.14 bundled fallback as well as newer system GTK.
    if not mimes and not (formats.get_gtypes() or ()):
        return 'empty'
    return 'other'


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE_BYTES = 32 * 1024 * 1024
IMAGE_MIME_PRIORITY = ('image/png', 'image/jpeg', 'image/webp', 'image/tiff',
                       'image/bmp', 'image/gif', 'image/avif')


def image_mime_types(formats) -> tuple:
    """Real image MIME types advertised by the clipboard, best first.

    Clipboard-history extensions read the advertised mimetypes and request
    that stream directly instead of assuming a single toolkit-native texture
    conversion. This is the same negotiation step, using GDK's format list.
    """
    if formats is None:
        return ()
    try:
        mimes = [str(mime).lower() for mime in (formats.get_mime_types() or ())]
    except (AttributeError, TypeError, ValueError):
        return ()
    images = {mime for mime in mimes if mime.startswith('image/')}
    ordered = [mime for mime in IMAGE_MIME_PRIORITY if mime in images]
    ordered.extend(sorted(images.difference(ordered)))
    return tuple(ordered)


def image_to_png(data: bytes):
    """Normalize clipboard image bytes to a bounded PNG for ScreenshotSession."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None
    if data.startswith(PNG_MAGIC):
        return data
    try:
        import gi
        gi.require_version('Gdk', '4.0')
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import Gdk, GdkPixbuf, Gio
        stream = Gio.MemoryInputStream.new_from_data(data, None)
        pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
        if pixbuf is None:
            return None
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        png = bytes(texture.save_to_png_bytes().get_data())
        return png if png.startswith(PNG_MAGIC) and len(png) <= MAX_IMAGE_BYTES else None
    except Exception:
        return None
