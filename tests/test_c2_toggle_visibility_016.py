"""C2 panel visibility contract: no auto-expand, Translation implies OCR."""
import ast
from pathlib import Path
import textwrap
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / 'snapmark/editor.py').read_text('utf-8')
OCR = (ROOT / 'official_plugins/ocr/main.py').read_text('utf-8')
TRANSLATION = (ROOT / 'official_plugins/translation/main.py').read_text('utf-8')


def meth(code, cls, name):
    tree = ast.parse(code)
    klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
    fn = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(code, fn)


class Toggle:
    def __init__(self, active=False):
        self.active = active
        self.sensitive = True
    def get_active(self): return self.active
    def set_active(self, flag): self.active = flag
    def set_sensitive(self, value): self.sensitive = value


class PluginPanelBehavior(unittest.TestCase):
    def setUp(self):
        self.ocr = Toggle()
        self.trans = Toggle()
        self.ed = types.SimpleNamespace(
            _plugin_action_buttons={'ocr': self.ocr, 'translation': self.trans},
            _plugin_visibility={'ocr': False, 'translation': False},
            _updating_plugin_buttons=False,
            render_count=0,
        )
        self.ed._render_plugin_results = lambda: setattr(self.ed, 'render_count', self.ed.render_count+1)
        scope = {}
        exec(compile(textwrap.dedent(meth(EDITOR, 'EditorWindow', '_plugin_button_toggled')),
                     '<toggle behavior>', 'exec'), scope)
        self.callback = scope['_plugin_button_toggled']

    def test_both_buttons_start_off(self):
        self.assertFalse(self.ocr.get_active())
        self.assertFalse(self.trans.get_active())
        self.assertEqual(self.ed._plugin_visibility, {'ocr': False, 'translation': False})

    def test_open_ocr_only(self):
        self.ocr.set_active(True)
        self.callback(self.ed, self.ocr, 'ocr')
        self.assertEqual(self.ed._plugin_visibility, {'ocr': True, 'translation': False})
        self.assertTrue(self.ocr.sensitive)

    def test_translation_automatically_opens_and_locks_ocr(self):
        self.trans.set_active(True)
        self.callback(self.ed, self.trans, 'translation')
        self.assertTrue(self.ocr.get_active())
        self.assertTrue(self.trans.get_active())
        self.assertEqual(self.ed._plugin_visibility, {'ocr': True, 'translation': True})
        self.assertFalse(self.ocr.sensitive)
        self.assertEqual(self.ed.render_count, 1)

    def test_close_translation_keeps_ocr_open(self):
        self.trans.set_active(True)
        self.callback(self.ed, self.trans, 'translation')
        self.trans.set_active(False)
        self.callback(self.ed, self.trans, 'translation')
        self.assertTrue(self.ocr.get_active())
        self.assertEqual(self.ed._plugin_visibility, {'ocr': True, 'translation': False})
        self.assertTrue(self.ocr.sensitive)

    def test_close_last_ocr_hides_all(self):
        self.ocr.set_active(True)
        self.callback(self.ed, self.ocr, 'ocr')
        self.ocr.set_active(False)
        self.callback(self.ed, self.ocr, 'ocr')
        self.assertEqual(self.ed._plugin_visibility, {'ocr': False, 'translation': False})

    def test_translation_never_remains_without_ocr(self):
        self.trans.set_active(True)
        self.ed._plugin_action_buttons.pop('ocr')
        self.callback(self.ed, self.trans, 'translation')
        self.assertFalse(self.trans.get_active())
        self.assertFalse(self.ed._plugin_visibility['translation'])

    def test_toolbar_only_toggles_visibility_does_not_run_ocr(self):
        part = meth(EDITOR, 'EditorWindow', 'add_plugin_action')
        self.assertIn('Gtk.ToggleButton(', part)
        self.assertIn("button.connect('toggled', self._plugin_button_toggled, ident)", part)
        self.assertNotIn('callback()', part)
        self.assertNotIn('run_whole(', part)
        self.assertNotIn('run_whole(', meth(OCR, 'OCRController', 'on_toolbar'))
        self.assertIn("host.register_toolbar_action('translation', 'Translation'", TRANSLATION)

    def test_initial_registration_does_not_show_bottom(self):
        part = meth(EDITOR, 'EditorWindow', 'add_plugin_result')
        self.assertNotIn('self._result_split.set_end_child(holder)', part)
        self.assertIn('do NOT attach the holder', part)
        constructor = meth(EDITOR, 'EditorWindow', '__init__')
        self.assertIn("_plugin_visibility = {'ocr': False, 'translation': False}", constructor)

    def test_compact_single_row_translation_controls_and_blank_catalog(self):
        part = meth(TRANSLATION, 'TranslationController', 'build_panel')
        self.assertIn('Gtk.Orientation.HORIZONTAL', part)
        self.assertLess(part.index('header.append(selector)'),part.index('header.append(dropdown)'))
        self.assertLess(part.index('header.append(dropdown)'),part.index('header.append(run)'))
        self.assertNotIn("Gtk.Label(label='Translation model'",part)
        self.assertNotIn("Gtk.Label(label='Target language'",part)
        self.assertIn("Gtk.DropDown.new_from_strings([''])",part)
        self.assertIn("Gtk.StringList.new(names or [''])", TRANSLATION)

    def test_ocr_compact_icon_model_and_blank_catalog(self):
        part = meth(OCR, 'OCRController', 'build_panel')
        self.assertIn('Gtk.Image.new_from_icon_name(',part)
        self.assertNotIn("Gtk.Label(label='OCR model'",part)
        self.assertIn("Gtk.DropDown.new_from_strings([''])",part)
        self.assertIn("Gtk.StringList.new(items or [''])",OCR)

    def test_both_timers_bottom_left_actions_right(self):
        for source,controller in ((OCR,'OCRController'),(TRANSLATION,'TranslationController')):
            part = meth(source,controller,'build_panel')
            self.assertIn('actions.set_halign(Gtk.Align.FILL)',part)
            self.assertIn('right_spacer.set_hexpand(True)',part)
            self.assertLess(part.index('actions.append(self.timer)'),part.index('actions.append(right_spacer)'))
            self.assertLess(part.index('actions.append(right_spacer)'),part.index('root.append(actions)'))
            self.assertLess(part.index('root.append(scroll)'),part.index('root.append(actions)'))

    def test_editor_models_are_not_installed_from_editor(self):
        ocr_panel = meth(OCR,'OCRController','build_panel')
        trans_panel = meth(TRANSLATION,'TranslationController','build_panel')
        for part in (ocr_panel,trans_panel):
            self.assertNotIn('install_zip',part)
            self.assertNotIn('register_clicked',part)

if __name__ == '__main__': unittest.main()
