# Python → Verilog LLM Translator — Scaffolding Design

Design doc for an LLM-driven tool that takes a NumPy-style Python algorithm and produces a Vivado bitstream for a target Xilinx part. Status: **design approved, not yet implemented**. Pick up from here.

## Context

The repo already contains one hand-built Python→Verilog translation (`projects/eig_10/eig_10.py` → `old/matrix_eig_10_fxp.m` → `ip_custom/evd_10x10/`). That manual flow is slow and hard to replay for new algorithms. Goal: an LLM-driven tool that automates end-to-end, while letting the LLM (a) plan with knowledge of existing IP + online research, (b) iterate against a faithful Python trace for debug, (c) work in an isolated build space that never mutates the project source, and (d) promote successful results back into `ip_custom/` as a first-class, reusable IP entry.

Initial target project is `projects/eig_10/` on `xc7a35tcpg236-1` (Basys3), reproducing the hand-built `ip_custom/evd_10x10/` result.

CLI shape: `python src/main.py projects/eig_10 -part xc7a35tcpg236-1`.

## Locked design decisions

- **Agent host**: native multi-provider tool loop (not wrapping claude-code CLI). Claude models get Anthropic's native `web_search_20250305` server tool; OpenAI gets `web_search_preview`; local/Ollama gets a Tavily shim or no-research mode.
- **Stage-2 instrumentation**: AST rewrite of every assignment via libcst (no LLM).
- **Debug-stage Python edits**: restricted to prints, asserts, and new pure helper functions — LLM may not rewrite existing algorithmic lines, so the reference can't drift to match wrong RTL.
- **Single LLM loop spans Stages 3/4/5**: RTL generation, sim-driven debug, *and* Vivado error-driven fixes all share the same tool loop and transcript. A Vivado synthesis/impl error is just another structured feedback signal, same shape as a sim mismatch.

## Directory layout (all new — `src/` is currently empty)

```
src/
  main.py                   # CLI entry; argparse; dispatches orchestrator
  orchestrator.py           # Stage sequencer + cost guards + resume
  config.py                 # .env + CLI merge; provider selection (first non-empty, CLI overrides)
  buildspace.py             # Create build/<proj>_<ts>/, copy project in, promote on success

  llm/
    base.py                 # LLMClient protocol: chat(messages, tools, system) -> Response
    message_types.py        # Message / ToolCall / ToolResult / Response dataclasses
    anthropic_client.py     # Anthropic SDK + native web_search_20250305 server tool
    openai_client.py        # Responses API + web_search_preview
    ollama_client.py        # Local models; optional Tavily shim for web_search
    registry.py             # get_client(cfg) dispatcher

  tools/
    registry.py             # Tool objects + per-provider JSONSchema export
    scope.py                # Every FS path must resolve inside the active buildspace
    fs_tools.py             # read_file, write_file, edit_file, list_files
    exec_tools.py           # run_python, run_sim (iverilog/verilator), run_vivado
    diff_tools.py           # diff_trace (py vs sim), compare_hex
    research_tools.py       # search_ip_catalog, web_search, research_ip

  stages/
    plan.py                 # Stage 1: LLM emits artifacts/design_plan.json
    instrument.py           # Stage 2: AST rewrite → src_py_instr/; run → traces/python.jsonl
    generate.py             # Stage 3: LLM writes rtl/ + tb; loop until sim passes
    debug.py                # Stage 4: LLM diagnoses mismatches; restricted py edits
    bitstream.py            # Stage 5: iterative Vivado — errors feed back to the same loop
    promote.py              # Stage 6: copy artifacts into ip_custom/<proj>/

  instrument/
    ast_rewriter.py         # libcst transformer: wraps every Assign/AugAssign target
    tracer_runtime.py       # _trace(name, value, stage_hint) → NDJSON w/ shape+dtype+hex
    trace_schema.py         # Canonical record shape consumed by TB generator & diff_trace
    edit_guard.py           # AST diff between original and LLM-edited src_py/ in stage 4;
                            # rejects edits that touch non-added lines or non-assert/print/def

  sim/
    testbench_gen.py        # Generate SV TB that replays trace file, checks DUT signals
    runner.py               # iverilog/verilator compile+run; return mismatches + vcd path
    vivado_docker.py        # docker run vivado:latest -mode batch -source build.tcl;
                            # parse vivado.log for ERROR/CRITICAL WARNING → structured records

  catalog/
    index.py                # One-time: ip_catalog.txt → catalog_index.json
    search.py               # BM25/substring search → top-k for search_ip_catalog tool
    custom_ip_summary.py    # Schema + loader for ip_custom/<name>/summary.json

  prompts/
    system_plan.md
    system_generate.md
    system_debug.md
    system_bitstream.md     # Role + how to read Vivado error records
    ip_summary_template.md

  templates/
    build.tcl.j2            # Models ip_custom/evd_10x10/build.tcl
    host_uart.py.j2         # Models ip_custom/evd_10x10/host/evd_host.py
    basys3.xdc              # Baseline constraints for xc7a35tcpg236-1

  logging_util.py           # Per-run JSONL transcript
```

