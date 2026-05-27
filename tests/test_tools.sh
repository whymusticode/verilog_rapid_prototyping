#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
unset VIVADO_BACKEND VIVADO_NATIVE_BIN VITIS_HLS_BIN
source ./.envrc

echo "VIVADO_BACKEND=${VIVADO_BACKEND:-<unset>}"
echo "VIVADO_NATIVE_BIN=${VIVADO_NATIVE_BIN:-<unset>}"
echo "VITIS_HLS_BIN=${VITIS_HLS_BIN:-<unset>}"

python3 - <<'PY'
from py2v import vivado
print("detect_backend=", vivado.detect_backend())
PY

timeout 10s "${VIVADO_NATIVE_BIN}" -version >/dev/null

if [ "$(basename "${VITIS_HLS_BIN}")" = "vitis-run" ]; then
  timeout 10s "${VITIS_HLS_BIN}" --version >/dev/null
else
  timeout 10s "${VITIS_HLS_BIN}" -version >/dev/null
fi

echo "tool smoke checks passed"
