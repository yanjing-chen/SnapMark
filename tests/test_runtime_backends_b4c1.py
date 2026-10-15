"""No writes to a real Runtime; all HTTP is mocked."""
import unittest
from unittest.mock import patch
from snapmark import runtime_backends_b4 as b
from snapmark.ai_runtime import RuntimeIntegrationError

ENDPOINT = 'http://127.0.0.1:8111'
HEALTH = {'service':'local-ai-runtime','runtime_version':'1.0.0',
          'backend_running':False,'current_model':None,'active_backend':None}
OP = {'state':'idle','job_id':None}
OK_STATUS = {'current':'llama-d8123504-r1', 'previous':None, 'operation':OP}
CUDA_STATUS = {'current':None,'previous':None,'operation':OP}
PREF = {'backend_preference':'auto','idle_unload_seconds':300}
BACKENDS = {'availability':{'cpu':{'installed':True,'usable':True},
                           'vulkan':{'installed':True,'usable':True},
                           'cuda':{'installed':False,'usable':False}}}


class RuntimeBackendsB4C1Tests(unittest.TestCase):
    def routes(self, endpoint, route, timeout):
        return {'/health':HEALTH, '/v1/runtime/backends':BACKENDS,
                '/v1/runtime/llama/status':OK_STATUS,
                '/v1/runtime/cuda/status':CUDA_STATUS,
                '/v1/runtime/preferences':PREF}[route]

    @patch.object(b, '_read_json')
    def test_snapshot_read_only_and_real_vs_available(self, read):
        read.side_effect = self.routes
        result = b.read_overview(ENDPOINT)
        self.assertEqual(result.active_backend, '')
        self.assertFalse(result.backend_running)
        self.assertTrue(result.available['vulkan']['usable'])
        self.assertEqual(result.idle_seconds,300)
        self.assertEqual(result.llama['current'],'llama-d8123504-r1')
        self.assertEqual(read.call_count,5)

    @patch.object(b, '_read_json')
    def test_reject_08(self, read):
        read.return_value = dict(HEALTH,runtime_version='0.8.0')
        with self.assertRaisesRegex(RuntimeIntegrationError,'1.0.0'):
            b.read_overview(ENDPOINT)

    @patch.object(b, '_read_json')
    def test_reject_imposter_service(self, read):
        read.return_value = dict(HEALTH,service='different-service')
        with self.assertRaisesRegex(RuntimeIntegrationError,'not Local AI Runtime'):
            b.read_overview(ENDPOINT)

    @patch.object(b,'_post')
    def test_no_writes_without_explicit_consent(self, post):
        for callable_, args in ((b.change_preference,('vulkan',)),
                                (b.install_backend,('llama',)),
                                (b.rollback_backend,('cuda',))):
            with self.assertRaises(RuntimeIntegrationError):
                callable_(ENDPOINT,*args)
        post.assert_not_called()

    @patch.object(b, '_post')
    def test_input_validation(self, post):
        with self.assertRaises(RuntimeIntegrationError):
            b.install_backend(ENDPOINT,'bad',confirmed=True)
        with self.assertRaises(RuntimeIntegrationError):
            b.change_preference(ENDPOINT,'gpu',confirmed=True)
        with self.assertRaises(RuntimeIntegrationError):
            b.rollback_backend(ENDPOINT,'anything',confirmed=True)
        post.assert_not_called()

    @patch.object(b, '_post')
    @patch.object(b, '_read_json')
    def test_write_preference_only_with_confirmation_and_readback(self, read, post):
        def side(endpoint,route,timeout):
            if route=='/health':return HEALTH
            if route=='/v1/runtime/preferences':return {'backend_preference':'vulkan'}
        read.side_effect=side
        post.return_value={'backend_preference':'vulkan','backend_changed':True}
        with self.assertRaisesRegex(RuntimeIntegrationError,'changed'):
            b.change_preference(ENDPOINT,'cuda',confirmed=True,expected='auto')
        post.assert_not_called()

    @patch.object(b, '_post')
    @patch.object(b, '_read_json')
    def test_write_preference_request_payload(self, read, post):
        sequence=[HEALTH, PREF, dict(PREF,backend_preference='vulkan')]
        read.side_effect=sequence
        post.return_value={'backend_changed':True}
        b.change_preference(ENDPOINT,'vulkan',confirmed=True,expected='auto')
        self.assertEqual(post.call_args.args[2],{'backend_preference':'vulkan'})

    @patch.object(b, '_post')
    @patch.object(b, '_read_json')
    def test_install_202_async_job_id(self, read, post):
        read.return_value=HEALTH
        post.return_value={'accepted':True,'operation':{'state':'running','job_id':'abc'}}
        operation=b.install_backend(ENDPOINT,'cuda',confirmed=True)
        self.assertEqual(operation['job_id'],'abc')
        self.assertEqual(post.call_args.args[1],'/v1/runtime/cuda/install')
        self.assertEqual(post.call_args.args[2],{})
        self.assertEqual(post.call_args.args[3],(202,))

    @patch.object(b, '_post')
    @patch.object(b, '_read_json')
    def test_install_reject_unconfirmed_response(self, read, post):
        read.return_value=HEALTH
        post.return_value={'accepted':False,'operation':{}}
        with self.assertRaisesRegex(RuntimeIntegrationError,'did not confirm'):
            b.install_backend(ENDPOINT,'llama',confirmed=True)

    @patch.object(b, '_post')
    @patch.object(b, '_read_json')
    def test_rollback_route(self, read, post):
        read.return_value=HEALTH
        post.return_value={'rolled_back':True}
        b.rollback_backend(ENDPOINT,'llama',confirmed=True)
        self.assertEqual(post.call_args.args[1],'/v1/runtime/llama/rollback')

    @patch.object(b, '_read_json')
    def test_poll_success(self, read):
        read.side_effect=[{'operation':{'job_id':'a','state':'running','phase':'download'}},
                          {'operation':{'job_id':'a','state':'success','phase':'complete'}}]
        phases=[]
        result=b.wait_install(ENDPOINT,'cuda','a',progress=lambda x: phases.append(x['phase']),
                              sleeper=lambda _:None)
        self.assertEqual(phases,['download','complete'])
        self.assertEqual(result['operation']['state'],'success')

    @patch.object(b, '_read_json')
    def test_poll_error(self, read):
        read.return_value={'operation':{'job_id':'a','state':'error','error':'checksum failed'}}
        with self.assertRaisesRegex(RuntimeIntegrationError,'checksum failed'):
            b.wait_install(ENDPOINT,'llama','a',sleeper=lambda _:None)

    @patch.object(b, '_read_json')
    def test_poll_refuses_other_job(self, read):
        read.return_value={'operation':{'job_id':'another','state':'success'}}
        with self.assertRaisesRegex(RuntimeIntegrationError,'identity changed'):
            b.wait_install(ENDPOINT,'cuda','a',sleeper=lambda _:None)

    @patch.object(b, '_read_json')
    def test_poll_timeout(self, read):
        read.return_value={'operation':{'job_id':'a','state':'running'}}
        with self.assertRaisesRegex(RuntimeIntegrationError,'still running'):
            b.wait_install(ENDPOINT,'cuda','a',timeout=-1,sleeper=lambda _:None)


class B4C1UIContracts(unittest.TestCase):
    def test_distinct_shared_preference(self):
        from pathlib import Path
        source=(Path(__file__).parents[1]/'snapmark/ai_runtime_ui.py').read_text()
        self.assertIn('Shared Runtime backend preference',source)
        self.assertIn('BACKEND_PREFERENCES[self.widgets[\'b4_choice\'].get_selected()]',source)
        self.assertIn('Change the shared Runtime backend preference?',source)
        self.assertIn('confirmed=True, expected=expected',source)
        self.assertIn('Refresh backend status',source)
        self.assertIn('Detected backend availability', source)
