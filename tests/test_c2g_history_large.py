"""Screenshot History readable-preview geometry and read-only behavior."""
import ast
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
HISTORY=ROOT/'snapmark/history_c2g.py'

class ScreenshotHistoryPreviewTests(unittest.TestCase):
    def test_card_is_compact_and_picture_fills_it(self):
        source=HISTORY.read_text('utf-8')
        tree=ast.parse(source)
        self.assertIn('default_width=1020, default_height=680',source)
        self.assertIn('picture.set_size_request(288, 178)',source)
        self.assertIn('Gtk.Picture()',source)
        self.assertIn('Gtk.ContentFit.CONTAIN',source)
        calls={method:[call for call in ast.walk(tree)
                       if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute)
                       and call.func.attr==method]
               for method in ('set_max_children_per_line','set_min_children_per_line')}
        self.assertEqual(ast.literal_eval(calls['set_max_children_per_line'][0].args[0]),3)
        self.assertEqual(ast.literal_eval(calls['set_min_children_per_line'][0].args[0]),1)

    def test_history_is_read_only_and_opens_original(self):
        source=HISTORY.read_text('utf-8')
        tree=ast.parse(source)
        self.assertIn("btn.connect('clicked', lambda _button, p=path: app.show_editor(p))",source)
        self.assertIn('is_screenshot_folder(folder.name)',source)
        self.assertIn('image.is_symlink()',source)
        writes={'mkdir','write_bytes','write_text','unlink','rename','replace'}
        self.assertFalse([node.func.attr for node in ast.walk(tree)
                          if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute)
                          and node.func.attr in writes])
