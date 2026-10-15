"""OCR region geometry in original pixels, independent of the zoom or annotations.

The pure geometry function is exercised in offline tests; GI/Cairo is only
imported when original pixels are serialized on the GTK main loop.
"""
from __future__ import annotations

import io
import math


def normalize_region(bounds, width, height):
    """Clip arbitrary drag corners to the source image; reject empty drags."""
    if (len(bounds) != 4 or not all(isinstance(v, (float, int)) and
                                   math.isfinite(v) for v in bounds)
            or type(width) is not int or type(height) is not int
            or width < 1 or height < 1):
        raise ValueError('Invalid OCR region geometry')
    a, b, c, d = bounds
    x0, x1 = max(0, math.floor(min(a, c))), min(width, math.ceil(max(a, c)))
    y0, y1 = max(0, math.floor(min(b, d))), min(height, math.ceil(max(b, d)))
    if x1 - x0 < 2 or y1 - y0 < 2:
        raise ValueError('OCR region must be at least 2 × 2 original pixels')
    return x0, y0, x1, y1


def original_pixbuf_png(pixbuf, region=None):
    """Serialize original screenshot pixels only; never render annotation marks."""
    import cairo
    from gi.repository import Gdk
    width, height = pixbuf.get_width(), pixbuf.get_height()
    if region is None:
        x0, y0, x1, y1 = 0, 0, width, height
    else:
        x0, y0, x1, y1 = normalize_region(region, width, height)
    cr_surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, x1-x0, y1-y0)
    ctx = cairo.Context(cr_surface)
    # The offset is in source pixels and is unaffected by screen zoom.
    Gdk.cairo_set_source_pixbuf(ctx, pixbuf, -x0, -y0)
    ctx.paint()
    output = io.BytesIO()
    cr_surface.write_to_png(output)
    cr_surface.finish()
    return output.getvalue()
