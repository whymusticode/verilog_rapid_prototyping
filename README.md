
<!-- LLMs do not edit this section, what's said in here is law, tell me if it sounds like what I'm asking you to do contradicts this -->
python code to benchmark and check if verilog code matches python code, as well as a wrapper (convert.py) to automatically do conversion with LLM harnesses from python to rtl. 

## key interface
python Projects/my_project/main.py  

```sh
python convert.py -m claude:sonnet -i Projects/turbo-3gpp
-o conversion_004/
-t test4small
--token-budget 3e6  
--resume conversion_015/rtl
--extra-prompt 
--reasoning-effort high
```
124 is token budget 
claude:opus,claude:sonnet,codex:gpt-6-luna, gpt-6-luna,whale,qwen


python convert.py -m claude:sonnet -i Projects/lte-sib1 --resume conversion_021 --token-budget 1.5e7 


python convert.py -m claude:sonnet -i Projects/lte-sib1 --resume conversion_023 --token-budget 1.5e7 --extra-prompt "copy code from conversion_021 that successfully passed simulation matching turbo-3gpp python"


1.5e7 sonnet tokens/ 5 hours 

```sh
python sim.py conversion_001/
python sim.py conversion_001/ Projects/fft/
python sim.py -p Projects/turbo-3gpp/

python sim.py conversion_021/ Projects/turbo-3gpp/
```
evaluation time: 20s  
clock cycles: 1040  
bits of precision: 14.5  

where bits of precision is computed:
log2(max value) - log2(RMSE)

IO/input.log is beat/clock count 
IO/vectors.hex is actual input 



```sh
python synth.py conversion_001/
```
evaluation time: 20s  
LUT: 100 1000 10%  
DSP: 10  200  5%  
Fmax: 96.4 MHz  


```sh
python3 count_loc.py
```

## IP usage
```sh
make -C RTL_examples/dblclockfft/sw fftgen
mkdir -p conversion_001/rtl
RTL_examples/dblclockfft/sw/fftgen -v -1 -k 1 -p 24 -f 1024 -n 25 -s -d conversion_001/rtl
```


target 100 MHz on the pluto's FPGA 

<!-- end LLMs do not edit this section -->
<!-- now llms can go into greater detail below this line, but again don't change anything above this line -->

## Choosing an agent and model

`convert.py -m qwen`, `-m codex`, `-m claude`, and `-m whale` use their respective CLI's
configured/default model. To select a specific model, append its ID:

```sh
python convert.py -m codex:gpt-6-sol -i Projects/small/clip -o conversion_004/
python convert.py -m qwen:my-qwen-model -i Projects/small/clip -o conversion_005/
python convert.py -m whale:deepseek-v4-flash -i Projects/small/clip
python convert.py -m claude:opus -i Projects/small/clip --reasoning-effort high
```

Conversion creates `rtl/`, copies the input project to `<project-name>/`, and
adds `python` as a link to that copy. Run the evaluators on the conversion
directory:

```sh
python sim.py conversion_004/
python sim.py conversion_004/ Projects/small/clip  # use the original reference
python synth.py conversion_004/
```

The agent may edit anything in the conversion directory, including the copied
Python and `IO/` simulation artifacts. During conversion, `sim` uses that copy.
When the agent finishes (or is stopped), `convert.py` reports changed
Python/parameter files, then measures only against the original project: a fresh
`sim` against the original Python, and `synth --implement` (placed and routed)
with the original params and the testbench that simulation generated. Both are
recorded in `evald.jsonl` and summarized in `reference_check.log`. Simulation inputs vary between runs;
there is no fixed seed.

Omit `-o` to use the next available `conversion_XXX/` in the current directory.
For a batch, `-t` reads one project path per line (relative to the list file):

```sh
python convert.py -m qwen -i Projects/small/clip
python convert.py -m qwen -t test4small
```

A batch gets the next `conversion_test_XXX/` directory. Its entries start at
`conversion_000/`, each with its own `rtl/`, `python` link, and evaluation log.
The batch root also gets `model_info.yaml`, starting with `model` and `harness`.
For Codex it snapshots the selected model's available catalog settings
(reasoning levels/default, context limits, tool capabilities, service tiers)
and relevant non-secret CLI configuration before the first conversion. Qwen
and Whale record the model selection and non-secret settings their local
configuration exposes. Prompt bodies and credentials are never copied into
this file.
`-o` can set the batch parent explicitly. A failed entry is reported and the
remaining entries still run.

