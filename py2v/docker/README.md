# py2v Vitis Docker Setup

This folder sets up a Docker image that installs AMD Vitis/Vivado from the 2024.1 unified tarball so `py2v` can issue tool calls in a containerized environment.

## What this implements

- A Docker build flow for `FPGAs_AdaptiveSoCs_Unified_2024.1_0522_2023.tar.gz`
- Headless installer invocation using `xsetup` batch flags:
  - `-b ConfigGen`
  - `-b AuthTokenGen`
  - `-a XilinxEULA,3rdPartyEULA,WebTalkTerms -b Install -c <config>`
- BuildKit secret handling for the auth token (not baked into image layers)

## Why these flags

The unified installer batch flow above is the common documented/field-tested flow for non-GUI installs (used across AMD community guides and scripts). `WebTalkTerms` can be removed if your installer build rejects it.

If needed:

```bash
XSETUP_AGREE="XilinxEULA,3rdPartyEULA" ./py2v/docker/build_vitis_image.sh
```

## 1) Prepare install config and auth token

This step is interactive once, and writes a real `install_config.txt` into this folder:

```bash
./py2v/docker/prepare_xsetup_assets.sh \
  "$HOME/Desktop/FPGAs_AdaptiveSoCs_Unified_2024.1_0522_2023.tar.gz"
```

The helper also checks `$HOME/Dekstop/...` (matching the path typo in your request) before `$HOME/Desktop/...`.

## 2) Build the image

```bash
./py2v/docker/build_vitis_image.sh \
  "$HOME/Desktop/FPGAs_AdaptiveSoCs_Unified_2024.1_0522_2023.tar.gz"
```

Optional env vars:

- `PY2V_VITIS_IMAGE_TAG` (default: `py2v-vitis:2024.1`)
- `XILINX_AUTH_TOKEN_FILE` (if token is not in a default path)
- `XSETUP_AGREE` (override accepted EULAs list)

## 3) Hook py2v to the image

After image build, set your backend wrapper (`VIVADO_DOCKER_BIN`) to execute tools inside the container, for example:

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace \
  py2v-vitis:2024.1 \
  vivado -version
```

Then point `py2v` at the equivalent wrapper command in your env (`.envrc` or shell profile).
# Vitis HLS Docker Setup (py2v)

This folder builds a Docker image that includes Vivado + Vitis HLS from a local
installer tarball.

## Expected installer file

- `~/Downloads/Vivado_Vitis_Update_2024.1.1_0614_1525.tar.gz`

If your file is somewhere else, pass the path to the helper script.

## Build image

From repo root:

```bash
./py2v/docker/build_vitis_image.sh
```

Or with explicit path:

```bash
./py2v/docker/build_vitis_image.sh "/Users/mbenton/Downloads/Vivado_Vitis_Update_2024.1.1_0614_1525.tar.gz"
```

By default this builds image tag `vivado-vitis-2024.1.1:local` targeting
`linux/amd64` (important on Apple Silicon).

## Configure repo env

Set these in `.envrc.private`:

```bash
export VIVADO_BACKEND=docker
export VIVADO_DOCKER_IMAGE=vivado-vitis-2024.1.1:local
export VIVADO_DOCKER_PLATFORM=linux/amd64
export VIVADO_DOCKER_BIN=/opt/Xilinx/Vivado/2024.1/bin/vivado
export VITIS_HLS_BIN=/opt/Xilinx/Vitis_HLS/2024.1/bin/vitis_hls
```

Then apply:

```bash
direnv allow
```

## Sanity checks

```bash
docker run --rm --platform linux/amd64 vivado-vitis-2024.1.1:local /opt/Xilinx/Vivado/2024.1/bin/vivado -version
docker run --rm --platform linux/amd64 vivado-vitis-2024.1.1:local /opt/Xilinx/Vitis_HLS/2024.1/bin/vitis_hls -version
```

Then test py2v commands:

```bash
python -m py2v.main sim projects/eig_10
python -m py2v.main pnr projects/eig_10 --phase synth
```

## Notes

- The Dockerfile now uses the installer's documented non-config mode:
  `--product`, `--edition`, and `--location`, avoiding fragile config-file keys.
- Defaults:
  - `XILINX_PRODUCT=Vitis`
  - `XILINX_EDITION=Vitis Unified Software Platform`
  - `XILINX_ROOT=/opt/Xilinx`
- Override any of these as environment variables when invoking the build script.
- `build_vitis_image.sh` copies the installer into
  `py2v/docker/.build-context/` for deterministic Docker builds.

