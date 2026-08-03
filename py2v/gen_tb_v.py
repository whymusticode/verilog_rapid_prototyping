"""Generate tb.sv deterministically from manifest.json + params.yaml.

Mirrors gen_tb.py's role for the HLS-C path, but for the Verilog path: the LLM
never writes its own testbench, so it can neither fudge clock_cycles nor the
I/O comparison. tb.sv:
  - drives a real clock at params.yaml's clock.freq_hz
  - drives rst per params.yaml's reset block, then pulses start
  - counts real clock edges while kernel_top's `busy` is asserted -> clock_cycles.txt
    (this is a genuine measurement, not a proxy -- see PoC/count_cycles/)
  - reads inputs from / writes outputs to the same flat .txt files gen_tb.py
    uses, so util.compare() needs no changes

Fixed-point values are packed as plain two's-complement integers scaled by
2**fraction (see params.yaml's per-tensor "fraction" field) into flat
signed/unsigned buses. Array elements are packed row-major, low-to-high:
element [i0][i1] occupies bit offset (i0*DIM_1 + i1)*W. Complex elements pack
.re then .im, each of the scalar component width, so a complex tensor's flat
bus is 2x as wide per element as an equivalently-shaped real tensor.
"""
import json
from pathlib import Path


def _bits_for(t, params, role_key):
    """Look up (bits, signed, fraction) for a tensor from params.yaml's input/output block."""
    keys = list((params.get(role_key) or {}).keys())
    idx = t["_idx"]
    if idx < len(keys):
        spec = params[role_key][keys[idx]]
        return int(spec.get("bits", 16)), bool(spec.get("signed", 1)), int(spec.get("fraction", 0))
    return 16, True, 0


def _elem_width(t, params):
    role_key = "input" if t["role"] == "in" else "output"
    bits, signed, fraction = _bits_for(t, params, role_key)
    w = bits + (1 if signed else 0)
    return w, signed, fraction


def _total_width(t, params):
    w, signed, fraction = _elem_width(t, params)
    n = 1
    for d in t["shape"]:
        n *= d
    mult = 2 if t["complex"] else 1
    return w * mult * n, w, signed, fraction


def _dim_defines(tensors):
    lines = []
    for t in tensors:
        if not t["shape"]:
            continue
        role = t["role"].upper()
        idx = t["_idx"]
        for d, sz in enumerate(t["shape"]):
            lines.append(f"`define DIM_{role}{idx}_{d} {sz}")
    return lines


def _port_decl(t, params, direction):
    total_w, elem_w, signed, fraction = _total_width(t, params)
    name = f"{t['role']}{t['_idx']}"
    sign = "signed " if signed else ""
    kind = "reg" if direction == "output" else "wire"
    return f"    {direction} {kind} {sign}[{total_w - 1}:0] {name},"


def _elem_count(t):
    n = 1
    for d in t["shape"]:
        n *= d
    return n


def _read_block(t, params, io_dir_var):
    """SV block: read tensor's flat text file, pack into its bus register."""
    role = t["role"]
    idx = t["_idx"]
    fname = t["file"]
    name = f"{role}{idx}"
    total_w, elem_w, signed, fraction = _total_width(t, params)
    n = _elem_count(t)
    scale = f"real'({1 << fraction})" if fraction else "1.0"

    lines = [
        f'    fd = $fopen({{{io_dir_var}, "{fname}"}}, "r");',
        f'    if (fd == 0) begin $display("Cannot open {fname}"); $finish; end',
    ]
    if n == 1 and not t["complex"]:
        lines += [
            f"    r = $fscanf(fd, \"%f\", rv);",
            f"    {name} = $rtoi(rv * {scale});",
        ]
    elif n == 1 and t["complex"]:
        lines += [
            f"    r = $fscanf(fd, \"%f %f\", rv, iv);",
            f"    {name} = {{$rtoi(rv * {scale})[{elem_w-1}:0], $rtoi(iv * {scale})[{elem_w-1}:0]}};",
        ]
    else:
        lines.append(f"    for (idx_i = 0; idx_i < {n}; idx_i = idx_i + 1) begin")
        if t["complex"]:
            lines += [
                f'        r = $fscanf(fd, "%f %f", rv, iv);',
                f"        {name}[(idx_i*2+1)*{elem_w}-1 -: {elem_w}] = $rtoi(rv * {scale});",
                f"        {name}[(idx_i*2+2)*{elem_w}-1 -: {elem_w}] = $rtoi(iv * {scale});",
            ]
        else:
            lines += [
                f'        r = $fscanf(fd, "%f", rv);',
                f"        {name}[(idx_i+1)*{elem_w}-1 -: {elem_w}] = $rtoi(rv * {scale});",
            ]
        lines.append("    end")
    lines.append("    $fclose(fd);")
    return lines