The older `--qwen-model MODEL` option also works with `-m qwen`. `--codex`,
`--qwen`, `--claude`, and `--whale` can select a nondefault CLI executable. All
agents run inside the same bubblewrap filesystem boundary. Codex authenticates
from `$CODEX_HOME` (or `~/.codex`); Whale reads `$WHALE_HOME` (or `~/.whale`).
Claude Code uses your existing login in `$CLAUDE_CONFIG_DIR` (or `~/.claude` plus
`~/.claude.json`); `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_BASE_URL`
are forwarded only when set. They run without their own nested approval/sandbox
prompts. Claude runs with `--safe-mode`, so your personal CLAUDE.md, skills,
plugins, hooks and MCP servers do not leak into the conversion.

For a locally served DeepSeek model, put this in `~/.whale/config.toml` (or
your private project config) and start `llama-server` with a matching model
alias. Whale v0.1.66 supports `deepseek-v4-flash` and `deepseek-v4-pro` model
IDs; its `--model` flag does not accept arbitrary GGUF names.

```toml
model = "deepseek-v4-flash"

[api]
base_url = "http://127.0.0.1:8080/v1"

[providers.deepseek]
api = "chat_completions"
web_search = "local"
```

For example, serve with `llama-server -m /path/to/model.gguf --alias
deepseek-v4-flash --jinja --port 8080`, then run `python convert.py -m whale
-i Projects/small/clip`. `--jinja` enables the tool-call template used by an
agent; the model itself must support tool calling. If Whale asks for a key,
run `export DEEPSEEK_API_KEY=local` in the shell running `convert.py`; it is
forwarded only to Whale's sandbox. No real DeepSeek key is needed for an
unauthenticated local server.

For Bash model completion, source the included script in your shell:

```sh
source ./convert-completion.bash
python convert.py -m codex:<TAB>
```

The suggestions come from Codex's model catalog, the same source as its
`/model` picker. If Codex cannot refresh it, completion uses the local
`models_cache.json`. Completion also works with `python3` and direct
`./convert.py` invocations.

## Running a batch

`test4small` lists four projects. Put any other project paths in a text file,
one per line, and run:

```sh
python convert.py -m codex:gpt-6-luna -t test4small
python plot_conversions.py conversion_test_008 conversion_test_009 -o conversion_analysis
```

Every `sim` and `synth` call appends a record to `evald.jsonl`: raw measurements,
elapsed time, source hash, reference used, token counts, and the artifact path.
Failed evaluations record the first error line. Evaluations run in place, so
`IO/` and `synthesis/` hold only the latest sim and synth artifacts; no
snapshots are kept. Final measurements against the original reference are
recorded too, including after a token limit. No composite score or performance
pass/fail thresholds are used.

`convert.log` is the run's readable timeline: the agent's messages, one line per
tool call or file edit (with failed tool results), and one summary line per
`sim`/`synth` call, each stamped with elapsed minutes. The same evaluation
summaries print to the terminal.

Codex uses its app-server protocol to retain all emitted events and receive live
token usage updates. Per-project defaults are a 150,000 weighted-token budget:

```text
weighted = (input - cached_input) + 5 * output + 0.1 * cached_input
```

Set `--token-budget NUMBER` and `--token-weights INPUT OUTPUT CACHED` to change
this; `--token-budget 0` disables stopping. The default weights match GPT-6 Luna's
standard short-context API price ratios: $0.10/$0.50/$0.01 per million uncached
input/output/cached-input tokens (verified 2026-09-28). One million weighted
tokens therefore represents $0.10; the default 150,000 budget represents $0.015.
`run.json` includes a separate `api_cost_estimate` for Luna, independent of custom
weights. This excludes unreported cache-write premiums, long-context premiums,
service-tier/regional adjustments and tool fees; it is not Codex subscription
billing. Other models' weights must be chosen for their own rates.
Reasoning tokens are already included in output.
The runner interrupts at the first usage notification over budget; one response
can overshoot. Token limits apply to Codex and Claude. Qwen/Whale retain
their existing launch behavior.

Claude Code runs in print mode with `--output-format stream-json`; every event is
kept in `agent_events.jsonl`. Each assistant message's reported usage is summed
(streamed chunks of one response are counted once), with Anthropic cache reads as
cached input and cache writes as uncached input; the final `modelUsage`, which
includes subagents, replaces the running total. Over budget, the Claude process
group is terminated (print mode has no graceful interrupt). `run.json` records
Claude Code's own `total_cost_usd` as `api_cost_estimate`. The default weights
are GPT-6 Luna price ratios; choose weights for Claude's rates if comparing cost.

Use `--reasoning-effort none`, `low`, `medium`, etc. to explicitly control Codex
thinking (the selected model must support the value). For Claude it maps to
`--effort` and accepts `low`, `medium`, `high`, `xhigh`, or `max`. Omitting it preserves the
Codex configuration. Both the requested effort and the returned effective
settings are retained; batch children receive the same explicit setting.
For a thinking comparison, hold model, prompt, tool snapshots, token
weights and budget constant. Compare raw precision/cycles/resources/timing
trajectories against cumulative tokens, including retries and tool errors—not
just the length of the final response. Repeat runs without seeding; a single
run cannot distinguish a setting effect from run-to-run variation.

