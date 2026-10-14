"""Image-space, non-destructive annotations; no GTK or Cairo dependency.

Each layer is one Mark. History snapshots are DEEP copies: editing a Mark in
place would otherwise retroactively change undo and redo snapshots.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from math import hypot, sqrt
import unicodedata


@dataclass
class Mark:
    tool: str
    x1: float
    y1: float
    x2: float
    y2: float
    color: str = '#e82c20'
    width: float = 4.0
    fill: bool = False
    opacity: float = 0.25
    text: str = ''
    points: list[tuple[float, float]] = field(default_factory=list)
    font: str = 'Sans 20'
    fill_color: str = ''

    def is_meaningful(self):
        if self.tool == 'text':
            return bool(self.text.strip())
        if self.tool in ('pen', 'highlighter'):
            return len(self.points) > 1
        return hypot(self.x2 - self.x1, self.y2 - self.y1) >= 2


def _distance_to_segment(x, y, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    length2 = vx * vx + vy * vy
    f = max(0., min(1., ((x - ax) * vx + (y - ay) * vy) / length2)) if length2 else 0.
    return hypot(x - (ax + f * vx), y - (ay + f * vy))


def font_size(mark):
    try:
        return max(5., float(mark.font.rsplit(' ', 1)[-1]))
    except (ValueError, IndexError):
        return 20.


def mark_bounds(mark):
    """Approximate image-space hit/handle bounds; text uses glyph estimates.

    Text metrics in pixels depend on font rendering; margin around bounds
    leaves useful handles even when an unusual font is chosen.
    """
    if mark.tool in ('pen', 'highlighter') and mark.points:
        xs, ys = zip(*mark.points)
        padding = max(mark.width * (2.5 if mark.tool == 'highlighter' else .5), 2.)
        return min(xs) - padding, min(ys) - padding, max(xs) + padding, max(ys) + padding
    if mark.tool == 'text':
        size = font_size(mark)
        units = sum(1.0 if unicodedata.east_asian_width(char) in 'WF' else .59
                    for char in mark.text)
        return mark.x1, mark.y1, mark.x1 + max(size, units * size), mark.y1 + size * 1.55
    return (min(mark.x1, mark.x2), min(mark.y1, mark.y2),
            max(mark.x1, mark.x2), max(mark.y1, mark.y2))


def mark_touches(mark, x, y, radius=12.):
    """Hit-test a visible mark, with a modest tolerance for strokes."""
    if mark.tool in ('pen', 'highlighter'):
        pts = mark.points
        width = mark.width * (5 if mark.tool == 'highlighter' else 1)
        return any(_distance_to_segment(x, y, *a, *b) <= radius + width / 2
                   for a, b in zip(pts, pts[1:]))
    if mark.tool in ('line', 'arrow'):
        return _distance_to_segment(x, y, mark.x1, mark.y1,
                                    mark.x2, mark.y2) <= radius + mark.width / 2
    left, top, right, bottom = mark_bounds(mark)
    if not (left - radius <= x <= right + radius and top - radius <= y <= bottom + radius):
        return False
    if mark.tool in ('text', 'mosaic', 'blur') or mark.fill:
        return True
    if mark.tool == 'rectangle':
        return min(abs(x - left), abs(x - right), abs(y - top), abs(y - bottom)) <= radius + mark.width
    if mark.tool == 'ellipse':
        cx, cy = (left + right) / 2, (top + bottom) / 2
        rx, ry = max((right - left) / 2, 1), max((bottom - top) / 2, 1)
        return abs(((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 - 1) < max(.18, radius / min(rx, ry))
    if mark.tool == 'triangle':
        a = ((left + right) / 2, top)
        b, c = (left, bottom), (right, bottom)
        return min(_distance_to_segment(x, y, *p, *q)
                   for p, q in ((a, b), (b, c), (c, a))) <= radius + mark.width
    return False


def translated(mark, dx, dy):
    """Return a translated copy, leaving the original/undo snapshot intact."""
    result = deepcopy(mark)
    result.x1 += dx
    result.x2 += dx
    result.y1 += dy
    result.y2 += dy
    if result.points:
        result.points = [(x + dx, y + dy) for x, y in result.points]
    return result


def resized(mark, new_bounds):
    """Affine-transform an annotation into a new bounding rectangle.

    Stroke coordinates are transformed, including pen/highlighter sample points;
    fonts scale to approximate the geometric resize on text annotations.
    """
    x0, y0, x1, y1 = mark_bounds(mark)
    nx0, ny0, nx1, ny1 = new_bounds
    if nx1 <= nx0 or ny1 <= ny0:
        return deepcopy(mark)
    ow, oh = max(x1 - x0, .001), max(y1 - y0, .001)
    sx, sy = (nx1 - nx0) / ow, (ny1 - ny0) / oh

    def tx(x):
        return nx0 + (x - x0) * sx

    def ty(y):
        return ny0 + (y - y0) * sy

    result = deepcopy(mark)
    result.x1, result.x2 = tx(mark.x1), tx(mark.x2)
    result.y1, result.y2 = ty(mark.y1), ty(mark.y2)
    if mark.points:
        result.points = [(tx(x), ty(y)) for x, y in mark.points]
    if mark.tool == 'text':
        size = max(5., min(300., font_size(mark) * sqrt(sx * sy)))
        family = mark.font.rsplit(' ', 1)[0]
        result.font = f'{family} {size:.1f}'
    return result


class History:
    def __init__(self):
        self.marks = []
        self._undo = []
        self.redo_stack = []
        self._batch_start = None

    def _snapshot(self):
        return deepcopy(self.marks)

    def _record(self):
        if self._batch_start is None:
            self._undo.append(self._snapshot())
            self.redo_stack.clear()

    def push(self, mark):
        if not mark.is_meaningful():
            return False
        self._record()
        self.marks.append(deepcopy(mark))
        return True

    def replace(self, index, mark):
        if not (0 <= index < len(self.marks)) or self.marks[index] == mark:
            return False
        self._record()
        self.marks[index] = deepcopy(mark)
        return True

    def delete(self, index):
        if not (0 <= index < len(self.marks)):
            return False
        self._record()
        del self.marks[index]
        return True

    def index_at_point(self, x, y, radius=8.):
        for i in range(len(self.marks) - 1, -1, -1):
            if mark_touches(self.marks[i], x, y, radius):
                return i
        return None

    def begin_erase(self):
        if self._batch_start is None:
            self._batch_start = self._snapshot()

    def erase_at(self, x, y, radius=12.):
        remaining = [m for m in self.marks if not mark_touches(m, x, y, radius)]
        if len(remaining) == len(self.marks):
            return False
        self._record()
        self.marks = remaining
        return True

    def end_erase(self):
        if self._batch_start is not None and self.marks != self._batch_start:
            self._undo.append(self._batch_start)
            self.redo_stack.clear()
        self._batch_start = None

    def undo(self):
        if not self._undo:
            return False
        self.redo_stack.append(self._snapshot())
        self.marks = self._undo.pop()
        return True

    def redo(self):
        if not self.redo_stack:
            return False
        self._undo.append(self._snapshot())
        self.marks = self.redo_stack.pop()
        return True


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def fit_zoom(width, height, available_width, available_height):
    if min(width, height, available_width, available_height) <= 0:
        return 1.0
    return min(1.0, available_width / width, available_height / height)
