
<!-- LLMs do not edit this section -->

python code to benchmark and check if verilog code matches python code


```sh
python convert.py -m qwen -i Projects/small/clip -o conversion_004/
python convert.py -m codex:gpt-6-luna -t test4small

python convert.py -m codex:gpt-6-luna -i Projects/turbo-3gpp
```

```sh
python sim.py conversion_001/
python sim.py conversion_001/ Projects/fft/
```
evaluation time: 20s  
clock cycles: 1040  
bits of precision: 14.5  

where bits of precision is computed:
log2(max value) - log2(RMSE)




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


<!-- end LLMs do not edit this section -->
<!-- now llms can go into greater detail below this line, but again don't change anything above this line -->

## Choosing an agent and model

`convert.py -m qwen`, `-m codex`, and `-m whale` use their respective CLI's
configured/default model. To select a specific model, append its ID:

```sh
python convert.py -m codex:gpt-6-sol -i Projects/small/clip -o conversion_004/
python convert.py -m qwen:my-qwen-model -i Projects/small/clip -o conversion_005/
python convert.py -m whale:deepseek-v4-flash -i Projects/small/clip
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
When the agent finishes, `convert.py` runs fresh simulations against both the
copy and the original project, reports changed Python/parameter files, and
writes details to `reference_check.log`. Simulation inputs vary between runs;
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
`--qwen`, and `--whale` can select a nondefault CLI executable. All three
agents run inside the same bubblewrap filesystem boundary. Codex authenticates
from `$CODEX_HOME` (or `~/.codex`); Whale reads `$WHALE_HOME` (or `~/.whale`).
Both run without their own nested approval/sandbox prompts.

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
python convert.py -m codex:gpt-6-luna -t test4small --prompt-version v2
python plot_conversions.py conversion_test_008 conversion_test_009 -o conversion_analysis
```

Every `sim` and `synth` call appends a record to `evald.jsonl`: raw measurements,
elapsed time, source hash, reference used, token counts, and the artifact path.
`evaluations/` keeps each evaluated RTL/Python snapshot, full evaluator output,
stimulus, mismatch diagnostics, testbench, and synthesis reports. Final simulations
against the original reference are recorded there too, including after a token
limit. No composite score or performance pass/fail thresholds are used.

Codex uses its app-server protocol to retain all emitted events and receive live
token usage updates. Per-project defaults are a 150,000 weighted-token budget:

```text
weighted = (input - cached_input) + 5 * output + 0.1 * cached_input
```

Set `--token-budget NUMBER` and `--token-weights INPUT OUTPUT CACHED` to change
this; `--token-budget 0` disables stopping. These weights are experimental units,
not a claimed billing rate. Reasoning tokens are already included in output.
The runner interrupts at the first usage notification over budget; one response
can overshoot. Token limits currently apply only to Codex. Qwen/Whale retain
their existing launch behavior.

`agent_events.jsonl` preserves the full Codex event stream, `tokens.jsonl` records
usage updates, `run.json` records the stop reason and effective settings, and
`prompt.txt` holds the exact prompt. Batch `harness_sources/` freezes the scripts
used by that batch; `model_info.yaml` records their hashes and the budget settings.
`--prompt-version baseline` selects the brief original-style instructions;
`v2` adds the explicit streaming contract, numerical guidance and tool guide.

Simulation prints precision and RMS error continuously—14 bits is better than
13. Its default input is unthrottled, so cycles/frame exposes design capacity;
`--rate HZ` requests a paced stream. Exit codes describe measurement errors,
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
