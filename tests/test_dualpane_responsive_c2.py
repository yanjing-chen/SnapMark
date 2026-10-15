"""Regression: standalone OCR uses full width; both plugins split evenly; actions hug right."""
import ast
from pathlib import Path
import textwrap
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
EDITOR = (ROOT / 'snapmark/editor.py').read_text(encoding='utf-8')
OCR = (ROOT / 'official_plugins/ocr/main.py').read_text(encoding='utf-8')
TRANSLATION = (ROOT / 'official_plugins/translation/main.py').read_text(encoding='utf-8')


def method(source, cls, meth):
    tree = ast.parse(source)
    definition = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == cls)
    func = next(x for x in definition.body if isinstance(x, ast.FunctionDef) and x.name == meth)
    return ast.get_source_segment(source, func)


class FakeWidget:
    def __init__(self, **kwargs):
        self.children = []
        self.start = self.end = None
        self.position = None
        self.width = 800
        self.height = 700
        self.callbacks = {}
        self.settings = {}
        self.parent = None

    def set_hexpand(self, value): self.settings['hexpand'] = value
    def set_vexpand(self, value): self.settings['vexpand'] = value
    def set_wide_handle(self, value): self.settings['wide'] = value
    def set_resize_start_child(self, value): self.settings['resize_start'] = value
    def set_resize_end_child(self, value): self.settings['resize_end'] = value
    def set_shrink_start_child(self, value): self.settings['shrink_start'] = value
    def set_shrink_end_child(self, value): self.settings['shrink_end'] = value
    def set_start_child(self, child):
        if self.start is not None: self.start.parent = None
        self.start = child
        if child is not None: child.parent = self
    def set_end_child(self, child):
        if self.end is not None: self.end.parent = None
        self.end = child
        if child is not None: child.parent = self
    def get_end_child(self): return self.end
    def set_position(self, position): self.position = position
    def get_width(self): return self.width
    def get_height(self): return self.height
    def get_first_child(self): return self.children[0] if self.children else None
    def append(self, child):
        if child.parent is not None: raise AssertionError('already parented')
        self.children.append(child);child.parent = self
    def remove(self, child):
        self.children.remove(child);child.parent = None
    def connect(self, event, callback): self.callbacks[event] = callback


class FakeGtk:
    Orientation = types.SimpleNamespace(HORIZONTAL='horizontal')
    Box = FakeWidget
    Paned = FakeWidget


class FakeGLib:
    SOURCE_REMOVE = False
    @staticmethod
    def idle_add(callback): return callback()


def get_method(name):
    source = textwrap.dedent(method(EDITOR, 'EditorWindow', name))
    scope = {'Gtk': FakeGtk, 'GLib': FakeGLib}
    exec(compile(source, '<editor method>', 'exec'), scope)
    return scope[name]