def _write_block(t, params, sim_dir_var):
    """SV block: write tensor's bus register out to its flat text file.

    Uses a per-tensor exact-width signed scratch reg for slices so $signed()
    sign-extends from the correct bit position -- a shared wider scratch reg
    would zero-extend the slice on assignment and silently corrupt negative
    values (verified: passing -3.0 through a 17-bit signed slice into a
    64-bit scratch reg round-tripped as +509 before this fix).
    """
    role = t["role"]
    idx = t["_idx"]
    fname = t["file"]
    name = f"{role}{idx}"
    total_w, elem_w, signed, fraction = _total_width(t, params)
    n = _elem_count(t)
    inv_scale = f"real'({1 << fraction})" if fraction else "1.0"
    cast = "$signed" if signed else ""
    re_r = f"{name}_re_r"
    im_r = f"{name}_im_r"

    lines = [
        f'    fd = $fopen({{{sim_dir_var}, "{fname}"}}, "w");',
        f'    if (fd == 0) begin $display("Cannot open {fname}"); $finish; end',
    ]
    if n == 1 and not t["complex"]:
        lines.append(f'    $fwrite(fd, "%.17g\\n", real\'({cast}({name})) / {inv_scale});')
    elif n == 1 and t["complex"]:
        lines += [
            f"    {re_r} = {name}[{total_w-1}:{elem_w}];",
            f"    {im_r} = {name}[{elem_w-1}:0];",
            f'    $fwrite(fd, "%.17g %.17g\\n", real\'({cast}({re_r})) / {inv_scale}, real\'({cast}({im_r})) / {inv_scale});',
        ]
    else:
        lines.append(f"    for (idx_i = 0; idx_i < {n}; idx_i = idx_i + 1) begin")
        if t["complex"]:
            lines += [
                f"        {re_r} = {name}[(idx_i*2+1)*{elem_w}-1 -: {elem_w}];",
                f"        {im_r} = {name}[(idx_i*2+2)*{elem_w}-1 -: {elem_w}];",
                f'        $fwrite(fd, "%.17g %.17g\\n", real\'({cast}({re_r})) / {inv_scale}, real\'({cast}({im_r})) / {inv_scale});',
            ]
        else:
            lines += [
                f"        {re_r} = {name}[(idx_i+1)*{elem_w}-1 -: {elem_w}];",
                f'        $fwrite(fd, "%.17g\\n", real\'({cast}({re_r})) / {inv_scale});',
            ]
        lines.append("    end")
    lines.append("    $fclose(fd);")
    return lines


def _write_scratch_decls(t, params):
    """Per-tensor exact-width signed scratch regs used only by _write_block for slicing."""
    if t["role"] != "out":
        return []
    total_w, elem_w, signed, fraction = _total_width(t, params)
    n = _elem_count(t)
    if n == 1 and not t["complex"]:
        return []
    name = f"{t['role']}{t['_idx']}"
    sign = "signed " if signed else ""
    if t["complex"]:
        return [f"    reg {sign}[{elem_w-1}:0] {name}_re_r, {name}_im_r;"]
    return [f"    reg {sign}[{elem_w-1}:0] {name}_re_r;"]


