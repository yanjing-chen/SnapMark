"""Role-separated model catalogs and user-approved editor layout contracts."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
OCR = ROOT / 'official_plugins/ocr'
TRANS = ROOT / 'official_plugins/translation'


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem+'_modelrole_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

CATALOG = load(OCR/'catalog.py')
CLIENT = load(TRANS/'runtime_client.py')


class OCRTranslationCatalogTests(unittest.TestCase):
    def test_ocr_and_translation_registration_are_disjoint(self):
        payload = {'data': [
            {'id':'ocr-a','installed':True,'type':'ocr','capabilities':{'ocr':True}},
            {'id':'translation-b','installed':True,'type':'translation','capabilities':{'translation':True}},
            {'id':'chat-c','installed':True,'type':'chat','capabilities':{'chat':True}},
            {'id':'missing','installed':False,'type':'ocr','capabilities':{'ocr':True}},
        ]}
        self.assertEqual(CATALOG.runtime_models(payload, 'ocr'), ['ocr-a'])
        self.assertEqual(CATALOG.runtime_models(payload, 'translation'), ['translation-b'])
        self.assertEqual(CLIENT.registered_models(payload), ['translation-b'])

    def test_type_mismatch_excludes_model_even_if_capabilities_mislabelled(self):
        payload={'data':[{'id':'wrong','installed':True,'type':'ocr','capabilities':{'ocr':True,'translation':True}}]}
        self.assertEqual(CATALOG.runtime_models(payload,'translation'),[])
        self.assertEqual(CLIENT.registered_models(payload),[])

    def test_capability_required_not_name_matching(self):
        payload={'data':[{'id':'OCR-super','installed':True,'type':'ocr'},
                         {'id':'translation-super','installed':True,'type':'translation','capabilities':{'ocr':False}}]}
        self.assertEqual(CATALOG.runtime_models(payload,'ocr'),[])
        self.assertEqual(CLIENT.registered_models(payload),[])

    def test_local_lightweight_explicit_registration_and_real_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            python=root/'python'; python.write_text('#!python'); python.chmod(0o700)
            root_models=root/'models'; root_models.mkdir()
            (root_models/'det').mkdir(); (root_models/'rec').mkdir()
            (root_models/'det'/'x.pdiparams').write_bytes(b'x')
            (root_models/'rec'/'x.pdiparams').write_bytes(b'x')
            settings={'python':str(python),'models_root':str(root_models), 'registered_lightweight':[]}
            specs={'Paddle small': ['det','rec']}
            self.assertEqual(CATALOG.lightweight_available(settings,specs),[])
            settings['registered_lightweight']=['Paddle small']
            self.assertEqual(CATALOG.lightweight_available(settings,specs),['Paddle small'])
            (root_models/'rec'/'x.pdiparams').unlink()
            self.assertEqual(CATALOG.lightweight_available(settings,specs),[])

    def test_selected_translation_model_must_still_be_eligible_at_execution(self):
        fake=[{'data':[{'id':'ocr','installed':True,'type':'ocr','capabilities':{'ocr':True}},
                       {'id':'hy-mt','installed':True,'type':'translation','capabilities':{'translation':True}}]}]
        with patch.object(CLIENT,'_request',side_effect=fake):
            with self.assertRaisesRegex(CLIENT.TranslationError,'not installed and registered'):
                CLIENT.translate('你好','Dutch', model_id='ocr')

    def test_translation_uses_explicit_model_selection(self):
        inputs=[]
        def mock(endpoint,path,**kw):
            inputs.append((path,kw))
            if path=='/v1/models':
                return {'data':[{'id':'model1','installed':True,'type':'translation','capabilities':{'translation':True}}]}
            return {'choices':[{'message':{'content':'Hoi'}}]}
        with patch.object(CLIENT,'_request',side_effect=mock):
            text, model=CLIENT.translate('你好','Dutch',model_id='model1')
        self.assertEqual((text,model),('Hoi','model1'))
        self.assertEqual(inputs[1][1]['payload']['model'],'model1')

    def test_ocr_time_below_editor_run_top(self):
        text=(OCR/'main.py').read_text()
        section=text.split('def build_panel(',1)[1].split('def _apply_models(',1)[0]
        self.assertLess(section.index('header.append(run)'),section.index('root.append(result_stack)'))
        self.assertGreater(section.index('actions.append(self.timer)'),section.index('root.append(result_stack)'))
        self.assertNotIn('OCR area',section)

    def test_translation_timer_before_clear_translation_bottom(self):
        text=(TRANS/'main.py').read_text()
        section=text.split('def build_panel(',1)[1].split('def _refresh_models(',1)[0]
        self.assertIn("label='Time: Not run'",section)
        self.assertLess(section.index('actions.append(self.timer)'),section.index("('Clear translation'"))
        self.assertIn("Gtk.Button(label='Translate')",section)
        self.assertIn('Translation model',section)

    def test_only_preferences_registers_lightweight_models(self):
        text=(OCR/'main.py').read_text()
        editor=text.split('def build_panel(',1)[1].split('def build_preferences(',1)[0]
        self.assertNotIn('Register selected installed model', editor)
        prefs=text.split('def build_preferences(',1)[1].split('def _model_selected(',1)[0]
        self.assertIn('Register selected installed model',prefs)
        self.assertIn('High-performance Runtime OCR',prefs)
        self.assertIn("fetch_runtime_models('ocr')",text)

    def test_windows_panes_initialize_after_map(self):
        text=(ROOT/'snapmark/editor.py').read_text()
        self.assertIn("self.paned.connect('map', self._initial_window_layout)",text)
        self.assertIn('height * 0.59',text)
        self.assertNotIn('self.paned.set_position(945)',text)

if __name__ == '__main__': unittest.main()