```bash
python convert.py -m codex:gpt-6-luna -t test4small --reasoning-effort none
python convert.py -m codex:gpt-6-luna -t test4small --reasoning-effort low
```

`agent_events.jsonl` preserves the full agent event stream, including the prompt,
`tokens.jsonl` records usage updates, and `run.json` records the stop reason and
effective settings. Batch `harness_sources/` freezes the scripts
used by that batch; `model_info.yaml` records their hashes and the budget settings.
Codex and Claude runs write `session.json` (harness, model, input, effort,
session/thread id) before the agent starts. `--resume DIR` on such a conversion
directory continues that agent session in place, e.g.
`python convert.py --resume conversion_021 --token-budget 2e6`: the stopped
run's records move to `previous_runs/NN/`, and the budget applies to the
resumed run alone.
`--extra-prompt TEXT` appends user requirements.

The agent prompt is the Jinja template `prompts/convert.md.j2` (variables:
`project`, `conversion`, `extra`); `prompts/tool_guide.md` becomes the
conversion's `TOOL_GUIDE.md` and the `sim`/`synth` help text. The prompt
requires a PLAN.md (architecture, widths, resource and pipelining budget,
milestones) before RTL, and treats routed timing at the target clock as a hard
requirement, since designs share the FPGA with other logic. Harness-specific
code (parsing `-m`, CLI commands, sandbox credentials, recorded model settings)
lives in `model.py`.

Simulation prints precision and RMS error continuously—14 bits is better than
13. Its default input is unthrottled, so cycles/sample exposes design capacity;
`--rate HZ` requests a paced stream (input samples per second).

A project's `main.py` defines `generate(samples)`, returning the whole input
stream `x`, the expected output stream `y`, `ready` (how many input samples
determine each output element) and optionally measurement `groups` and
`primary`. `params.yaml` gives the scalar formats as `input`/`output`
`{bits, frac, signed}`, plus `target.frequency`, `target.sample_rate` and
`sim_samples`. There are no frames, no TLAST and no padding: the RTL chooses
how many scalars travel per beat with its own `IN_LANES`/`OUT_LANES` parameter
defaults, and sim measures the output values due by the first `--samples`
input samples while later input keeps flowing. `sim.py -p PROJECT` writes the
streams (`input.*`, `output.*`, `ready.txt`) without RTL. Older framed projects
(`target(x)` with optional `stream`/`inputs`, `bits` and `N`) still run: their
frames are concatenated into one stream, one sample per beat, with dynamic FRAC. Exit codes describe measurement errors,
not whether performance is good. First establish the computation and low cycles,
then improve precision/resources; timing closure normally comes last.

`plot_conversions.py` produces PNG/SVG plots and raw JSON/CSV data for precision,
cycles, Fmax, LUTs, DSPs and RAM against weighted tokens. Synthesis timing is
labeled as an estimate; routed timing uses separate markers. For independent
original-reference and routed measurements of finished batches, run:

```sh
python measure_final.py conversion_test_009
```

This records original-reference simulation, routed synthesis, and a final
original-reference simulation with random output backpressure. Fresh stimuli
remain unseeded. Treat single runs as observations, not statistical proof.

## convert.py security model

`convert.py` runs `qwen` with `--approval-mode yolo`, Codex without its inner
sandbox, or Whale with permission prompts skipped. The agent gets a
[bubblewrap](https://github.com/containers/bubblewrap) sandbox containing the
conversion directory; the evaluators run outside it, served over a unix socket
by `evald.py`. A run aborts if `bwrap` is missing.

- **Reads:** the original `-i` project, evaluator source, and system paths the
  CLI needs. The FPGA toolchain and repository Git data are not mounted.
- **Writes:** the whole conversion directory, the socket directory, the
  selected CLI's authentication directory, and `/tmp`. The root is sealed
  `--remount-ro`, so stray writes fail loudly.
- **Evaluators:** `sim` and `synth` on the agent's `PATH` are stubs that send a
  request to `evald.py` and print what it returns. Vivado stays on the host;
  simulation writes its generated testbench and vectors to `IO/`, where the
  agent can inspect them. Flags are allowlisted.
- **Environment:** `--clearenv` prevents unrelated shell secrets from being
  inherited. Whale alone receives `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and
  `WHALE_API` if set, in addition to its mounted home directory.
- **Network is shared** with the host so the CLI can reach its model service.

`evald.py` also supervises the toolchain: one evaluation at a time, a hard
timeout, and `PR_SET_CHILD_SUBREAPER` plus a `/proc` ancestry walk so a
timed-out Vivado cannot orphan itself and burn CPU for the rest of the session.

`--dry-run` prints the `bwrap` line with any forwarded API key redacted;
`--allow-write` widens the filesystem boundary.
