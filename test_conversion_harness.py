"""Focused regression checks; no model requests or FPGA toolchain required."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import codex_run
import evald


class HarnessTests(unittest.TestCase):
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
                                         stop, root / 'convert.log')
            self.assertEqual(code, 124)
            self.assertEqual(result['status'], 'token_limit')
            self.assertEqual(result['weighted_tokens'], 155)
            self.assertIn('turn/interrupt', (root / 'agent_events.jsonl').read_text())

    def test_archive_and_original_reference(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            project, conversion = root / 'source', root / 'conversion'
            project.mkdir(); (conversion / 'rtl').mkdir(parents=True)
            (conversion / 'python').mkdir()
            (project / 'main.py').write_text('original')
            (conversion / 'python' / 'main.py').write_text('modified')
            (conversion / 'rtl' / 'top.sv').write_text('module top; endmodule')
            recorder = evald.Recorder(project, conversion / 'rtl')
            with patch.object(evald, 'evaluate', return_value=(0, 'bits of precision: inf\n')) as run:
                reply = recorder.evaluate('sim', [], 'original')
                self.assertEqual(run.call_args.args[1], [str(project)])
            archive = conversion / reply['record']['archive']
            self.assertEqual((archive / 'original_reference' / 'main.py').read_text(), 'original')
            self.assertEqual((archive / 'python' / 'main.py').read_text(), 'modified')
            self.assertTrue(reply['record']['exact'])
            self.assertIn('rtl/top.sv', json.loads((archive / 'manifest.json').read_text()))

    def test_agent_cannot_override_reference(self):
        reply = evald.handle({'tool': 'sim', 'args': ['/some/oracle']}, Path('/source'), Path('/rtl'))
        self.assertEqual(reply['exit'], 2)


if __name__ == '__main__':
    unittest.main()
