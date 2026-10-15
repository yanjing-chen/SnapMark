"""Regression: B3-2 ActionRow management text must be Pango markup-safe."""
from pathlib import Path
import unittest

UI = (Path(__file__).resolve().parent.parent / 'snapmark' / 'ai_runtime_ui.py').read_text(encoding='utf-8')


class RuntimeManagementMarkupContract(unittest.TestCase):
    def test_action_row_title_and_subtitle_are_escaped(self):
        block = UI.split('    def _management_row(', 1)[1].split('    def _refresh_manager_buttons(', 1)[0]
        self.assertIn('title=GLib.markup_escape_text(title)', block)
        self.assertIn('subtitle=GLib.markup_escape_text(subtitle)', block)

    def test_button_caption_remains_plain_text(self):
        block = UI.split('    def _management_row(', 1)[1].split('    def _refresh_manager_buttons(', 1)[0]
        self.assertIn('button = Gtk.Button(label=caption)', block)
        self.assertIn("'Download & verify Runtime 1.0.0'", UI)
