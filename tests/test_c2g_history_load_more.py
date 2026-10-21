"""Run *real History nested GTK callbacks* with deterministic GTK/GLib stand-ins.

No screenshot reading, no GUI display, no Runtime/model invocation needed.
"""
import ast
import collections
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'snapmark/history_c2g.py'


def callbacks(count, failing=()):
    code = ast.parse(SOURCE.read_text(encoding='utf-8'))
    show = next(n for n in code.body if isinstance(n, ast.FunctionDef) and n.name == 'show_history')
    inner = [n for n in ast.walk(show) if isinstance(n, ast.FunctionDef)
             and n.name in ('fill_thumbnail', 'load_more')]
    assert {n.name for n in inner} == {'fill_thumbnail', 'load_more'}
    frames = collections.deque()
    pictures = []

    class Picture:
        def __init__(self):
            self.paintable = None
            pictures.append(self)
        def set_paintable(self, value): self.paintable = value
        def set_content_fit(self, *_): pass
        def set_can_shrink(self, *_): pass
        def set_size_request(self, *_): pass
        def set_halign(self, *_): pass
    class Widget:
        def __init__(self, *a, **k): self.visible = None
        def add_css_class(self, *_): pass
        def set_margin_bottom(self, *_): pass
        def set_halign(self, *_): pass
        def set_child(self, *_): pass
        def set_tooltip_text(self, *_): pass
        def connect(self, *_): pass
        def set_max_width_chars(self, *_): pass
        def set_width_chars(self, *_): pass
        def set_ellipsize(self, *_): pass
        def append(self, *_): pass
        def set_visible(self, value): self.visible = value
    class Flow:
        def __init__(self): self.cells = []
        def insert(self, cell, position): self.cells.append(cell)
    class GLib:
        PRIORITY_DEFAULT_IDLE = 20
        Error = ValueError
        @staticmethod
        def idle_add(fn, priority=20):
            frames.append(fn)
            return len(frames)
    class Texture:
        @staticmethod
        def new_for_pixbuf(data): return data
    flow, more = Flow(), Widget()
    pending, position, closed, scheduled = [], [0], [False], [False]
    items = [Path(f'/fake/Screenshot-{i:03d}.png') for i in range(count)]
    failing = set(failing)
    def preview(filename):
        if str(filename) in failing:
            raise OSError('Test-only corrupted PNG')
        return str(filename)
    scope = dict(
        Gtk=SimpleNamespace(Picture=Picture, Button=Widget, Box=Widget, Label=Widget,
                            ContentFit=SimpleNamespace(CONTAIN=0),
                            Align=SimpleNamespace(CENTER=0),
                            Orientation=SimpleNamespace(VERTICAL=0)),
        GLib=GLib, Gdk=SimpleNamespace(Texture=Texture),
        Pango=SimpleNamespace(EllipsizeMode=SimpleNamespace(END=0)),
        _thumbnail_preview=preview, _card_pixbuf=lambda value: 'preview:' + value,
        app=SimpleNamespace(show_editor=lambda *_: None),
        flow=flow, more=more, items=items, pending=pending, position=position,
        closed=closed, scheduled=scheduled,
    )
    exec(compile(ast.Module(body=inner, type_ignores=[]), str(SOURCE), 'exec'), scope)
    def drain():
        iteration = 0
        while frames:
            iteration += 1
            if iteration > 300:
                raise AssertionError('Idle callback unexpectedly loops forever')
            cb = frames.popleft()
            if cb():
                frames.append(cb)
    return SimpleNamespace(load=scope['load_more'], drain=drain, pictures=pictures,
                           scheduled=scheduled, pending=pending, flow=flow,
                           frames=frames, more=more, items=items)


class HistoryLoadMoreTests(unittest.TestCase):
    def test_first_batch_releases_idle_scheduler(self):
        ctx = callbacks(38)
        ctx.load()
        self.assertTrue(ctx.scheduled[0])
        ctx.drain()
        self.assertFalse(ctx.scheduled[0], 'After draining batch 1, scheduler must reset')
        self.assertEqual(len(ctx.pictures), 18)
        self.assertTrue(all(x.paintable is not None for x in ctx.pictures))

    def test_second_and_third_batches_render_real_previews(self):
        ctx = callbacks(38)
        for expected in (18, 36, 38):
            ctx.load()
            ctx.drain()
            self.assertEqual(len(ctx.pictures), expected)
            self.assertEqual(len(ctx.flow.cells), expected)
            self.assertTrue(all(x.paintable is not None for x in ctx.pictures),
                            f'Page ending at {expected} has blank previews')
            self.assertFalse(ctx.scheduled[0])
        self.assertFalse(ctx.more.visible)

    def test_next_load_during_active_thumbnail_job_is_not_lost(self):
        ctx = callbacks(38)
        ctx.load()
        ctx.load()  # User clicks Load more before idle task has finished
        self.assertEqual(len(ctx.frames), 1, 'One pending batch processor should suffice')
        ctx.drain()
        self.assertEqual(len(ctx.pictures), 36)
        self.assertTrue(all(p.paintable for p in ctx.pictures))
        self.assertFalse(ctx.scheduled[0])
        ctx.load()
        ctx.drain()
        self.assertEqual(len(ctx.pictures), 38)
        self.assertTrue(all(p.paintable for p in ctx.pictures))

    def test_corrupt_file_does_not_block_new_batch(self):
        bad = '/fake/Screenshot-008.png'
        ctx = callbacks(20, failing={bad})
        ctx.load()
        ctx.drain()
        self.assertFalse(ctx.scheduled[0])
        self.assertIsNone(ctx.pictures[8].paintable)
        self.assertTrue(all(p.paintable for i, p in enumerate(ctx.pictures) if i != 8))
        ctx.load()
        ctx.drain()
        self.assertTrue(all(p.paintable for p in ctx.pictures[18:]))
        self.assertFalse(ctx.scheduled[0])

if __name__ == '__main__':
    unittest.main()
