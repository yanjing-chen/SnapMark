"""C2-F OCR 0.2.4: no table mode; preserve per-model settings and native OCR."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'official_plugins/ocr'
spec = importlib.util.spec_from_file_location('c2f_no_table_profiles', PLUGIN/'profiles_c2f.py')
profiles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiles)

class RemovedTable(unittest.TestCase):
    def test_only_plain_and_paragraphs_remain(self):
        self.assertEqual(profiles.OUTPUTS, ('Plain text', 'Preserve paragraphs'))
        self.assertEqual(profiles.DEFAULT['output'], 'Plain text')
        self.assertEqual(profiles.prompt_for('paddleocr-vl-1.6', {'output':'Preserve paragraphs'}), 'OCR:')
        self.assertIn('paragraph boundaries', profiles.prompt_for('generic-ocr', {'output':'Preserve paragraphs'}))

    def test_legacy_table_profile_falls_back_without_losing_unrelated_fields(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME':tmp}):
            target = profiles.profile_path()
            target.parent.mkdir(parents=True)
            raw = {'models': {'paddleocr-vl-1.6': {
                'preset': 'Model default', 'prompt': '', 'output': 'Table recognition (experimental)',
                'temperature': 0.3, 'max_tokens': 8192, 'streaming': True,
            }}}
            target.write_text(json.dumps(raw), encoding='utf-8')
            before = target.read_bytes()
            updated = profiles.read_profile('paddleocr-vl-1.6')
            self.assertEqual(updated['output'], 'Plain text')
            self.assertEqual(updated['temperature'], 0.3)
            self.assertEqual(updated['max_tokens'], 8192)
            self.assertTrue(updated['streaming'])
            self.assertEqual(target.read_bytes(), before, 'reading must not overwrite user settings')
            profiles.save_profile('paddleocr-vl-1.6', updated)
            after = json.loads(target.read_text(encoding='utf-8'))
            self.assertEqual(after['models']['paddleocr-vl-1.6']['output'], 'Plain text')

    def test_table_cannot_be_newly_saved_for_any_model(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME':tmp}):
            for model in ('paddleocr-vl-1.6', 'generic-ocr'):
                with self.assertRaises(ValueError):
                    profiles.save_profile(model, {'output':'Table recognition (experimental)'})
            self.assertFalse(profiles.profile_path().exists(), 'rejected settings must not change disk')

    def test_gui_and_runtime_never_offer_table_recognition(self):
        main = (PLUGIN / 'main.py').read_text('utf-8')
        runtime = (PLUGIN / 'advanced_runtime_c2.py').read_text('utf-8')
        conf = (PLUGIN / 'profiles_c2f.py').read_text('utf-8')
        self.assertNotIn('Table Recognition:', main + runtime + conf)
        self.assertNotIn('Table recognition (experimental)', main)
        self.assertNotIn('Experimental table recognition', main)
        self.assertNotIn('def output_changed(', main)
        self.assertIn("runtime_model.connect('notify::model', new_selection)", main)
        self.assertIn('Unverified OCR preview:', main)
        self.assertNotIn('Markdown', conf)
        meta = json.loads((PLUGIN/'plugin.json').read_text('utf-8'))
        self.assertEqual(meta['version'],'0.2.4')
        self.assertEqual(json.loads((ROOT/'official_plugins/translation/plugin.json').read_text('utf-8'))['version'], '0.1.5')

if __name__ == '__main__':
    unittest.main()
