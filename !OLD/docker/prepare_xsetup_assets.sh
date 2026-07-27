#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DOCKER_DIR="${REPO_ROOT}/py2v/docker"
DEFAULT_TARBALL_NAME="FPGAs_AdaptiveSoCs_Unified_2024.1_0522_2023.tar.gz"

USER_TARBALL_PATH="${1:-}"

resolve_tarball() {
  if [[ -n "${USER_TARBALL_PATH}" && -f "${USER_TARBALL_PATH}" ]]; then
    echo "${USER_TARBALL_PATH}"
    return
  fi

  local candidates=(
    "${HOME}/Dekstop/${DEFAULT_TARBALL_NAME}"
    "${HOME}/Desktop/${DEFAULT_TARBALL_NAME}"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -f "${candidate}" ]]; then
      echo "${candidate}"
      return
    fi
  done

  echo ""
}

TARBALL_PATH="$(resolve_tarball)"
if [[ -z "${TARBALL_PATH}" ]]; then
  echo "Could not find ${DEFAULT_TARBALL_NAME}." >&2
  echo "Pass it explicitly: ${DOCKER_DIR}/prepare_xsetup_assets.sh /absolute/path/${DEFAULT_TARBALL_NAME}" >&2
  exit 1
fi

WORKDIR="$(mktemp -d)"
cleanup() {
  rm -rf "${WORKDIR}"
}
trap cleanup EXIT

tar -xzf "${TARBALL_PATH}" -C "${WORKDIR}"
shopt -s nullglob
matches=("${WORKDIR}"/*/xsetup)
shopt -u nullglob

INSTALLER_DIR=""
if [[ ${#matches[@]} -gt 0 ]]; then
  INSTALLER_DIR="$(dirname "${matches[0]}")"
fi

if [[ -z "${INSTALLER_DIR}" ]]; then
  echo "Could not locate xsetup in extracted archive." >&2
  exit 1
fi

echo "Launching ConfigGen. Choose your product/modules, then quit."
"${INSTALLER_DIR}/xsetup" -b ConfigGen

if [[ ! -f "${HOME}/.Xilinx/install_config.txt" ]]; then
  echo "Expected ~/.Xilinx/install_config.txt after ConfigGen, but it was not found." >&2
  exit 1
fi

cp "${HOME}/.Xilinx/install_config.txt" "${DOCKER_DIR}/install_config.txt"
echo "Wrote ${DOCKER_DIR}/install_config.txt"

echo "Launching AuthTokenGen. Sign in when prompted."
"${INSTALLER_DIR}/xsetup" -b AuthTokenGen

if [[ -f "${HOME}/.Xilinx/wi_authentication_key" ]]; then
  echo "Auth token generated at ${HOME}/.Xilinx/wi_authentication_key"
elif [[ -f "${HOME}/.Xilinx/xinstall/authToken" ]]; then
  echo "Auth token generated at ${HOME}/.Xilinx/xinstall/authToken"
else
  echo "Auth token generation completed, but no known token file path was found." >&2
  echo "Set XILINX_AUTH_TOKEN_FILE when running build_vitis_image.sh." >&2
fi
