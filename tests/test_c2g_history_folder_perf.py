"""C2-G Screenshot History folder, localized paths, 3-column progressive previews."""
import ast
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
HIST=ROOT/'snapmark/history_c2g.py'
EDIT=ROOT/'snapmark/editor.py'

class FolderAndPerformanceTests(unittest.TestCase):
    def test_localized_manual_folder_without_magic_name(self):
        text=HIST.read_text('utf-8')
        fn=next(x for x in ast.parse(text).body if isinstance(x,ast.FunctionDef)
                and x.name=='history_paths')
        env={'Path':Path,'IMAGE_SUFFIXES':frozenset({'.png','.jpg','.jpeg','.webp'}),
             'is_screenshot_folder':lambda name:name.casefold() in {'截图','screenshots'}}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(HIST),'exec'),env)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pics=root/'Pictures';pics.mkdir()
            selected=root/'Aangepaste Schermopnamen';selected.mkdir()
            (selected/'Screenshot 2026.png').write_bytes(b'fake')
            (selected/'other.txt').write_bytes(b'text')
            self.assertEqual([p.name for p in env['history_paths'](pics,selected,home=root)],
                             ['Screenshot 2026.png'])
            self.assertEqual(env['history_paths'](pics,home=root),[])

    def test_three_columns_progressive_nonblocking_window(self):
        t=HIST.read_text('utf-8')
        self.assertIn('flow.set_max_children_per_line(3)',t)
        self.assertIn('flow.set_min_children_per_line(1)',t)
        self.assertIn('GLib.idle_add(load_more',t)
        self.assertIn('GLib.idle_add(fill_thumbnail',t)
        self.assertIn('start + 18',t)
        self.assertIn("more = Gtk.Button(label='Load more screenshots')",t)
        self.assertIn('window.present()',t)
        self.assertIn('Gdk.Texture.new_for_pixbuf',t)
        self.assertIn('Gtk.ContentFit.CONTAIN',t)
        self.assertIn('picture.set_size_request(288, 178)',t)
        self.assertIn('1280, 850',t)
        self.assertIn('InterpType.BILINEAR',t)

    def test_folder_row_preserved_and_watcher_not_reenabled(self):
        src=EDIT.read_text('utf-8')
        self.assertIn("folder = Adw.ActionRow(title='Screenshot history folder'",src)
        self.assertIn('screenshot_group.add(folder)',src)
        self.assertIn('Settings().set_screenshot_directory(selected.get_path())',src)
        self.assertIn("Settings().set_screenshot_directory('')",src)
        self.assertNotIn('self.get_application().refresh_watching()',src)

    def test_history_never_mutates_screenshots(self):
        text=HIST.read_text('utf-8')
        self.assertIn('app.show_editor(p)',text)
        tree=ast.parse(text)
        mutators={'mkdir','write_bytes','write_text','unlink','rename','replace','savev'}
        self.assertFalse([n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call)
                          and isinstance(n.func,ast.Attribute) and n.func.attr in mutators])

if __name__=='__main__':unittest.main()
