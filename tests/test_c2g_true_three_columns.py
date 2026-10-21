"""Regression for GTK4 FlowBox intrinsic thumbnail sizing and 3-column layout."""
import ast
import importlib.util
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'snapmark/history_c2g.py'

class ThreeColumnHistoryTests(unittest.TestCase):
    def test_picture_natural_dimensions_are_bounded(self):
        src=SRC.read_text('utf-8')
        node=next(n for n in ast.parse(src).body if isinstance(n,ast.FunctionDef)
                  and n.name=='_card_pixbuf')
        class MockPix:
            def __init__(self,w,h):self.w,self.h=w,h
            def get_width(self): return self.w
            def get_height(self):return self.h
            def scale_simple(self,w,h,method):return MockPix(w,h)
        class StubInterp: HYPER='hyper'
        class StubGdk: InterpType=StubInterp
        scope={'GdkPixbuf':StubGdk}
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(SRC),'exec'),scope)
        resize=scope['_card_pixbuf']
        for width,height in ((760,480),(1280,850),(400,180),(120,80), (2400,600)):
            pix=resize(MockPix(width,height))
            self.assertLessEqual(pix.get_width(),288)
            self.assertLessEqual(pix.get_height(),178)
            self.assertGreaterEqual(pix.get_width(),1)
            self.assertGreaterEqual(pix.get_height(),1)
            self.assertAlmostEqual(pix.get_width()/pix.get_height(),width/height,delta=.025)

    def test_flowbox_can_display_three_cards_without_natural_width_growth(self):
        t=SRC.read_text('utf-8')
        self.assertIn('flow.set_max_children_per_line(3)',t)
        self.assertIn('flow.set_min_children_per_line(1)',t)
        self.assertIn('picture.set_size_request(288, 178)',t)
        self.assertIn('label.set_max_width_chars(23)',t)
        self.assertIn('label.set_width_chars(23)',t)
        self.assertIn('Gdk.Texture.new_for_pixbuf(_card_pixbuf(_thumbnail_preview(filename)))',t)
        # Default 1020 wide: 3x288 with typical GTK spacing + margins fits.
        self.assertLessEqual(3*288+2*12+2*14,1020)
        self.assertIn('GLib.idle_add(load_more',t)
        self.assertIn('GLib.idle_add(fill_thumbnail',t)
        self.assertIn("btn.connect('clicked', lambda _button, p=path: app.show_editor(p))",t)

    def test_history_filters_and_configuration_remain_unchanged(self):
        t=SRC.read_text('utf-8')
        self.assertIn('def history_paths(',t)
        self.assertIn('Settings().screenshot_directory()',t)
        self.assertIn('GLib.get_user_special_dir(',t)
        self.assertIn('def _content_bounds_rgb(',t)
        tree=ast.parse(t)
        prohibited={'write_text','write_bytes','unlink','rename','replace','mkdir'}
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n,ast.Call)
                          and isinstance(n.func,ast.Attribute) and n.func.attr in prohibited])

if __name__=='__main__': unittest.main()
