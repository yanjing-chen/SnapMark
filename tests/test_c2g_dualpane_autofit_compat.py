"""C2-G: responsive result panes work on both real editor and minimal panel adapters.

Executes the actual EditorWindow._render_plugin_results source against protocol-only
fake panes. The old full test suite used SimpleNamespace with no `_schedule_auto_fit`.
"""
import ast
from pathlib import Path
import types
import unittest

SRC = Path(__file__).resolve().parents[1] / 'snapmark' / 'editor.py'
TEXT = SRC.read_text(encoding='utf-8')
TREE = ast.parse(TEXT)
EDITOR = next(x for x in TREE.body if isinstance(x, ast.ClassDef) and x.name == 'EditorWindow')
METHOD = next(x for x in EDITOR.body if isinstance(x, ast.FunctionDef) and x.name == '_render_plugin_results')
SCOPE = {}
exec(compile('class Extracted:\n' + '\n'.join(TEXT.splitlines()[METHOD.lineno-1:METHOD.end_lineno]), str(SRC), 'exec'),
     {'GLib': types.SimpleNamespace(SOURCE_REMOVE=False, idle_add=lambda cb: cb())}, SCOPE)
RENDER = SCOPE['Extracted']._render_plugin_results

class FakeHolder:
    def __init__(self): self.child = None
    def get_first_child(self): return self.child
    def remove(self, child):
        if child is not self.child: raise AssertionError('wrong child')
        self.child = None
    def append(self, child): self.child = child

class FakePaned:
    def __init__(self, width=520, height=650):
        self.start = None
        self.end = None
        self.position = None
        self.width, self.height = width, height
    def set_start_child(self, widget): self.start=widget
    def set_end_child(self, widget): self.end=widget
    def get_end_child(self): return self.end
    def set_position(self, n): self.position=n
    def get_width(self): return self.width
    def get_height(self): return self.height

class ResponsiveAutoFitCompatTests(unittest.TestCase):
    def make_window(self, ocr, translation, callback=False):
        obj = types.SimpleNamespace()
        obj._plugin_results_stack = FakeHolder()
        obj._result_split = FakePaned()
        obj._plugin_results_paned = FakePaned()
        obj._plugin_visibility = {'ocr':ocr,'translation':translation}
        obj._plugin_result_widgets = {'ocr':object(), 'translation':object()}
        calls = []
        if callback: obj._schedule_auto_fit = lambda: calls.append('fit')
        return obj, calls

    def test_ocr_only_no_autofit_method_keeps_full_width(self):
        obj, _ = self.make_window(True, False)
        RENDER(obj)
        self.assertIs(obj._result_split.end, obj._plugin_results_stack)
        self.assertIs(obj._plugin_results_stack.child, obj._plugin_result_widgets['ocr'])
        self.assertGreater(obj._result_split.position, 100)

    def test_both_panels_no_autofit_method_still_center(self):
        obj, _ = self.make_window(True, True)
        RENDER(obj)
        self.assertIs(obj._plugin_results_paned.start, obj._plugin_result_widgets['ocr'])
        self.assertIs(obj._plugin_results_paned.end, obj._plugin_result_widgets['translation'])
        self.assertIs(obj._plugin_results_stack.child, obj._plugin_results_paned)
        self.assertEqual(obj._plugin_results_paned.position, 260)

    def test_hiding_all_no_autofit_method_removes_bottom(self):
        obj, _ = self.make_window(True, True)
        RENDER(obj)
        obj._plugin_visibility={'ocr':False,'translation':False}
        RENDER(obj)
        self.assertIsNone(obj._result_split.end)
        self.assertIsNone(obj._plugin_results_stack.child)

    def test_rerender_retains_same_ocr_and_translation_widgets(self):
        obj, _ = self.make_window(True, True)
        ocr_widget=obj._plugin_result_widgets['ocr']
        translation_widget=obj._plugin_result_widgets['translation']
        RENDER(obj)
        obj._plugin_visibility['translation']=False
        RENDER(obj)
        obj._plugin_visibility['translation']=True
        RENDER(obj)
        self.assertIs(obj._plugin_results_paned.start, ocr_widget)
        self.assertIs(obj._plugin_results_paned.end, translation_widget)

    def test_real_editor_still_schedules_auto_fit(self):
        obj, calls = self.make_window(True, True, callback=True)
        RENDER(obj)
        self.assertEqual(calls, ['fit'])
        obj._plugin_visibility['ocr']=False
        obj._plugin_visibility['translation']=False
        RENDER(obj)
        self.assertEqual(calls, ['fit','fit'])

if __name__ == '__main__': unittest.main()
