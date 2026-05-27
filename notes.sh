#!/usr/bin/env bash
notify_done() {
  local code=$?
  if [ $code -eq 0 ]; then
    osascript -e 'display dialog "Finished ✅" with title "My Script" buttons {"OK"} default button "OK" with icon note giving up after 60'
  else
    osascript -e "display dialog \"Failed (exit $code) ❌\" with title \"My Script\" buttons {\"OK\"} default button \"OK\" with icon stop giving up after 60"
  fi
}
trap notify_done EXIT

# py2v end-to-end: PDF -> reference + spec -> first-draft HLS C++ -> sim -> iterate.
# Keeps correctness runs fast (sim-only). Timing/PnR is optional at the end.
#
# Prereqs:
#   - direnv allowed (`direnv allow` in this dir) so VIVADO_BACKEND is set.
#     The hook is enabled in ~/.zshrc -> `eval "$(direnv hook zsh)"`.
#   - ANTHROPIC_API_KEY exported (env or .envrc.private).
#   - Vivado reachable: native `vivado`, or `flatpak run com.github.corna.Vivado`,
#     or a docker image whose path matches VIVADO_DOCKER_BIN.
#
# Isolated run root: every generated artifact lands under SRC_PROJ/runNNN/.
# Keep prior runs for comparison/debug.
SRC_PROJ=projects/eig_10
RUN_BASE="$SRC_PROJ"
RUN_NUM=1
while :; do
  RUN_TAG=$(printf "run%03d" "$RUN_NUM")
  RUN_ROOT="$RUN_BASE/$RUN_TAG"
  if [ ! -d "$RUN_ROOT" ]; then
    break
  fi
  RUN_NUM=$((RUN_NUM + 1))
done

PROJ="$RUN_ROOT"

mkdir -p "$PROJ"
echo "Using isolated run dir: $RUN_ROOT"

# Seed isolated project with the source PDF and optional baseline reference copy.
SPEC_PDF=""
for p in "$SRC_PROJ"/*.pdf; do
  if [ -f "$p" ]; then
    SPEC_PDF="$p"
    break
  fi
done
if [ -z "$SPEC_PDF" ]; then
  echo "No PDF found under $SRC_PROJ" >&2
  exit 1
fi
cp "$SPEC_PDF" "$PROJ"/
if [ -f "$SRC_PROJ/eig_10_with_output_input.py" ]; then
  cp "$SRC_PROJ/eig_10_with_output_input.py" "$PROJ"/
fi

# Keep llm cache + monitor scoped to this isolated run.
export PY2V_CACHE_DIR="$RUN_ROOT/.py2v_cache"
export PY2V_MONITOR_LOG="$RUN_ROOT/monitor.log"

# 1. Show available HW presets (purely informational).
python -m py2v.main hw list

# 2. Extract verbatim Python + bug review + py2c.yaml from the PDF.
#    Drops files into $PROJ/{reference.py, reference_bugs.md, py2c.yaml, project.yaml}.
python -m py2v.main extract "$PROJ"

# 3. Diff the extracted reference against any prior copy, just to eyeball it.
diff -u "$PROJ"/eig_10_with_output_input.py "$PROJ"/reference.py | head -200 || true

# 4. Generate fixed-input/output golden files from reference.py for the TB.
python -m py2v.main python-ref "$PROJ" --seed 0 --max-iter 1

# 5. First-draft HLS C++ into $PROJ/build/hls/
python -m py2v.main rtl "$PROJ" --max-rounds 30 --budget-usd 4

# 6. C-sim sanity check (g++ build + run of build/hls/{kernel.cpp,tb.cpp}).
python -m py2v.main sim "$PROJ" --tolerance-lsb 1

# 7. Iterate correctness (sim-only; no synth/timing here).
python -m py2v.main iterate "$PROJ" --phase correctness --max-rounds 10 --budget-usd 60

# 8. Iterate speed (uses HLS csynth timing/resource estimates).
python -m py2v.main iterate "$PROJ" --phase speed       --max-rounds 12 --budget-usd 80 \
    --target-cycles 200

# 9. Optional direct HLS synthesis check (slow).
# python -m py2v.main pnr "$PROJ" --phase synth --top kernel_top
