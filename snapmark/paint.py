"""Non-destructive Cairo rendering at original image-pixel coordinates."""
import math
import cairo
import gi
# The paint module is imported directly by tests and plug-in callers. Register
# the PyCairo foreign type here rather than relying on app.py import order.
gi.require_version('Gdk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
gi.require_foreign('cairo')
from gi.repository import Gdk, GdkPixbuf, GLib, Pango, PangoCairo
from .filters import box_blur_bytes


def hex_rgba(color: str, alpha: float = 1.) -> tuple[float, float, float, float]:
    color = color.lstrip('#')
    return tuple(int(color[i:i+2], 16) / 255 for i in (0, 2, 4)) + (alpha,)


def fill_or_stroke(cr, mark):
    if mark.fill:
        cr.save()
        cr.set_source_rgba(*hex_rgba(mark.fill_color or mark.color, mark.opacity))
        cr.fill_preserve()
        cr.restore()
    cr.stroke()


def rounded_rectangle_path(cr, x, y, w, h, radius):
    """Build one path used for both filling and stroking (image coordinates)."""
    r = max(0., min(float(radius), abs(w) / 2., abs(h) / 2.))
    if r <= 0:
        cr.rectangle(x, y, w, h)
        return
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def rounded_triangle_path(cr, vertices, radius):
    """True circular tangential corners on a clockwise three-vertex path.

    The uniform radius is clamped so tangent points on every side never cross.
    Cairo image-space coordinates have y increasing downwards.
    """
    vertices = tuple((float(x), float(y)) for x, y in vertices)
    requested = max(0., float(radius))
    if requested <= 0:
        cr.move_to(*vertices[0])
        for vertex in vertices[1:]:
            cr.line_to(*vertex)
        cr.close_path()
        return
    directions, factors = [], []
    for i, (x, y) in enumerate(vertices):
        px, py = vertices[(i - 1) % 3]
        nx, ny = vertices[(i + 1) % 3]
        a, b = (px - x, py - y), (nx - x, ny - y)
        la, lb = math.hypot(*a), math.hypot(*b)
        if min(la, lb) < 1e-6:
            rounded_triangle_path(cr, vertices, 0)
            return
        a, b = (a[0]/la, a[1]/la), (b[0]/lb, b[1]/lb)
        cosine = max(-1., min(1., a[0]*b[0] + a[1]*b[1]))
        theta = math.acos(cosine)
        if theta < 1e-5 or abs(math.pi - theta) < 1e-5:
            rounded_triangle_path(cr, vertices, 0)
            return
        directions.append((a,b,theta))
        factors.append(1. / math.tan(theta / 2.))
    r = requested
    for i in range(3):
        x,y=vertices[i]; nx,ny=vertices[(i+1)%3]
        edge=math.hypot(nx-x,ny-y)
        r=min(r, max(0., edge / (factors[i]+factors[(i+1)%3])))
    if r < 1e-5:
        rounded_triangle_path(cr, vertices, 0)
        return
    corners=[]
    for i,(x,y) in enumerate(vertices):
        a,b,theta = directions[i]
        tangent = r * factors[i]
        entry=(x+a[0]*tangent,y+a[1]*tangent)
        exit=(x+b[0]*tangent,y+b[1]*tangent)
        bx,by=a[0]+b[0], a[1]+b[1]
        mag=math.hypot(bx,by)
        distance=r/math.sin(theta/2.)
        cx,cy=x+bx/mag*distance,y+by/mag*distance
        corners.append((entry,exit,(cx,cy)))
    cr.new_sub_path()
    cr.move_to(*corners[0][1])
    for i in (1,2,0):
        entry,exit,center=corners[i]
        cr.line_to(*entry)
        a1=math.atan2(entry[1]-center[1], entry[0]-center[0])
        a2=math.atan2(exit[1]-center[1], exit[0]-center[0])
        cr.arc(center[0],center[1],r,a1,a2)
    cr.close_path()


def _mosaic(cr, m, pixbuf):
    if pixbuf is None:
        return
    image_width, image_height = pixbuf.get_width(), pixbuf.get_height()
    x1 = max(0, min(image_width, math.floor(min(m.x1, m.x2))))
    y1 = max(0, min(image_height, math.floor(min(m.y1, m.y2))))
    x2 = max(0, min(image_width, math.ceil(max(m.x1, m.x2))))
    y2 = max(0, min(image_height, math.ceil(max(m.y1, m.y2))))
    width, height = x2 - x1, y2 - y1
    if width < 2 or height < 2:
        return
    # Shrink to a coarse image, then scale via Cairo NEAREST to retain blocks.
    block = max(6, round(m.width * 3))
    tiny_width, tiny_height = max(1, math.ceil(width / block)), max(1, math.ceil(height / block))
    cropped = pixbuf.new_subpixbuf(x1, y1, width, height)
    small = cropped.scale_simple(tiny_width, tiny_height, GdkPixbuf.InterpType.NEAREST)
    cr.save()
    cr.translate(x1, y1)
    cr.scale(width / tiny_width, height / tiny_height)
    Gdk.cairo_set_source_pixbuf(cr, small, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_NEAREST)
    cr.rectangle(0, 0, tiny_width, tiny_height)
    cr.clip()
    cr.paint_with_alpha(max(0., min(1., m.opacity)))
    cr.restore()


def _blur(cr, mark, pixbuf):
    if pixbuf is None:
        return
    iw, ih = pixbuf.get_width(), pixbuf.get_height()
    x0 = max(0, min(iw, math.floor(min(mark.x1, mark.x2))))
    y0 = max(0, min(ih, math.floor(min(mark.y1, mark.y2))))
    x1 = max(0, min(iw, math.ceil(max(mark.x1, mark.x2))))
    y1 = max(0, min(ih, math.ceil(max(mark.y1, mark.y2))))
    w, h = x1 - x0, y1 - y0
    if w < 2 or h < 2:
        return
    cropped = pixbuf.new_subpixbuf(x0, y0, w, h)
    channels = cropped.get_n_channels()
    raw = cropped.get_pixels()
    stride = cropped.get_rowstride()
    packed = b''.join(raw[y * stride:y * stride + w * channels] for y in range(h))
    # Width slider doubles as blur radius. The operation is non-destructive.
    blurred = box_blur_bytes(packed, w, h, channels, max(3, round(mark.width * 2)))
    blurred_pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
        GLib.Bytes.new(blurred), GdkPixbuf.Colorspace.RGB,
        cropped.get_has_alpha(), 8, w, h, w * channels)
    cr.save()
    Gdk.cairo_set_source_pixbuf(cr, blurred_pixbuf, x0, y0)
    cr.rectangle(x0, y0, w, h)
    cr.clip()
    cr.paint_with_alpha(max(0., min(1., mark.opacity)))
    cr.restore()


