#!/usr/bin/env bash
# Compares iverilog vs xsim (Vivado Simulator) wall-clock time on the real
# eig_10 kernel (conversion_027, jacobi eigendecomposition, 10x10 complex),
# with THRESH patched unreachable (kernel_bench.sv) so the FSM runs sustained
# work for the full cycle budget instead of converging early and idling.
#
# Usage: ./run_bench.sh [N_CYCLES]
set -e
cd "$(dirname "$0")/eig10"

N_CYCLES="${1:-200000}"
sed -i "s/localparam N_CYCLES = [0-9]*;/localparam N_CYCLES = ${N_CYCLES};/" bench_tb.sv

echo "=== iverilog: compile + run, N_CYCLES=${N_CYCLES} ==="
rm -f bench_iv.out
iverilog -g2012 -I . -o bench_iv.out kernel_bench.sv bench_tb.sv 2>&1 | grep -vi truncated || true
time vvp bench_iv.out

echo
echo "=== xsim: compile + elaborate (one-time cost, not included in run timing) ==="
source ~/Xilinx/*/Vivado/settings64.sh 2>/dev/null
unset LIBRARY_PATH
rm -rf xsim.dir *.log *.jou *.pb *.wdb .Xil
xvlog -sv kernel_bench.sv bench_tb.sv > /dev/null
xelab -debug typical bench_tb -s eig10_bench > /dev/null

echo "=== xsim: run, N_CYCLES=${N_CYCLES} ==="
time xsim eig10_bench -runall 2>&1 | tail -6
