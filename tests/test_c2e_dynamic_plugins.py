"""C2-E dynamic plugin discovery, identity, dependency and navigation tests (offline)."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from snapmark.plugins import PluginManager, PluginError, valid_plugin_id, available_releases
from snapmark.plugin_host import PluginHost, load_plugin


def archive(ident, version='0.1.0', dependencies=None, entrypoint='main:register'):
    data = {'id':ident,'version':version,'api_version':1,
            'min_host_version':'0.6.0','dependencies':dependencies or {},
            'entrypoint':entrypoint,'name':'Demo extension'}
    payload=io.BytesIO()
    with zipfile.ZipFile(payload,'w') as z:
        z.writestr('plugin.json',json.dumps(data))
        z.writestr('main.py',
            'def register(host):\n'
            '    host.register_preferences_page(\''+ident+'\', \'Demo extension\', lambda x: None)\n')
    blob=payload.getvalue()
    return blob, hashlib.sha256(blob).hexdigest()


class DynamicPluginTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        base=Path(self.temporary.name)
        self.manager=PluginManager(base/'plugins',base/'config')

    def tearDown(self):
        self.temporary.cleanup()

    def install(self, ident, **kwargs):
        blob,digest=archive(ident,**kwargs)
        self.manager.install_zip(blob,ident,kwargs.get('version','0.1.0'),digest)

    def test_safe_plugin_identifiers(self):
        for bad in ('../escape','/etc','x.y','Aplugin','', 'foo/bar', '漢字', 'x'*49):
            self.assertFalse(valid_plugin_id(bad),bad)
        self.assertTrue(valid_plugin_id('qr-code'))

    def test_new_plugin_visible_only_when_enabled(self):
        self.install('qr-code')
        self.assertIn('qr-code',self.manager.known_ids())
        self.assertNotIn('qr-code',self.manager.enabled_ids())
        self.manager.select('qr-code','0.1.0',True)
        self.assertIn('qr-code',self.manager.enabled_ids())
        self.manager.set_enabled('qr-code',False)
        self.assertNotIn('qr-code',self.manager.enabled_ids())

    def test_install_does_not_execute_extension(self):
        self.install('qr-code')
        self.assertEqual(self.manager.versions('qr-code'),['0.1.0'])
        self.assertFalse(self.manager.is_enabled('qr-code'))

    def test_nested_dependencies_and_disable_guard(self):
        self.install('qr-code')
        self.install('qr-export',dependencies={'qr-code':'0.1.0'})
        with self.assertRaises(PluginError):
            self.manager.select('qr-export','0.1.0',True)
        self.manager.select('qr-code','0.1.0',True)
        self.manager.select('qr-export','0.1.0',True)
        self.assertTrue(self.manager.is_available('qr-export'))
        with self.assertRaises(PluginError):
            self.manager.set_enabled('qr-code',False)

    def test_cycle_in_corrupt_state_fails_closed(self):
        self.install('addon-a',dependencies={'addon-b':'0.1.0'})
        self.install('addon-b',dependencies={'addon-a':'0.1.0'})
        self.manager._save({'addon-a':{'version':'0.1.0','enabled':True},
                            'addon-b':{'version':'0.1.0','enabled':True}})
        self.assertFalse(self.manager.is_available('addon-a'))

    def test_load_plugin_registers_settings_without_hardcoding(self):
        self.install('qr-code')
        self.manager.select('qr-code','0.1.0',True)
        class Editor:
            plugin_manager=self.manager
        host=PluginHost(Editor())
        self.assertTrue(load_plugin(self.manager,'qr-code',host))
        self.assertIn('qr-code',host.settings_factories)
        self.assertEqual(host._loading_plugin_id,None)
        self.assertIsNone(host._loading_manager)
        # Plugins cannot register new pages when no loader is active.
        with self.assertRaisesRegex(PluginError, 'outside the active loader'):
            host.register_preferences_page('qr-code', 'Late', lambda x: None)

    def test_malicious_plugin_cannot_impersonate_ocr(self):
        self.install('qr-code')
        self.manager.select('qr-code','0.1.0',True)
        path=self.manager.root/'qr-code'/'0.1.0'/'main.py'
        path.write_text("def register(host):\n    host.register_preferences_page('ocr','Fake',lambda x: None)\n")
        class Editor:
            plugin_manager=self.manager
        host=PluginHost(Editor())
        with self.assertRaisesRegex(PluginError,'another ID'):
            load_plugin(self.manager,'qr-code',host)
        self.assertEqual(host.settings_factories,{})
        self.assertIsNone(host._loading_plugin_id)

    def test_uninstalled_plugin_is_not_discovered(self):
        self.install('qr-code')
        self.manager.select('qr-code','0.1.0',True)
        self.manager.uninstall('qr-code','0.1.0')
        self.assertNotIn('qr-code',self.manager.known_ids())

    def test_unknown_official_release_id_can_be_discovered(self):
        name='SnapMark-qr-code-0.1.0.zip'
        prefix='https://github.com/yanjing-chen/SnapMark/releases/download/qr-code-v0.1.0/'
        records=[{'tag_name':'qr-code-v0.1.0','assets':[
            {'name':name,'browser_download_url':prefix+name},
            {'name':name+'.sha256','browser_download_url':prefix+name+'.sha256'}]}]
        with patch('snapmark.plugins._http_bytes',return_value=json.dumps(records).encode()):
            found=available_releases('qr-code')
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]['id'],'qr-code')

    def test_nav_plugin_settings_registration_is_dynamic(self):
        root=Path(__file__).resolve().parents[1]
        nav=(root/'snapmark/preferences_sidebar_c2e.py').read_text()
        editor=(root/'snapmark/editor.py').read_text()
        ui=(root/'snapmark/plugin_ui.py').read_text()
        self.assertIn('def populate_plugins(',nav)
        self.assertIn('navigation.populate_plugins(registered)',editor)
        self.assertIn('self.manager.known_ids()',ui)
        self.assertIn("'ai-runtime'",nav)
        self.assertIn("'shortcuts'",nav)

if __name__=='__main__':
    unittest.main()
