"""A3 regression: avoid calling GI inherited do_shutdown as a Python bound method.

Real GUI shutdown is covered by the separate --smoke-test, because this
static test should run even where PyGObject is not installed.
"""
import ast
import unittest
from pathlib import Path


class ApplicationShutdownContractTests(unittest.TestCase):
    def test_signal_handler_preserves_parent_shutdown_and_cleans_tray(self):
        src = (Path(__file__).resolve().parents[1] / 'snapmark' / 'app.py').read_text(encoding='utf-8')
        tree = ast.parse(src)
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == 'SnapMarkApplication')
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        self.assertNotIn('do_shutdown', methods, 'Do not override the GI shutdown VFUNC')
        self.assertIn('_on_shutdown', methods)
        self.assertEqual([a.arg for a in methods['_on_shutdown'].args.args],
                         ['self', '_application'])
        handler_body = ast.unparse(methods['_on_shutdown'])
        self.assertIn('self.tray.stop()', handler_body)
        self.assertNotIn('super()', handler_body)
        init_body = ast.unparse(methods['__init__'])
        self.assertIn("self.connect('shutdown', self._on_shutdown)", init_body)


if __name__ == '__main__':
    unittest.main()
