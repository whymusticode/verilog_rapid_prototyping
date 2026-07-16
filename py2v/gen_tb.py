"""Generate tb.cpp deterministically from manifest.json + params.yaml.

The LLM is told to use these exact type/variable names in kernel.h:
  - Scalars:    in{N}_t, out{N}_t
  - Complex:    in{N}_t (struct with .re / .im), out{N}_t
  - Arrays:     in{N}[D0][D1]..., out{N}[D0][D1]...
  - Dimensions: DIM_IN{N}_0, DIM_IN{N}_1, ... (only for non-scalar tensors)

tb.cpp reads call index 0 from the IO files, invokes kernel_top, writes
outputs to the sim directory, and writes clock_cycles.txt using the value
of the last integer output (which is conventionally the iteration count).
"""
import json, math
from pathlib import Path


def _c_dim_macros(tensors):
    """Return lines defining DIM_IN/OUT_N_D macros for non-scalar tensors."""
    lines = []
    for t in tensors:
        if not t["shape"]:
            continue
        role = t["role"].upper()
        idx  = t["_idx"]
        for d, sz in enumerate(t["shape"]):
            lines.append(f"#define DIM_{role}{idx}_{d} {sz}")
    return lines


def _declare(t):
    """C declaration for a tensor variable."""
    role = t["role"]
    idx  = t["_idx"]
    typ  = f"{role}{idx}_t"
    name = f"{role}{idx}"
    if not t["shape"]:
        return f"    {typ} {name};"
    dims = "".join(f"[DIM_{role.upper()}{idx}_{d}]" for d in range(len(t["shape"])))
    return f"    {typ} {name}{dims};"


def _read_block(t, io_dir_var):
    """C block that reads tensor from its flat text file."""
    role  = t["role"]
    idx   = t["_idx"]
    fname = t["file"]
    name  = f"{role}{idx}"
    typ   = f"{role}{idx}_t"
    lines = [
        f"    {{",
        f'        FILE *fp = fopen({io_dir_var}"{fname}", "r");',
        f'        if (!fp) {{ fprintf(stderr, "Cannot open {fname}\\n"); return 1; }}',
    ]
    if not t["shape"]:
        if t["complex"]:
            lines += [
                f"        double _re = 0, _im = 0;",
                f'        if (fscanf(fp, "%lf %lf", &_re, &_im) != 2) {{ fprintf(stderr, "Parse error {fname}\\n"); fclose(fp); return 1; }}',
                f"        {name}.re = ({typ.replace('_t','_re_t')})_re;",
                f"        {name}.im = ({typ.replace('_t','_im_t')})_im;",
            ]
        else:
            lines += [
                f"        double _v = 0;",
                f'        if (fscanf(fp, "%lf", &_v) != 1) {{ fprintf(stderr, "Parse error {fname}\\n"); fclose(fp); return 1; }}',
                f"        {name} = ({typ})_v;",
            ]
    else:
        # Flatten nested loops over shape
        shape = t["shape"]
        indent = "        "
        loop_vars = [f"_i{d}" for d in range(len(shape))]
        for d, (var, sz) in enumerate(zip(loop_vars, shape)):
            lines.append(f"{indent}for (int {var} = 0; {var} < DIM_{role.upper()}{idx}_{d}; {var}++) {{")
            indent += "    "
        subscript = "".join(f"[{v}]" for v in loop_vars)
        if t["complex"]:
            lines += [
                f"{indent}double _re = 0, _im = 0;",
                f'{indent}if (fscanf(fp, "%lf %lf", &_re, &_im) != 2) {{ fprintf(stderr, "Parse error {fname}\\n"); fclose(fp); return 1; }}',
                f"{indent}{name}{subscript}.re = _re;",
                f"{indent}{name}{subscript}.im = _im;",
            ]
        else:
            lines += [
                f"{indent}double _v = 0;",
                f'{indent}if (fscanf(fp, "%lf", &_v) != 1) {{ fprintf(stderr, "Parse error {fname}\\n"); fclose(fp); return 1; }}',
                f"{indent}{name}{subscript} = ({typ})_v;",
            ]
        for _ in shape:
            indent = indent[4:]
            lines.append(f"{indent}}}")
    lines += [
        f"        fclose(fp);",
        f"    }}",
    ]
    return lines


