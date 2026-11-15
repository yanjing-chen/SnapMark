"""Exercise real clipboard-probe methods with mocked GDK, no GUI required."""
from __future__ import annotations
import ast
import time
import unittest
from pathlib import Path

from snapmark.clipboard_images import image_mime_types, clipboard_image_state

SRC = Path(__file__).resolve().parents[1] / 'snapmark/app.py'

class Formats:
    def __init__(self, mimes): self.mimes = mimes
    def get_mime_types(self): return self.mimes
    def get_gtypes(self): return ()
    def contain_gtype(self, _): return False

class Clipboard:
    def __init__(self, mimes):
        self.formats=Formats(mimes); self.texture_reads=0; self.stream_reads=0
    def get_formats(self): return self.formats
    def read_async(self,*args): self.stream_reads+=1
    def read_texture_async(self,*args): self.texture_reads+=1

class FakeGLib:
    class Error(Exception): pass
    PRIORITY_DEFAULT=0

class FakeGdk:
    class Texture:
        __gtype__=object()
    class Display:
        clipboard=None
        @classmethod
        def get_default(cls): return cls
        @classmethod
        def get_clipboard(cls): return cls.clipboard

class Methods(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree=ast.parse(SRC.read_text())
        klass=next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name=='SnapMarkApplication')
        names={'probe_clipboard_now','_probe_clipboard_stream'}
        nodes=[n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name in names]
        ast.fix_missing_locations(module:=ast.Module(body=nodes,type_ignores=[]))
        class Settings:
            def monitor_clipboard_images(self): return True
        ctx=dict(Settings=Settings,Gdk=FakeGdk,GLib=FakeGLib,time=time,
                 image_mime_types=image_mime_types,clipboard_image_state=clipboard_image_state)
        exec(compile(module,str(SRC),'exec'),ctx)
        cls.Impl=type('Impl',(),{n:ctx[n] for n in names})

    def setUp(self):
        self.app=self.Impl()
        self.app._menu_probe_at=0
        self.app._clipboard_generation=0
        self.app._read_clipboard_screenshot=lambda *a: setattr(self,'fallback',self.fallback+1)
        self.fallback=0
        self.app._clipboard_stream_ready=lambda *a: None

    def test_text_only_does_not_read_image_payload(self):
        clip=Clipboard(('text/plain',))
        FakeGdk.Display.clipboard=clip
        self.app.probe_clipboard_now(force=True)
        self.assertEqual(clip.texture_reads,0)
        self.assertEqual(clip.stream_reads,0)
        self.assertEqual(self.fallback,1) # image metadata checked only; texture helper declines text

    def test_image_mime_uses_only_stream(self):
        clip=Clipboard(('image/png',))
        FakeGdk.Display.clipboard=clip
        self.app.probe_clipboard_now(force=True)
        self.assertEqual(clip.stream_reads,1)
        self.assertEqual(self.fallback,0)

if __name__=='__main__': unittest.main()
