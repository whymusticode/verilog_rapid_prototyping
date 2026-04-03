#!/usr/bin/env bash
# Check that the evd_10x10 RTL is synthesizable using yosys (open-source, cross-platform).
# Must be run from the repository root:
#   bash evd_10x10/synth_check_yosys.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

RTL="evd_10x10/rtl"

echo "=== Checking synthesizability with yosys ==="
yosys -p "
  read_verilog -sv \
    $RTL/uart_rx.v \
    $RTL/uart_tx.v \
    $RTL/complex_mul_3dsp.v \
    $RTL/cmatmul10x10_dsp.v \
    $RTL/pivot_pairs_10x10.v \
    $RTL/jacobi_sweep10x10.v \
    $RTL/jacobi_engine10x10.v;
  hierarchy -check -top jacobi_engine10x10;
  proc;
  opt;
  synth -top jacobi_engine10x10;
  stat;
"
echo "=== Synthesis check passed ==="
