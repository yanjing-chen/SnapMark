"""C3: extracted legacy GTK behavior tests must not require imported gettext names."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "snapmark" / "editor.py"


def extracted_method(name, namespace):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    editor = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "EditorWindow")
    method = next(node for node in editor.body if isinstance(node, ast.FunctionDef) and node.name == name)
    code = compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(SOURCE), "exec")
    exec(code, namespace)
    return namespace[name]

class LocalizeCompatibility(unittest.TestCase):
    def test_legacy_dualpane_extracted_method_without_i18n_globals(self):
        calls = []
        widget = SimpleNamespace(set_hexpand=lambda v: calls.append(("hexpand", v)),
                                 set_vexpand=lambda v: calls.append(("vexpand", v)))
        obj = SimpleNamespace(_plugin_result_widgets={}, _plugin_results_stack=object())
        method = extracted_method("add_plugin_result", {})
        self.assertIs(method(obj, "ocr", "OCR", lambda owner: widget), widget)
        self.assertIn(("hexpand", True), calls)
        self.assertIs(obj._plugin_result_widgets["ocr"], widget)

    def test_normal_widget_localization_is_not_silenced(self):
        calls = []
        widget = SimpleNamespace(set_hexpand=lambda v: None, set_vexpand=lambda v: None)
        obj = SimpleNamespace(_plugin_result_widgets={}, _plugin_results_stack=object())
        ns = {"localize_widget_tree": lambda w, plugin_id=None: calls.append((w, plugin_id))}
        method = extracted_method("add_plugin_result", ns)
        method(obj, "translation", "Translation", lambda owner: widget)
        self.assertEqual(calls, [(widget, "translation")])

    def test_tool_button_translation_is_optional_for_legacy_method_extraction(self):
        s = SOURCE.read_text(encoding="utf-8")
        self.assertIn("_localize_text = globals().get('_', lambda text: text)", s)
        self.assertIn("tooltip_text=_localize_text(", s)
        self.assertIn("label=_localize_text(label)", s)

    def test_all_widget_localization_sites_have_guards(self):
        s = SOURCE.read_text(encoding="utf-8")
        self.assertGreaterEqual(s.count('if callable(globals().get("localize_widget_tree")):'), 4)
        self.assertIn('localize_widget_tree(plugin_page, plugin_id=ident)', s)
        self.assertIn('localize_widget_tree(window)', s)

if __name__ == "__main__": unittest.main()
