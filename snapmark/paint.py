"""Paint screenshot and vector overlays in source pixel coordinates."""
import math
import cairo
from gi.repository import Gdk, Pango, PangoCairo


def hex_rgba(color: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    color = color.lstrip('#')
    return tuple(int(color[i:i+2], 16) / 255 for i in (0, 2, 4)) + (alpha,)


def paint_mark(cr: cairo.Context, m) -> None:
    cr.save()
    cr.set_source_rgba(*hex_rgba(m.color))
    cr.set_line_width(m.width)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    x, y, dx, dy = m.x1, m.y1, m.x2 - m.x1, m.y2 - m.y1
    if m.tool in ('line', 'arrow'):
        cr.move_to(x, y)
        cr.line_to(m.x2, m.y2)
        cr.stroke()
        if m.tool == 'arrow':
            angle = math.atan2(dy, dx)
            length = max(12.0, m.width * 4.0)
            for offset in (-0.52, 0.52):
                cr.move_to(m.x2, m.y2)
                cr.line_to(m.x2 - length * math.cos(angle + offset),
                           m.y2 - length * math.sin(angle + offset))
                cr.stroke()
    elif m.tool == 'rectangle':
        cr.rectangle(min(x, m.x2), min(y, m.y2), abs(dx), abs(dy))
        fill_or_stroke(cr, m)
    elif m.tool == 'ellipse':
        cr.translate((x + m.x2)/2, (y + m.y2)/2)
        cr.scale(max(abs(dx)/2, .01), max(abs(dy)/2, .01))
        cr.arc(0, 0, 1, 0, math.tau)
        cr.restore()
        cr.save()
        cr.set_source_rgba(*hex_rgba(m.color))
        cr.set_line_width(m.width)
        # A Cairo path remains in untransformed coordinates after restore.
        fill_or_stroke(cr, m)
    elif m.tool == 'pen' and m.points:
        cr.move_to(*m.points[0])
        for point in m.points[1:]:
            cr.line_to(*point)
        cr.stroke()
    elif m.tool == 'text' and m.text:
        layout = PangoCairo.create_layout(cr)
        layout.set_text(m.text, -1)
        font = Pango.FontDescription.from_string(f'Sans {max(10, int(m.width * 5))}')
        layout.set_font_description(font)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)
    cr.restore()


def fill_or_stroke(cr: cairo.Context, mark) -> None:
    if mark.fill:
        cr.save()
        cr.set_source_rgba(*hex_rgba(mark.color, mark.opacity))
        cr.fill_preserve()
        cr.restore()
    cr.stroke()


def paint_document(cr: cairo.Context, pixbuf, marks, preview=None) -> None:
    # Source pixels are never resized or modified while editing.
    Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
    cr.paint()
    for mark in marks:
        paint_mark(cr, mark)
    if preview is not None:
        paint_mark(cr, preview)
