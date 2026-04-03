#!/usr/bin/env bash
# Run the evd_10x10 simulation using iverilog (open-source, cross-platform).
# Must be run from the repository root:
#   bash evd_10x10/sim_iverilog.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

RTL="evd_10x10/rtl"
SIM="evd_10x10/sim"

echo "=== Compiling with iverilog ==="
iverilog -g2012 -o "$SIM/tb_jacobi_engine_iverilog" \
    "$RTL/uart_rx.v" \
    "$RTL/uart_tx.v" \
    "$RTL/complex_mul_3dsp.v" \
    "$RTL/cmatmul10x10_dsp.v" \
    "$RTL/pivot_pairs_10x10.v" \
    "$RTL/jacobi_sweep10x10.v" \
    "$RTL/jacobi_engine10x10.v" \
    "$SIM/tb_jacobi_engine.v"

echo "=== Running simulation with vvp ==="
vvp "$SIM/tb_jacobi_engine_iverilog"

echo "=== Comparing output against Python reference ==="
python3 "$SIM/compare_one_iter.py"
