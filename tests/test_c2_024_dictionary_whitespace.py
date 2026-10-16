"""C2-024: protect PP-OCRv6 dictionary's legitimate blank/space slots."""
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / '.github/workflows/ocr-onnx-engine.yml'


def validator_code():
    s = FLOW.read_text(encoding='utf-8')
    start = "          python3 - \"$MODEL_STAGE/dict.txt\" <<'PYDICT'\n"
    # Workflow contents are bash embedded in YAML, not Python source.
    start = "          python3 - \"$MODEL_STAGE/dict.txt\" <<'PYDICT'\n".replace('\\"','"')
    assert s.count(start) == 1, 'Missing unique PYDICT start'
    section = s.split(start, 1)[1].split('          PYDICT', 1)[0]
    return textwrap.dedent(section)


def run_validator(lines):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'dict.txt'
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return subprocess.run([sys.executable, '-c', validator_code(), str(path)],
                              capture_output=True, text=True, timeout=8)


class WhitespaceDictionaryTests(unittest.TestCase):
    def test_legitimate_space_and_blank_slot_keeps_6904_entries(self):
        chars = ['中'] * 6904
        chars[2] = ' '
        chars[3] = ''
        result = run_validator(chars)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SNAPMARK_V6_TINY_DICT_ENTRIES= 6904', result.stdout)
        self.assertIn('SNAPMARK_V6_TINY_DICT_WHITESPACE_ENTRIES= 2', result.stdout)

    def test_wrong_count_is_rejected(self):
        result = run_validator(['中'] * 6903)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('6903 entries (expected 6904)', result.stderr)

    def test_all_blank_entries_are_rejected(self):
        result = run_validator([' '] * 6904)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('all entries are whitespace', result.stderr)

    def test_only_github_smoke_workflow_changes(self):
        s = FLOW.read_text(encoding='utf-8')
        self.assertIn('ONNXRUNTIME_NODE_INSTALL: skip', s)
        self.assertIn('node worker.cjs --smoke-test --model-dir "$MODEL_STAGE"', s)
        self.assertNotIn('if len(chars) != 6904 or any(not ch.strip() for ch in chars):', s)

if __name__ == '__main__':
    unittest.main()
