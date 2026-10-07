"""Focused regression checks; no model requests or FPGA toolchain required."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import claude_run
import codex_run
import evald


class HarnessTests(unittest.TestCase):
    def test_luna_api_cost_matches_default_weights(self):
        usage = codex_run.Usage(0, [1, 5, .1])
        point = usage.update({"inputTokens": 1000, "cachedInputTokens": 800, "outputTokens": 20})
        cost = codex_run.api_cost_estimate('gpt-6-luna', point)
        self.assertAlmostEqual(cost['usd'], point['weighted_tokens'] * .10 / 1_000_000)
        self.assertIsNone(codex_run.api_cost_estimate('unknown-model', point))

    def test_cached_input_is_not_double_counted(self):
        usage = codex_run.Usage(100, [1, 5, .1])
        point = usage.update({"inputTokens": 1000, "cachedInputTokens": 800, "outputTokens": 20})
        self.assertEqual(point["weighted_tokens"], 380)

    def test_budget_interrupts_and_keeps_events(self):
        server = '''import sys,json
def send(m): print(json.dumps(m),flush=True)
for line in sys.stdin:
 m=json.loads(line); method=m.get('method')
 if method=='initialize': send({'id':0,'result':{}})
 if method=='thread/start': send({'id':1,'result':{'thread':{'id':'thread'}}})
 if method=='turn/start':
  send({'method':'turn/started','params':{'turn':{'id':'turn'}}})
  send({'method':'thread/tokenUsage/updated','params':{'turnId':'turn','tokenUsage':{'total':{'inputTokens':100,'cachedInputTokens':50,'outputTokens':20}}}})
 if method=='turn/interrupt':
  send({'id':3,'result':{}})
  send({'method':'turn/completed','params':{'turn':{'status':'interrupted'}}})
  break
'''
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            def stop(p):
                p.terminate()
                p.wait(timeout=5)
            code, result = codex_run.run([sys.executable, '-u', '-c', server], root,
                                         'test', 'fake', codex_run.Usage(100, [1, 5, .1]),
                                         stop, root / 'convert.log', reasoning_effort='none')
            self.assertEqual(code, 124)
            self.assertEqual(result['status'], 'token_limit')
            self.assertEqual(result['weighted_tokens'], 155)
            self.assertIn('turn/interrupt', (root / 'agent_events.jsonl').read_text())
            events = [json.loads(line) for line in (root / 'agent_events.jsonl').read_text().splitlines()]
            start = next(e['message'] for e in events if e['message'].get('method') == 'thread/start')
            self.assertEqual(start['params']['config']['model_reasoning_effort'], 'none')
            self.assertEqual(result['requested_reasoning_effort'], 'none')

    def test_claude_budget_stops_and_dedupes_streamed_usage(self):
        agent = '''import json,time
def send(m): print(json.dumps(m),flush=True)
send({'type':'system','subtype':'init','model':'fake','session_id':'s'})
u={'input_tokens':10,'cache_creation_input_tokens':40,'cache_read_input_tokens':50,'output_tokens':4}
send({'type':'assistant','message':{'id':'a','content':[{'type':'text','text':'hi'}],'usage':u}})
send({'type':'assistant','message':{'id':'a','content':[{'type':'tool_use','name':'Bash','input':{'command':'sim'}}],'usage':u}})
send({'type':'assistant','message':{'id':'b','content':[],'usage':u}})
time.sleep(30)
'''
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            def stop(p):
                p.terminate()
                p.wait(timeout=5)
            code, result = claude_run.run([sys.executable, '-u', '-c', agent], root, 'the prompt',
                                          codex_run.Usage(150, [1, 5, .1]), stop,
                                          root / 'convert.log', reasoning_effort='high')
            self.assertEqual(code, 124)
            self.assertEqual(result['status'], 'token_limit')
            # Message 'a' counted once: 2 * (50 uncached + 5*4 output + 0.1*50 cached).
            self.assertEqual(result['weighted_tokens'], 150)
            self.assertEqual(result['effective_settings']['model'], 'fake')
            log = (root / 'convert.log').read_text()
            self.assertIn('hi', log)
            self.assertIn('> Bash: sim', log)
            self.assertIn('the prompt', (root / 'agent_events.jsonl').read_text())

    def test_evaluations_run_in_place_and_are_logged(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            project, conversion = root / 'source', root / 'conversion'
            project.mkdir(); (conversion / 'rtl').mkdir(parents=True)
            (project / 'main.py').write_text('original')
            (conversion / 'IO').mkdir()
            (conversion / 'IO' / 'planted').symlink_to(project / 'main.py')
            (conversion / 'rtl' / 'top.sv').write_text('module top; endmodule')
            recorder = evald.Recorder(project, conversion / 'rtl', log=conversion / 'convert.log')
            printed = 'throughput: 12.5 cycles/sample\nbits of precision: inf\n'
            with patch.object(evald, 'evaluate', return_value=(0, printed)) as run:
                reply = recorder.evaluate('sim', [], 'original')
                self.assertEqual(run.call_args.args[1], [str(project)])
                self.assertEqual(run.call_args.args[2], conversion / 'rtl')
            with patch.object(evald, 'evaluate', return_value=(1, 'x\ntop.sv:3: error: bad\n9 errors\n')):
                failed = recorder.evaluate('sim', [])
            self.assertFalse((conversion / 'IO' / 'planted').is_symlink())
            self.assertEqual((project / 'main.py').read_text(), 'original')
            self.assertFalse((conversion / 'evaluations').exists())
            self.assertTrue(reply['record']['exact'])
            self.assertEqual(reply['record']['cycles_per_sample'], 12.5)
            self.assertEqual(failed['record']['error'], 'top.sv:3: error: bad')
            self.assertEqual(len((conversion / 'evald.jsonl').read_text().splitlines()), 2)
            log = (conversion / 'convert.log').read_text()
            self.assertIn('cycles_per_sample=12.5', log)
            self.assertIn('error=top.sv:3: error: bad', log)

    def test_final_check_uses_only_original_reference(self):
        import convert
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            project, conversion = root / 'source', root / 'conversion'
            project.mkdir(); (conversion / 'rtl').mkdir(parents=True)
            (conversion / 'python').mkdir(); (conversion / 'IO').mkdir()
            (project / 'main.py').write_text('original')
            (conversion / 'python' / 'main.py').write_text('modified')
            (conversion / 'IO' / 'tb.sv').write_text('agent edited')
            (conversion / 'rtl' / 'top.sv').write_text('module top; endmodule')

            def fake(tool, extra, output):
                if tool == 'sim':
                    (output.parent / 'IO' / 'tb.sv').write_text('from original sim')
                    return 0, 'bits of precision: inf\n'
                self.assertEqual((output.parent / 'IO' / 'tb.sv').read_text(), 'from original sim')
                return 0, 'Fmax: 123.4\n'

            with patch.object(evald, 'evaluate', side_effect=fake) as run:
                convert.check_references(project, conversion / 'rtl', conversion,
                                         evald.Recorder(project, conversion / 'rtl'))
            self.assertEqual([call.args[0] for call in run.call_args_list], ['sim', 'synth'])
            self.assertEqual(run.call_args_list[0].args[1], [str(project)])
            self.assertIn('--implement', run.call_args_list[1].args[1])
            self.assertIn(str(project), run.call_args_list[1].args[1])
            log = (conversion / 'reference_check.log').read_text()
            self.assertIn('Changed Python/parameter files: main.py', log)

    def test_agent_cannot_override_reference(self):
        reply = evald.handle({'tool': 'sim', 'args': ['/some/oracle']}, Path('/source'), Path('/rtl'))
        self.assertEqual(reply['exit'], 2)


if __name__ == '__main__':
    unittest.main()