class ResponsivePaneTests(unittest.TestCase):
    def setUp(self):
        self.editor = types.SimpleNamespace(
            _plugin_results_stack=None, _plugin_result_widgets={},
            _plugin_results_paned=None, _plugin_visibility={'ocr': False, 'translation': False},
            _result_split=FakeWidget(), _center_plugin_split_on_first_map=lambda _: None)
        self.add = get_method('add_plugin_result')
        self.render = get_method('_render_plugin_results')

    def test_registration_does_not_show_any_bottom_panel(self):
        ocr = FakeWidget()
        self.add(self.editor, 'ocr', 'OCR', lambda _editor: ocr)
        holder = self.editor._plugin_results_stack
        self.assertIsInstance(holder, FakeWidget)
        self.assertEqual(holder.children, [])
        self.assertIsNone(self.editor._result_split.end)

    def test_ocr_only_occupies_full_width(self):
        ocr = FakeWidget()
        self.add(self.editor, 'ocr', 'OCR', lambda _: ocr)
        self.editor._plugin_visibility['ocr'] = True
        self.render(self.editor)
        holder = self.editor._plugin_results_stack
        self.assertEqual(holder.children, [ocr])
        self.assertIs(self.editor._result_split.end, holder)
        self.assertIsNone(self.editor._plugin_results_paned)

    def test_both_panels_center_once_and_support_manual_dragging(self):
        ocr, translation = FakeWidget(), FakeWidget()
        self.add(self.editor, 'ocr', 'OCR', lambda _: ocr)
        self.add(self.editor, 'translation', 'Translation', lambda _: translation)
        self.assertIsNone(self.editor._result_split.end)
        self.editor._plugin_visibility.update(ocr=True, translation=True)
        self.render(self.editor)
        split = self.editor._plugin_results_stack.children[0]
        self.assertIs(split.start, ocr)
        self.assertIs(split.end, translation)
        self.assertEqual(split.position, 400)
        self.assertTrue(split.settings['wide'])
        self.assertIn('map', split.callbacks)
        split.set_position(550)
        self.assertEqual(split.position, 550)

    def test_switch_both_to_ocr_preserves_widget_and_text(self):
        ocr, translation = FakeWidget(), FakeWidget()
        self.add(self.editor, 'ocr', 'OCR', lambda _: ocr)
        self.add(self.editor, 'translation', 'Translation', lambda _: translation)
        self.editor._plugin_visibility.update(ocr=True, translation=True)
        self.render(self.editor)
        self.editor._plugin_visibility['translation'] = False
        self.render(self.editor)
        self.assertEqual(self.editor._plugin_results_stack.children, [ocr])
        self.assertIsNone(translation.parent)
        self.assertIs(self.editor._result_split.end, self.editor._plugin_results_stack)

    def test_hiding_everything_removes_bottom_child(self):
        self.add(self.editor, 'ocr', 'OCR', lambda _: FakeWidget())
        self.editor._plugin_visibility['ocr'] = True
        self.render(self.editor)
        self.editor._plugin_visibility['ocr'] = False
        self.render(self.editor)
        self.assertIsNone(self.editor._result_split.end)
        self.assertEqual(self.editor._plugin_results_stack.children, [])

    def test_duplicate_result_registration_does_not_replace_user_data(self):
        ocr = FakeWidget()
        self.add(self.editor, 'ocr', 'OCR', lambda _: ocr)
        with self.assertRaises(ValueError):
            self.add(self.editor, 'ocr', 'OCR', lambda _: FakeWidget())
        self.assertEqual(self.editor._plugin_result_widgets['ocr'], ocr)

    def test_ocr_actions_right_aligned_and_after_editable_text(self):
        part = method(OCR, 'OCRController', 'build_panel')
        self.assertIn('actions.set_halign(Gtk.Align.FILL)', part)
        self.assertIn('right_spacer.set_hexpand(True)', part)
        self.assertIn('actions.set_valign(Gtk.Align.END)', part)
        self.assertIn('actions.set_homogeneous(False)', part)
        self.assertLess(part.index('root.append(scroll)'), part.index('root.append(actions)'))
        self.assertEqual(part.count("Gtk.Button(label='Run OCR')"), 1)

    def test_translation_actions_right_aligned_and_after_editable_text(self):
        part = method(TRANSLATION, 'TranslationController', 'build_panel')
        self.assertIn('actions.set_halign(Gtk.Align.FILL)', part)
        self.assertIn('right_spacer.set_hexpand(True)', part)
        self.assertIn('actions.set_valign(Gtk.Align.END)', part)
        self.assertIn('actions.set_homogeneous(False)', part)
        self.assertLess(part.index('root.append(scroll)'), part.index('root.append(actions)'))
        self.assertIn('header.append(run)', part)
        self.assertLess(part.index('header.append(run)'), part.index('root.append(scroll)'))

    def test_no_second_ocr_area_and_source_language_selector(self):
        self.assertNotIn('Select region', method(OCR, 'OCRController', 'build_panel'))
        self.assertIn('original_png_for_ocr()', method(OCR, 'OCRController', 'run_whole'))
        self.assertNotIn('Source language', method(TRANSLATION, 'TranslationController', 'build_panel'))
        self.assertIn("host.get_text_provider('ocr')", TRANSLATION)


if __name__ == '__main__':
    unittest.main()
