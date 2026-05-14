#!/usr/bin/env bash
# py2v end-to-end: PDF -> reference + spec -> first-draft RTL -> sim -> iterate.
# Keeps correctness runs fast (sim-only). Timing/PnR is optional at the end.
#
# Prereqs:
#   - direnv allowed (`direnv allow` in this dir) so VIVADO_BACKEND is set.
#     The hook is enabled in ~/.zshrc -> `eval "$(direnv hook zsh)"`.
#   - ANTHROPIC_API_KEY exported (env or .envrc.private).
#   - Vivado reachable: native `vivado`, or `flatpak run com.github.corna.Vivado`,
#     or a docker image whose path matches VIVADO_DOCKER_BIN.
#
# Pick a project once and reuse the variable through the run.
PROJ=projects/eig_10

# 1. Show available HW presets (purely informational).
python -m py2v.main hw list

# 2. Extract verbatim Python + bug review + py2c.yaml from the PDF.
#    Drops files into $PROJ/{reference.py, reference_bugs.md, py2c.yaml, project.yaml}.
python -m py2v.main extract "$PROJ"

# 3. Diff the extracted reference against any prior copy, just to eyeball it.
diff -u "$PROJ"/eig_10_with_output_input.py "$PROJ"/reference.py | head -200 || true

# 4. Generate fixed-input/output golden files from reference.py for the TB.
python -m py2v.main python-ref "$PROJ" --seed 0 --max-iter 1

# 5. First-draft RTL + TB into $PROJ/build/{rtl,tb}/
python -m py2v.main rtl "$PROJ" --max-rounds 30 --budget-usd 4

# 6. Sim sanity check (xsim under the active vivado backend).
python -m py2v.main sim "$PROJ" --tolerance-lsb 1

# 7. Iterate correctness (sim-only; no synth/timing here).
python -m py2v.main iterate "$PROJ" --phase correctness --max-rounds 10 --budget-usd 60

# 8. Iterate speed (brings in timing/pnr checks).
python -m py2v.main iterate "$PROJ" --phase speed       --max-rounds 12 --budget-usd 80 \
    --target-cycles 200

# 9. Optional timing/PnR checks (uncomment when needed; these are slow).
# python -m py2v.main pnr "$PROJ" --phase synth --top top
# python -m py2v.main pnr "$PROJ" --phase impl --top top