Top-level additions:
- `.env.example` — empty `ANTHROPIC_API_KEY=`, `OPENAI_API_KEY=`, `OLLAMA_BASE_URL=`, `TAVILY_API_KEY=`, `LLM_PROVIDER=`.
- `requirements.txt` — `anthropic`, `openai`, `libcst`, `jinja2`, `numpy`, `pyserial`, `python-dotenv`, `httpx`.

## CLI

```
python src/main.py <project_dir> [flags]
  -part <str>                 Target part (default xc7a35tcpg236-1)
  --model <provider/model>    e.g. anthropic/claude-opus-4-7
  --provider <name>           Override .env auto-select
  --stages plan,instrument,generate,debug,bitstream,promote
  --resume <build-dir>        Continue an existing run
  --no-research               Disable web_search + research_ip tools
  --max-iter <n>              Hard cap on LLM turns across all iterative stages (default 40)
  --token-budget <n>          Cumulative token cap (default 2M)
  --sim iverilog|verilator    Inner-loop sim (default iverilog)
  --keep-build                Retain build dir after success
  --promote                   On success, copy rtl/top/xdc/build.tcl/host + summary.json to ip_custom/<proj>/
  --force-promote             Allow overwriting an existing ip_custom/<proj>/ entry
  --verbose / --dry-run
```

## Buildspace layout

`build/<project>_<YYYYMMDD_HHMMSS>/`
```
src_py/           copy of projects/<proj>/*.py (Stage 4 may add prints/asserts/helpers)
src_py_instr/     AST-rewritten copy (Stage 2)
rtl/              LLM-authored Verilog
tb/               generated testbench
traces/           python.jsonl, sim_<iter>.jsonl
artifacts/        design_plan.json, build.tcl, vivado.log, utilization.rpt, top.bit
transcript.jsonl  every LLM turn + tool call, across Stages 1–6
state.json        stage completion flags + resume cursor
```

## Tool catalog exposed to the LLM

All paths resolve through `tools/scope.py` — anything outside the buildspace is rejected.

```
read_file(path)                                     -> {content, sha}
write_file(path, content)                           -> {ok, bytes}
edit_file(path, find, replace, count=1)             -> {ok, replacements}
list_files(path=".", glob=None)                     -> {entries:[{path,type,size}]}
run_python(script, args=[], timeout=120)            -> {stdout, stderr, exit_code, trace_path}
run_sim(top, sources, tb, sim="iverilog", timeout)  -> {pass, mismatches:[...], vcd_path, logs}
diff_trace(py_trace, sim_trace, tolerance_bits=2)   -> {total, matched, first_mismatch, summary}
run_vivado(build_tcl, timeout=1800)                 -> {pass, errors:[{stage,severity,code,msg,file?,line?}],
                                                        warnings_critical:[...], utilization?, timing?, bit_path?}
search_ip_catalog(query, k=5)                       -> [{name,vlnv,category,desc,key_params}]
research_ip(name_or_topic, hints=None)              -> {summary, sources, suggested_ports}
web_search(query)                                   -> provider-native (Anthropic server tool, etc)
submit_design(rtl_files, top, xdc, notes)           -> orchestrator signals "sim-clean" from Stage 3
```

In Stages 4 and 5, `edit_file` on `src_py/` additionally passes through `instrument/edit_guard.py`, which re-parses and rejects any edit that modifies an existing non-print/assert statement. New top-level functions are allowed.

## Stage-by-stage flow

