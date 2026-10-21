"""Static contracts plus isolated file-format/config checks for C2-G Batch A."""
import ast
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def source(name):
    return (ROOT/name).read_text('utf-8')

class C2GBatchContract(unittest.TestCase):
    def test_printscreen_does_not_open_editor(self):
        tree=ast.parse(source('snapmark/app.py'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SnapMarkApplication')
        meth=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='start_watching')
        assert len(meth.body)==2 and isinstance(meth.body[-1],ast.Return)
        self.assertNotIn('self.watcher = ScreenshotWatcher(',source('snapmark/app.py'))
    def test_clipboard_images_only_explicit(self):
        app=source('snapmark/app.py')
        self.assertIn("read_texture_async(None, finished)",app)
        self.assertIn('clipboard_has_image',app)
        self.assertIn('get_formats()',app)
    def test_tray_menu_icons_and_disabled_clipboard(self):
        tray=source('snapmark/tray.py')
        for name in ('Open Clipboard Image','Screenshot History','Preferences','About','Quit'):
            self.assertIn(name,tray)
        self.assertIn("'icon-name'",tray)
        self.assertIn('self.clipboard_ready() if index == 2',tray)
        self.assertIn("'ItemsPropertiesUpdated'",tray)
    def test_history_read_only_and_screenshot_directories(self):
        gallery=source('snapmark/history_c2g.py')
        self.assertIn('is_screenshot_folder(folder.name)',gallery)
        self.assertNotIn('monitor_directory',gallery)
        tree = ast.parse(gallery)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split('.')[0])
        self.assertFalse({'sqlite', 'sqlite3'} & imported,
                         'History must not import a database driver')
        # Check side-effecting operations, not words in documentation strings.
        writes = {'write_bytes', 'write_text', 'mkdir', 'touch', 'unlink',
                  'rmdir', 'rename', 'replace', 'remove', 'makedirs'}
        self.assertFalse([
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in writes
        ], 'History must not create, change or delete screenshots')
        self.assertIn('new_from_file_at_scale',gallery)
    def test_history_filters_other_images(self):
        # Test pure path logic after creating a fake GNOME Pictures folder.
        import sys
        sys.path.insert(0,str(ROOT))
        from snapmark.history_c2g import history_paths
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); pictures=root/'图片'; folder=pictures/'截图'; folder.mkdir(parents=True)
            (pictures/'random.png').write_bytes(b'not a screenshot')
            (folder/'截图 2026-10-21.png').write_bytes(b'file')
            self.assertEqual([x.name for x in history_paths(pictures,home=root)],['截图 2026-10-21.png'])
    def test_default_export_validation(self):
        from snapmark.preferences import Settings
        with tempfile.TemporaryDirectory() as tmp:
            settings=Settings(tmp)
            self.assertEqual(settings.image_format(),'png')
            settings.set_image_format('webp');settings.set_image_quality(86)
            self.assertEqual(Settings(tmp).image_format(),'webp')
            self.assertEqual(Settings(tmp).image_quality(),86)
            with self.assertRaises(ValueError): settings.set_image_format('pdf')
    def test_actual_save_encoders_for_each_format(self):
        editor=source('snapmark/editor.py')
        self.assertIn("'.webp': 'webp'",editor)
        self.assertIn("'.jpeg': 'jpeg'",editor)
        self.assertIn("pixbuf.savev(temporary, fmt",editor)
        self.assertIn('self.settings.image_format()',editor)
    def test_compact_button_sizes_and_tooltips(self):
        editor=source('snapmark/editor.py')
        self.assertIn('button.set_size_request(56, 52)',editor)
        self.assertIn('button.set_size_request(62, 52)',editor)
        self.assertIn('icon.set_content_width(22)',editor)
        self.assertIn('Pango.EllipsizeMode.END',editor)
        self.assertIn('tooltip_text=label',editor)
    def test_no_ocr_or_runtime_edits(self):
        # Nothing in this patch modifies official_plugins or Local AI Runtime.
        script=(Path(__file__).parent/'patch.py').read_text('utf-8') if (Path(__file__).parent/'patch.py').exists() else ''
        self.assertNotIn("patch('official_plugins",script)
    def test_python_parses(self):
        for name in ('snapmark/app.py','snapmark/editor.py','snapmark/tray.py','snapmark/preferences.py','snapmark/history_c2g.py'):
            ast.parse(source(name), filename=name)

if __name__=='__main__':unittest.main()