def paint_mark(cr, m, pixbuf=None):
    if m.tool == 'mosaic':
        _mosaic(cr, m, pixbuf)
        return
    if m.tool == 'blur':
        _blur(cr, m, pixbuf)
        return
    if m.tool == 'eraser':
        if not m.points:
            return
        cr.save()
        # CLEAR is permitted ONLY on the transparent annotation group.
        # paint_document() never calls this on the original screenshot.
        cr.set_operator(cairo.OPERATOR_CLEAR)
        cr.set_line_width(max(2., m.width))
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(*m.points[0])
        for point in m.points[1:]:
            cr.line_to(*point)
        if len(m.points) == 1:
            x, y = m.points[0]
            cr.arc(x, y, max(1., m.width / 2.), 0, math.tau)
            cr.fill()
        else:
            cr.stroke()
        cr.restore()
        return
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
            length = max(12., m.width * 4.)
            for offset in (-.52, .52):
                cr.move_to(m.x2, m.y2)
                cr.line_to(m.x2 - length * math.cos(angle + offset),
                           m.y2 - length * math.sin(angle + offset))
                cr.stroke()
    elif m.tool == 'rectangle':
        rounded_rectangle_path(cr, min(x, m.x2), min(y, m.y2),
                               abs(dx), abs(dy), getattr(m, 'corner_radius', 0))
        fill_or_stroke(cr, m)
    elif m.tool == 'triangle':
        left, right = sorted((x, m.x2))
        top, bottom = sorted((y, m.y2))
        rounded_triangle_path(cr, (((left + right) / 2, top),
                               (right, bottom), (left, bottom)),
                              getattr(m, 'corner_radius', 0))
        fill_or_stroke(cr, m)
    elif m.tool == 'ellipse':
        cr.translate((x + m.x2) / 2, (y + m.y2) / 2)
        cr.scale(max(abs(dx) / 2, .01), max(abs(dy) / 2, .01))
        cr.arc(0, 0, 1, 0, math.tau)
        cr.restore()
        cr.save()
        cr.set_source_rgba(*hex_rgba(m.color))
        cr.set_line_width(m.width)
        fill_or_stroke(cr, m)
    elif m.tool in ('pen', 'highlighter') and m.points:
        if m.tool == 'highlighter':
            # Draw the complete stroke to an intermediate group so overlapping
            # segments don't cause darker self-intersections.
            cr.push_group()
            cr.set_source_rgba(*hex_rgba(m.color))
            cr.set_line_width(max(12, m.width * 5))
        cr.move_to(*m.points[0])
        for point in m.points[1:]:
            cr.line_to(*point)
        cr.stroke()
        if m.tool == 'highlighter':
            cr.pop_group_to_source()
            cr.paint_with_alpha(max(0., min(1., m.opacity)))
    elif m.tool == 'text' and m.text:
        layout = PangoCairo.create_layout(cr)
        layout.set_text(m.text, -1)
        layout.set_font_description(Pango.FontDescription.from_string(m.font or 'Sans 20'))
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)
    cr.restore()


def paint_document(cr, pixbuf, marks, preview=None):
    """Composite original pixels independently from annotations.

    The eraser only affects the transparent annotation group. It can never
    clear source screenshot pixels, in on-screen previews or PNG exports.
    Mosaic/blur are base-image operations and remain outside the eraser mask.
    """
    Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
    cr.paint()
    sequence = list(marks)
    if preview is not None:
        sequence.append(preview)
    for mark in sequence:
        if mark.tool in ('mosaic', 'blur'):
            paint_mark(cr, mark, pixbuf)
    cr.push_group()
    for mark in sequence:
        if mark.tool not in ('mosaic', 'blur'):
            paint_mark(cr, mark, pixbuf)
    cr.pop_group_to_source()
    cr.paint()
