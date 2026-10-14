"""Regression coverage for user-selected, multi-file GGUF grouping, no writes."""
import tempfile
import unittest
from pathlib import Path

from snapmark.model_bundle import (ModelBundleError, inspect_gguf_files,
                                   inspect_gguf_folder)


def gguf(parent, name):
    path = Path(parent) / name
    path.write_bytes(b'GGUF' + b'\x00' * 16)
    return path


class MultiFileGGUFTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def test_paddleocr_main_and_mmproj_are_single_model(self):
        main = gguf(self.folder, 'PaddleOCR-VL-1.6-GGUF.gguf')
        proj = gguf(self.folder, 'PaddleOCR-VL-1.6-GGUF-mmproj.gguf')
        models = inspect_gguf_files([main, proj])
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].main, main)
        self.assertEqual(models[0].projectors, (proj,))
        self.assertTrue(models[0].ready_for_review)
        self.assertFalse(models[0].warnings)
        self.assertEqual(main.read_bytes()[:4], b'GGUF')

    def test_one_selected_file_can_discover_matching_companion_only(self):
        main = gguf(self.folder, 'PaddleOCR-VL-1.6-GGUF.gguf')
        projector = gguf(self.folder, 'PaddleOCR-VL-1.6-GGUF-mmproj.gguf')
        gguf(self.folder, 'unrelated-gguf.gguf')
        models = inspect_gguf_files([main])
        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].projectors, (projector,))

    def test_projector_without_main_is_not_ready(self):
        projector = gguf(self.folder, 'MyModel-mmproj.gguf')
        result = inspect_gguf_files([projector])[0]
        self.assertFalse(result.ready_for_review)
        self.assertIn('No main', result.warnings[0])

    def test_translation_single_gguf_does_not_require_projector(self):
        main = gguf(self.folder, 'HY-MT2-7B-Q8_0.gguf')
        result = inspect_gguf_files([main])[0]
        self.assertTrue(result.ready_for_review)
        self.assertEqual(result.projectors, ())
        self.assertEqual(result.main, main)

    def test_shards_one_model_and_missing_piece_warns(self):
        a = gguf(self.folder, 'text-00001-of-00003.gguf')
        b = gguf(self.folder, 'text-00002-of-00003.gguf')
        c = gguf(self.folder, 'text-00003-of-00003.gguf')
        result = inspect_gguf_files([a])[0]
        self.assertEqual(result.shards, (a, b, c))
        self.assertEqual(result.main, a)
        self.assertTrue(result.ready_for_review)
        c.unlink()
        result = inspect_gguf_files([a])[0]
        self.assertFalse(result.ready_for_review)
        self.assertTrue(any('Missing split parts: 3' in w for w in result.warnings))

    def test_bad_headers_not_mistaken_for_model(self):
        bad = self.folder / 'pretend.gguf'
        bad.write_text('HTML not a GGUF model')
        with self.assertRaisesRegex(ModelBundleError, 'Invalid GGUF header'):
            inspect_gguf_files([bad])

    def test_folder_scans_only_top_level_and_keeps_multiple_models(self):
        gguf(self.folder, 'a.gguf')
        gguf(self.folder, 'b.gguf')
        deeper = self.folder / 'nested'
        deeper.mkdir()
        gguf(deeper, 'c.gguf')
        result = inspect_gguf_folder(self.folder)
        self.assertEqual({x.name for x in result}, {'a', 'b'})

    def test_no_registration_or_mutation_of_model_files(self):
        main = gguf(self.folder, 'PaddleOCR-VL-1.6-GGUF.gguf')
        before = (main.stat().st_size, main.stat().st_mtime_ns)
        inspect_gguf_files([main])
        self.assertEqual((main.stat().st_size, main.stat().st_mtime_ns), before)
        self.assertEqual(list(self.folder.iterdir()), [main])

    def test_empty_folder_and_non_gguf_rejected(self):
        with self.assertRaisesRegex(ModelBundleError, 'No GGUF files'):
            inspect_gguf_folder(self.folder)
        bad = gguf(self.folder, 'model.bin')
        with self.assertRaisesRegex(ModelBundleError, 'Not a regular GGUF'):
            inspect_gguf_files([bad])


if __name__ == '__main__':
    unittest.main()