1. **Plan.** LLM sees `src_py/` + concatenated `ip_custom/*/summary.json` + the Xilinx `catalog_index.json` summary. Tools: `read_file`, `search_ip_catalog`, `research_ip`, `web_search`. Emits `artifacts/design_plan.json` with `{modules, ports, fixed_point, top_protocol, ip_deps, build_order}`.
2. **Instrument (no LLM).** `instrument/ast_rewriter.py` wraps every `Assign`/`AugAssign` with `_trace(fqname, value, stage_hint)`. NumPy arrays logged as `{shape, dtype, hex_flat}`. Run `src_py_instr/<entry>.py` once to produce `traces/python.jsonl`.
3. **Generate.** LLM loop writes `rtl/*.v` and consumes `testbench_gen` output. Calling `submit_design` triggers `run_sim`; mismatches are fed back as the next turn's tool result. Stage advances when sim passes cleanly.
4. **Debug.** Same loop, extended permissions: restricted `src_py/` edits via `edit_guard`. Cycle: edit → `run_python` → `run_sim` → `diff_trace`. Advances when `diff_trace` reports 0 mismatches for 1 consecutive run.
5. **Bitstream (iterative).** Orchestrator renders `templates/build.tcl.j2`, calls `run_vivado` in Docker (matches `vivado_gui.sh` pattern, batch mode), and parses `vivado.log` into structured error/critical-warning records. If `run_vivado.pass` is false, the error records are fed back to the LLM as the next turn's tool result — exactly the same shape as a sim mismatch. The LLM edits `rtl/`, `top.v`, `<xdc>`, or `build.tcl` and calls `run_vivado` again. Loop continues until a clean bitstream or `--max-iter` is hit. Common failure modes the planner prompt should cover: synthesis errors (undeclared nets, width mismatch), DRC errors (unconstrained I/O, clock pin mis-assignment), timing failures (WNS < 0 → suggest pipeline insertion), resource overflow (LUT/DSP/BRAM beyond part). On success: `report_utilization` and `report_timing_summary` are captured, `.bit` copied to `artifacts/`, host driver rendered from `templates/host_uart.py.j2` using `top_protocol`.
6. **Promote.** Gated on `--promote`. Copies into `ip_custom/<project>/`:
   - `rtl/*.v` (verbatim)
   - `top.v`, `<xdc>`, `build.tcl`, `program.tcl`
   - `host/<project>_host.py` (rendered)
   - `summary.json` auto-generated from `artifacts/design_plan.json` + utilization report (fills `ports`, `latency`, `resources_est`, `io_protocol`, `fixed_point`). Same schema that future runs read as an IP-reuse candidate — so every successful run enlarges the catalog.
   - `README.md` stub: one-liner purpose + link to `summary.json` + provenance (`generated by src/main.py @ <git sha> from projects/<name>`).
   Refuses to overwrite an existing `ip_custom/<project>/` unless `--force-promote` is also set; otherwise writes to `ip_custom/<project>_<ts>/`.

## Cost + loop guards (`orchestrator.py`)

- `--max-iter` caps total LLM turns across Stages 3–5 combined.
- `--token-budget` tracked cumulatively; orchestrator refuses the next turn and checkpoints.
- Per-tool output truncated to first 200 lines with `…[truncated, N lines]`. Vivado logs are additionally distilled into structured error records before truncation, so the LLM always sees the error list even if the raw log is long.
- Stuck detection: 3 turns without a tool call **or** the same error/mismatch signature 3× → inject a nudge. 5 nudges → abort with `stuck_reason`.
- Everything appended to `transcript.jsonl` → `--resume` works after abort.

## IP summaries

**Xilinx catalog**: one-time parse `ip_catalog.txt` → `catalog/catalog_index.json` (`[{name, vlnv, category, display_name, desc, params, param_count}]`) + a tiny inverted index for `search_ip_catalog`. LLM never sees the full 800 KB; only top-k results per query.

**Custom IP summary schema** (`ip_custom/<name>/summary.json`):
```json
{
  "name": "evd_10x10",
  "one_line": "Hermitian 10x10 eigendecomposition via Jacobi sweeps, S32Q16 complex",
  "top_module": "jacobi_engine10x10",
  "rtl_files": ["rtl/jacobi_engine10x10.v", "..."],
  "ports": [{"name":"clk","dir":"in","width":1}, "..."],
  "handshake": "start/done pulse",
  "latency": {"cycles_typ": 12000, "per_sweep": 1200},
  "resources_est": {"lut": 4500, "dsp": 48, "bram": 0},
  "io_protocol": {"kind":"uart","rx_frame":604,"tx_frame":65,"crc":"sum8"},
  "fixed_point": {"total":23, "frac":16, "complex":true},
  "known_limitations": ["max_iter capped at 65535", "N fixed at compile time"],
  "reference_host": "host/evd_host.py"
}
```

Stage-1 LLM gets the concatenation of all `summary.json` files (small) and calls `search_ip_catalog` on demand for Xilinx IPs.

