"""Focused regression for actual image previews and General preferences order."""
import ast
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
HIST=ROOT/'snapmark/history_c2g.py'
EDITOR=ROOT/'snapmark/editor.py'

class C2GFinalVisualTests(unittest.TestCase):
    def test_content_crop_targets_white_space_without_changing_files(self):
        src=HIST.read_text('utf-8')
        tree=ast.parse(src)
        helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
                    and n.name=='_content_bounds_rgb')
        ns={}
        exec(compile(ast.Module(body=[helper],type_ignores=[]),str(HIST),'exec'),ns)
        width,height=140,90
        pix=bytearray([255,255,255]*(width*height))
        for y in range(35,54):
            for x in range(47,99):
                off=(y*width+x)*3
                pix[off:off+3]=b'\x20\x20\x20'
        bounds=ns['_content_bounds_rgb'](pix,width,height,width*3,3)
        self.assertIsNotNone(bounds)
        self.assertLess(bounds[2],width)
        self.assertLess(bounds[3],height)
        self.assertLess(bounds[0],47)
        self.assertGreater(bounds[0]+bounds[2],98)
        blank=bytearray([255,255,255]*(width*height))
        self.assertIsNone(ns['_content_bounds_rgb'](blank,width,height,width*3,3))

    def test_history_preview_uses_paintable_coverage_but_not_file_mutation(self):
        src=HIST.read_text('utf-8')
        self.assertIn('Gtk.Picture()',src)
        self.assertIn('Gtk.ContentFit.CONTAIN',src)
        self.assertIn('picture.set_size_request(288, 178)',src)
        self.assertIn('def _thumbnail_preview(filename)',src)
        self.assertIn('btn.connect(\'clicked\', lambda _button, p=path: app.show_editor(p))',src)
        tree=ast.parse(src)
        history=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='history_paths')
        self.assertIn('is_screenshot_folder(folder.name)',ast.get_source_segment(src,history))
        blocked={'write_bytes','write_text','unlink','rename','replace','mkdir'}
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n,ast.Call) and
                          isinstance(n.func,ast.Attribute) and n.func.attr in blocked])

    def test_general_format_and_quality_are_last(self):
        src=EDITOR.read_text('utf-8')
        part=src[src.index('    def show_preferences(self):'):]
        self.assertLess(part.index('group.add(startup)'),part.index('group.add(minimized)'))
        self.assertLess(part.index('group.add(minimized)'),part.index('group.add(export)'))
        self.assertLess(part.index('group.add(export)'),part.index('group.add(quality)'))
        self.assertEqual(src.count("export = Adw.ComboRow(title='Default image format'"),1)
        self.assertEqual(src.count("quality.set_title('JPEG / WebP quality')"),1)

if __name__=='__main__':unittest.main()