def generate(manifest, params, io_dir, sim_dir):
    """Return tb.sv source as a string."""
    in_idx = out_idx = 0
    tensors = []
    for t in manifest["tensors"]:
        t = dict(t)
        if t["role"] == "in":
            t["_idx"] = in_idx; in_idx += 1
        else:
            t["_idx"] = out_idx; out_idx += 1
        tensors.append(t)

    inputs = [t for t in tensors if t["role"] == "in"]
    outputs = [t for t in tensors if t["role"] == "out"]

    clk_hz = float(params.get("clock", {}).get("freq_hz", 200e6))
    period_ns = 1.0e9 / clk_hz
    reset = params.get("reset", {}) or {}
    active_high = str(reset.get("active_level", "high")).lower() != "low"

    io_dir_str = str(io_dir).rstrip("/") + "/"
    sim_dir_str = str(sim_dir).rstrip("/") + "/"

    L = []
    L.append('`timescale 1ns/1ps')
    L.append('`include "kernel.h.sv"')
    L.append('')
    L.append('module tb;')
    L.append(f'    localparam IO_DIR  = "{io_dir_str}";')
    L.append(f'    localparam SIM_DIR = "{sim_dir_str}";')
    L.append('')
    L.append('    reg clk = 0;')
    L.append(f'    reg rst = {"1" if active_high else "0"};')
    L.append('    reg start = 0;')
    L.append('    wire busy, done;')
    L.append('')
    L.append('    integer fd, r, idx_i;')
    L.append('    real rv, iv;')
    L.append('    reg [63:0] cycle_count;')
    L.append('')

    for t in tensors:
        total_w, elem_w, signed, fraction = _total_width(t, params)
        sign = "signed " if signed else ""
        L.append(f"    reg  {sign}[{total_w - 1}:0] {t['role']}{t['_idx']};" if t["role"] == "in"
                  else f"    wire {sign}[{total_w - 1}:0] {t['role']}{t['_idx']};")
    for t in outputs:
        L.extend(_write_scratch_decls(t, params))
    L.append('')

    L.append(f'    always #{period_ns / 2:.6f} clk = ~clk;')
    L.append('')

    args = ", ".join(f".{t['role']}{t['_idx']}({t['role']}{t['_idx']})" for t in tensors)
    L.append('    kernel_top uut (')
    L.append('        .clk(clk), .rst(rst), .start(start), .busy(busy), .done(done),')
    L.append(f'        {args}')
    L.append('    );')
    L.append('')

    L.append('    always @(posedge clk) begin')
    L.append('        if (rst) cycle_count <= 0;')
    L.append('        else if (busy) cycle_count <= cycle_count + 1;')
    L.append('    end')
    L.append('')

    L.append('    initial begin')
    L.append('        cycle_count = 0;')
    for t in inputs:
        L.extend("        " + ln for ln in _read_block(t, params, "IO_DIR"))
    L.append('')
    L.append(f'        @(negedge clk); rst = {"0" if active_high else "1"};')
    L.append('        @(negedge clk); start = 1;')
    L.append('        @(negedge clk); start = 0;')
    L.append('')
    L.append('        wait (done);')
    L.append('        @(negedge clk);')
    L.append('')
    L.append('        if (cycle_count == 0) begin')
    L.append('            $display("CHEAT: busy was never asserted between start and done -- clock_cycles must be >= 1");')
    L.append('            $finish;')
    L.append('        end')
    L.append('')
    for t in outputs:
        L.extend("        " + ln for ln in _write_block(t, params, "SIM_DIR"))
    L.append('')
    L.append('        fd = $fopen({SIM_DIR, "clock_cycles.txt"}, "w");')
    L.append('        $fwrite(fd, "%0d\\n", cycle_count);')
    L.append('        $fclose(fd);')
    L.append('')
    L.append('        $display("SIM_DONE cycle_count=%0d", cycle_count);')
    L.append('        $finish;')
    L.append('    end')
    L.append('endmodule')

    dim_defines = _dim_defines(tensors)
    header = []
    if dim_defines:
        header.extend(dim_defines)
        header.append('')

    return "\n".join(header + L) + "\n"


if __name__ == "__main__":
    import sys, yaml
    conv = Path(sys.argv[1]).resolve()
    params = yaml.safe_load((conv / "params.yaml").read_text()) or {}
    name = params["name"]
    io_dir = conv / f"{name}_io"
    sim_dir = conv / "build" / "sim"
    manifest = json.loads((io_dir / "manifest.json").read_text())
    out = generate(manifest, params, io_dir, sim_dir)
    dst = conv / "build" / "hls" / "tb.sv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out)
    print(f"wrote {dst}")
    print(out)
