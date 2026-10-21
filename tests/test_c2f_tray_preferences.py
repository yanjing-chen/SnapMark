"""Four OCR 0.2.4 contracts: independent tray Preferences without table mode."""
import ast
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MAIN=(ROOT/'official_plugins/ocr/main.py').read_text('utf-8')
TREE=ast.parse(MAIN)
CONTROLLER=next(c for c in TREE.body if isinstance(c,ast.ClassDef) and c.name=='OCRController')
PREF=next(n for n in CONTROLLER.body if isinstance(n,ast.FunctionDef) and n.name=='build_preferences')
GUI=next(n for n in CONTROLLER.body if isinstance(n,ast.FunctionDef) and n.name=='_add_c2f_settings')

def fragment(node):return ast.get_source_segment(MAIN,node) or ''

class TrayPreferences(unittest.TestCase):
    def test_tray_opens_auto_fetch_after_profile_widgets_are_built(self):
        names=[fragment(n).strip() for n in PREF.body]
        add = [i for i,s in enumerate(names) if s.startswith('self._add_c2f_settings(')]
        fetch=[i for i,s in enumerate(names) if s=='GLib.idle_add(refresh_runtime, None)']
        self.assertEqual(len(add),1)
        self.assertEqual(len(fetch),1)
        self.assertLess(add[0],fetch[0])
        self.assertEqual(names[-1],'return page')
    def test_saved_model_restored_in_async_runtime_completion(self):
        refresh=[n for n in ast.walk(PREF) if isinstance(n,ast.FunctionDef) and n.name=='refresh_runtime']
        self.assertEqual(len(refresh),1)
        done=[n for n in ast.walk(refresh[0]) if isinstance(n,ast.FunctionDef) and n.name=='done']
        self.assertEqual(len(done),1)
        body=fragment(done[0])
        self.assertIn("preferred = self.settings.get('model', '')",body)
        self.assertIn('if items:',body)
        self.assertIn('runtime_model.set_selected(items.index(preferred) if preferred in items else 0)',body)
        self.assertIn("Connected · no OCR models",body)
    def test_selection_reconciles_on_both_list_and_selected_changes(self):
        text=fragment(GUI)
        self.assertIn("runtime_model.connect('notify::selected', new_selection)",text)
        self.assertIn("runtime_model.connect('notify::model', new_selection)",text)
        self.assertIn('show_profile(current_model())',text)
    def test_table_limitation_is_honest_and_runtime_unchanged(self):
        text=fragment(GUI)
        self.assertNotIn('Table Recognition:', text)
        self.assertNotIn('Table recognition (experimental)', text)
        self.assertIn('best-effort paragraphs', text)
        self.assertIn('_profiles_c2f.native_paddle(name)', text)
        manifest=json.loads((ROOT/'official_plugins/ocr/plugin.json').read_text())
        self.assertEqual(manifest['version'],'0.2.4')
        self.assertEqual(manifest['dependencies'],{})
        self.assertEqual(json.loads((ROOT/'official_plugins/translation/plugin.json').read_text())['version'],'0.1.5')

if __name__=='__main__':unittest.main()