def _write_block(t, sim_dir_var):
    """C block that writes tensor to its flat text file."""
    role  = t["role"]
    idx   = t["_idx"]
    fname = t["file"]
    name  = f"{role}{idx}"
    lines = [
        f"    {{",
        f'        FILE *fp = fopen({sim_dir_var}"{fname}", "w");',
        f'        if (!fp) {{ fprintf(stderr, "Cannot open {fname}\\n"); return 1; }}',
    ]
    if not t["shape"]:
        if t["complex"]:
            lines.append(f'        fprintf(fp, "%.17g %.17g\\n", (double){name}.re, (double){name}.im);')
        else:
            lines.append(f'        fprintf(fp, "%.17g\\n", (double){name});')
    else:
        shape = t["shape"]
        indent = "        "
        loop_vars = [f"_i{d}" for d in range(len(shape))]
        for d, (var, sz) in enumerate(zip(loop_vars, shape)):
            lines.append(f"{indent}for (int {var} = 0; {var} < DIM_{role.upper()}{idx}_{d}; {var}++) {{")
            indent += "    "
        subscript = "".join(f"[{v}]" for v in loop_vars)
        if t["complex"]:
            lines.append(f'{indent}fprintf(fp, "%.17g %.17g\\n", (double){name}{subscript}.re, (double){name}{subscript}.im);')
        else:
            lines.append(f'{indent}fprintf(fp, "%.17g\\n", (double){name}{subscript});')
        for _ in shape:
            indent = indent[4:]
            lines.append(f"{indent}}}")
    lines += [
        f"        fclose(fp);",
        f"    }}",
    ]
    return lines


def generate(manifest, io_dir, sim_dir):
    """Return tb.cpp source as a string."""
    # Tag each tensor with its per-role index
    in_idx = out_idx = 0
    tensors = []
    for t in manifest["tensors"]:
        t = dict(t)
        if t["role"] == "in":
            t["_idx"] = in_idx; in_idx += 1
        else:
            t["_idx"] = out_idx; out_idx += 1
        tensors.append(t)

    inputs  = [t for t in tensors if t["role"] == "in"]
    outputs = [t for t in tensors if t["role"] == "out"]

    # Find a scalar integer output to use as clock_cycles proxy (last scalar int out)
    clock_proxy = None
    for t in reversed(outputs):
        if not t["complex"] and not t["shape"] and "int" in t["dtype"]:
            clock_proxy = f"out{t['_idx']}"
            break

    io_dir_str  = str(io_dir).rstrip("/") + "/"
    sim_dir_str = str(sim_dir).rstrip("/") + "/"

    L = []
    L.append('#include <cstdio>')
    L.append('#include <cstdlib>')
    L.append('#include "kernel.h"')
    L.append('')
    L.append(f'static const char IO_DIR[]  = "{io_dir_str}";')
    L.append(f'static const char SIM_DIR[] = "{sim_dir_str}";')
    L.append('')

    dim_macros = _c_dim_macros(tensors)
    if dim_macros:
        L.extend(dim_macros)
        L.append('')

    L.append('int main()')
    L.append('{')

    for t in tensors:
        L.append(_declare(t))
    L.append('')

    for t in inputs:
        L.extend(_read_block(t, "IO_DIR "))
        L.append('')

    # Build kernel_top call arg list
    args = ", ".join(
        (f"out{t['_idx']}" if t["role"] == "out" and not t["shape"] and not t["complex"]
         else f"out{t['_idx']}" if t["role"] == "out"
         else f"in{t['_idx']}")
        for t in tensors
    )
    # outputs passed by reference if scalar
    call_args = []
    for t in tensors:
        n = f"{'in' if t['role']=='in' else 'out'}{t['_idx']}"
        if t["role"] == "out" and not t["shape"]:
            call_args.append(f"&{n}" if not t["complex"] else n)
        else:
            call_args.append(n)
    L.append(f"    kernel_top({', '.join(call_args)});")
    L.append('')

    for t in outputs:
        L.extend(_write_block(t, "SIM_DIR "))
        L.append('')

    # Write clock_cycles.txt using the proxy scalar int output
    if clock_proxy:
        L.append('    {')
        L.append(f'        FILE *fp = fopen(SIM_DIR "clock_cycles.txt", "w");')
        L.append(f'        if (fp) {{ fprintf(fp, "%llu\\n", (unsigned long long){clock_proxy}); fclose(fp); }}')
        L.append('    }')
        L.append('')

    L.append('    return 0;')
    L.append('}')

    return "\n".join(L) + "\n"


if __name__ == "__main__":
    import sys, yaml
    conv = Path(sys.argv[1]).resolve()
    params = yaml.safe_load((conv / "params.yaml").read_text()) or {}
    name = params["name"]
    io_dir = conv / f"{name}_io"
    sim_dir = conv / "build" / "sim"
    manifest = json.loads((io_dir / "manifest.json").read_text())
    out = generate(manifest, io_dir, sim_dir)
    dst = conv / "build" / "hls" / "tb.cpp"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out)
    print(f"wrote {dst}")
    print(out)
