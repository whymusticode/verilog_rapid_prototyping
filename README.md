# Verilog Rapid Prototyping

A collection of FPGA designs targeting the Digilent Basys3 board (Xilinx Artix-7).

## Projects

| Directory | Description |
|-----------|-------------|
| `evd_10x10/` | Eigenvalue decomposition (Jacobi algorithm) for 10×10 complex Hermitian matrices |
| `matmul_10x10/` | 10×10 complex matrix multiply |
| `ov7670/` | OV7670 camera interface with VGA output |
| `demo/` | CORDIC demo |

## Verifying the Verilog

You can verify the `evd_10x10` design using open-source tools that work on any Linux distro (and macOS).

### Install dependencies

**Debian/Ubuntu:**
```bash
sudo apt-get install iverilog yosys python3-numpy
```

**Fedora/RHEL:**
```bash
sudo dnf install iverilog yosys python3-numpy
```

**Arch Linux:**
```bash
sudo pacman -S iverilog yosys python-numpy
```

**macOS (Homebrew):**
```bash
brew install icarus-verilog yosys numpy
```

### Run the simulation (iverilog)

Run from the repository root:

```bash
bash evd_10x10/sim_iverilog.sh
```

This:
1. Compiles all RTL and the testbench with `iverilog`
2. Runs the simulation with `vvp`, producing `evd_10x10/sim/sim_diag_out.txt`
3. Compares the simulation output against the Python reference (`compare_one_iter.py`)

Expected output ending with:
```
compare_pass one_iteration_match worst_abs_err=<N>
```

### Check synthesizability (yosys)

Run from the repository root:

```bash
bash evd_10x10/synth_check_yosys.sh
```

This runs a full generic synthesis pass with `yosys` and prints a resource utilization report. A successful run ends with:
```
=== Synthesis check passed ===
```

### Targeting actual hardware (Xilinx Vivado)

See `basys3.md` for board details. Use the `build.tcl` and `program.tcl` scripts inside each project directory with Vivado 2024.1:

```bash
cd evd_10x10
vivado -mode batch -source build.tcl
vivado -mode batch -source program.tcl
```
