#!/usr/bin/env bash
set -euo pipefail

python3 scripts/regression.py
python3 -m py_compile host/fixed23.py host/evd_host.py scripts/regression.py scripts/check_utilization.py

echo "python_checks_pass"