## Reuse / reference points

- `ip_custom/evd_10x10/build.tcl` — template for `src/templates/build.tcl.j2`.
- `ip_custom/evd_10x10/host/evd_host.py` — shape for `src/templates/host_uart.py.j2` (UART framing, CRC, pack/unpack).
- `vivado_gui.sh` — canonical docker invocation pattern for `src/sim/vivado_docker.py` (strip `-X` + GUI flags, add `-mode batch`).
- `ip_catalog.txt` + `dump_ip_catalog.tcl` — input + regeneration recipe for `src/catalog/index.py`.
- `ip_submodule/cordic/rtl/cordic.v` — concrete example of an external IP the planner should reference by summary.
- `projects/eig_10/eig_10.py` — canonical Stage-0 input for the first end-to-end run.
- `old/matrix_eig_10_fxp.m` — hand-written fixed-point reference, useful as an oracle when comparing generated RTL to what a human wrote.

## Critical files to create (first PR)

- `src/main.py`, `src/orchestrator.py`, `src/config.py`, `src/buildspace.py`
- `src/llm/base.py`, `src/llm/anthropic_client.py`, `src/llm/openai_client.py`, `src/llm/ollama_client.py`, `src/llm/registry.py`
- `src/tools/registry.py`, `src/tools/scope.py`, `src/tools/fs_tools.py`, `src/tools/exec_tools.py`, `src/tools/diff_tools.py`, `src/tools/research_tools.py`
- `src/stages/plan.py`, `src/stages/instrument.py`, `src/stages/generate.py`, `src/stages/debug.py`, `src/stages/bitstream.py`, `src/stages/promote.py`
- `src/instrument/ast_rewriter.py`, `src/instrument/tracer_runtime.py`, `src/instrument/trace_schema.py`, `src/instrument/edit_guard.py`
- `src/sim/testbench_gen.py`, `src/sim/runner.py`, `src/sim/vivado_docker.py`
- `src/catalog/index.py`, `src/catalog/search.py`, `src/catalog/custom_ip_summary.py`
- `src/templates/build.tcl.j2`, `src/templates/host_uart.py.j2`, `src/templates/basys3.xdc`
- `src/prompts/system_plan.md`, `src/prompts/system_generate.md`, `src/prompts/system_debug.md`, `src/prompts/system_bitstream.md`, `src/prompts/ip_summary_template.md`
- `.env.example`, `requirements.txt`
- `ip_custom/evd_10x10/summary.json` — hand-authored as first catalog entry and schema exemplar.

## Verification

Smoke tests, in order of increasing scope:

1. **Unit**: `pytest src/instrument/ast_rewriter_test.py` — feed a toy function, assert every assignment emits a trace record.
2. **Unit**: `pytest src/catalog/index_test.py` — parse `ip_catalog.txt`; confirm ≥200 entries and `search_ip_catalog("fifo", k=5)` returns FIFO-related IP.
3. **Unit**: `pytest src/tools/scope_test.py` — reads of `/etc/passwd` or `../../foo` fail; in-buildspace paths succeed.
4. **Unit**: `pytest src/sim/vivado_docker_test.py` — feed a canned `vivado.log` with synth errors and confirm the parser produces structured error records.
5. **LLM dry-run**: `python src/main.py projects/eig_10 -part xc7a35tcpg236-1 --dry-run` — Stage 1 only; confirm `artifacts/design_plan.json` references evd_10x10's summary.
6. **Stages 1–2**: `--stages plan,instrument` — confirm `traces/python.jsonl` is schema-valid.
7. **Full run against a trivial project** (before eig10): `projects/adder_8/adder_8.py` with `def add(a, b): return (a + b) & 0xFF`. Run full pipeline; verify `.bit` is produced and host driver round-trips test vectors.
8. **Full eig_10 run**: `python src/main.py projects/eig_10 -part xc7a35tcpg236-1 --sim iverilog --max-iter 40 --promote`. Success = `run_sim` pass + clean `run_vivado` + utilization within 2× of the hand-built evd_10x10. Compare generated `rtl/` to `ip_custom/evd_10x10/rtl/` post-mortem.
9. **Provider parity**: repeat (7) with `--provider openai` and `--provider ollama` (research disabled for ollama unless Tavily key is set).

## Explicitly out of scope for the first implementation

- Automatic XDC generation for parts other than the bundled Basys3 template.
- Parallel candidate-RTL exploration.
- Non-UART host protocols (AXIS / Ethernet templates).
