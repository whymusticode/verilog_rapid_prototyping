"""Run all tests and optionally write a machine-readable verification report."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import unittest

root = Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tests'))
from oracle import Oracle

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report',type=Path,help='Write JSON results to this path')
args = parser.parse_args()
called = Counter()
package_prefix = str(root/'turbo_3gpp')


def profile(frame,event,arg):
    if event == 'call' and frame.f_code.co_filename.startswith(package_prefix):
        called[Path(frame.f_code.co_filename).name+':'+frame.f_code.co_qualname] += 1


start = time.monotonic()
suite = unittest.defaultTestLoader.discover(str(root/'tests'))
sys.setprofile(profile)
try:
    result = unittest.TextTestRunner(verbosity=2).run(suite)
finally:
    sys.setprofile(None)
report = dict(success=result.wasSuccessful(),tests=result.testsRun,
              failures=len(result.failures),errors=len(result.errors),
              elapsed_seconds=round(time.monotonic()-start,3),
              seed=int(os.environ.get('FUZZ_SEED','20260909')),
              fuzz_cases=int(os.environ.get('FUZZ_CASES','16')),
              python=platform.python_version(),
              octave=subprocess.run(['octave','--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0],
              octave_processes=Oracle.processes,
              numerical_comparisons=dict(sorted(Oracle.comparisons.items())),
              total_numerical_comparisons=sum(Oracle.comparisons.values()),
              python_function_calls=dict(sorted(called.items())))
if args.report:
    args.report.write_text(json.dumps(report,indent=2)+'\n')
sys.exit(0 if result.wasSuccessful() else 1)
