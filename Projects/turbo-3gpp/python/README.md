# Python port of turbo-3gpp-matlab

Independent NumPy implementations of all 20 numerical functions, the three
coding-chain classes, and both QPSK/AWGN plotting drivers. Octave is used only
by the tests. The original MATLAB files are unchanged. GPL-3.0-or-later;
see LICENSE and the original copyright notices.

From the repository root:

```sh
python3 -m pip install -e './python[test]'
PYTHONPATH=python python3 -m unittest discover -s python/tests -v
```

If NumPy, SciPy and Matplotlib are already installed, installation is optional.
Octave must be on PATH; differential tests fail rather than silently skip it.

```python
import numpy as np
from turbo_3gpp import turbo_encoding_chain, turbo_decoding_chain

bits = np.random.default_rng(7).integers(0, 2, 40)
encoder = turbo_encoding_chain(A=40, G=192)
decoder = turbo_decoding_chain(A=40, G=192, iterations=8)
encoded = encoder(bits)
decoded, iterations = decoder(8 * (1 - 2 * encoded))
assert np.array_equal(bits, decoded)
```

## API and behavior

Import functions directly from `turbo_3gpp`; names and positional argument order
match the `.m` files. Python vectors are 1-D NumPy arrays; MATLAB row-cell arrays
become lists of arrays. Matrices retain their MATLAB row/column layout. Indices
in interleaver/rate-matching patterns remain zero-based. Multiple MATLAB outputs
become tuples, including `constituent_encoder` → `(z, x)` and `turbo_decoder` →
`(c, iterations_performed)`. CRC failure returns an empty array. Filler bits
remain NaN; positive LLRs favor zero.

Set `turbo_3gpp.core.approx_star = True` for max-log decoding, or `False` for
exact log-MAP. This is process-global, like the source's `global approx_star`.

Chain constructors use keyword arguments with the original property names.
Call `chain(bits)` or `chain.step(bits)`. `reset()` clears HARQ buffers;
`release()` permits structural property changes and causes the next call to
set up the object again. Changes to `rv_idx`, `G`, `N_L`, or `Q_m` recompute
rate-matching patterns on the next call. Derived properties and the source's
`setupImpl`, `processTunedPropertiesImpl`, `stepImpl`, and `resetImpl` methods
are available. The coding-chain base class supplies configuration, not a codec.

Two upstream quirks are deliberately preserved:

* Encoded block lengths use `gamma = G mod C`, because the source writes `G'`
  (transpose), not `G_prime`. Some modulation/layer combinations consequently
  produce lengths whose sum differs from G; deconcatenation then rejects G
  input values. Choose G divisible by `C*N_L*Q_m` to avoid this source behavior.
* The decoder's iteration-zero hard decision uses the first K elements in
  column-major order, not the systematic row. CRC early termination preserves
  this behavior too.

An all-punctured/empty circular buffer with nonzero requested output raises
`ValueError`, avoiding the source's infinite loop. Unsupported inputs generally
raise Python exceptions rather than matching MATLAB exception identifiers.

## Plotting

`plot_BLER_vs_SNR` and `plot_SNR_vs_A` retain the original positional parameters,
channel equations, HARQ flow, stopping rules, and tab-separated result files.
They additionally return a list of dictionaries containing numerical results,
Matplotlib figures and file paths; `results_dir` selects the output directory
(created automatically). Figures can be saved with `result['figure'].savefig(...)`.
Use `MPLBACKEND=Agg` for headless execution. The plots are populated at completion
rather than redrawn after every Monte Carlo block. Small target BLER values can
require very long runs, as in MATLAB.

Python uses NumPy's random generator: the same numeric seed does **not** produce
MATLAB/Octave's random stream. The optional `rng` parameter accepts an object
with `random(n)` and `standard_normal(n)` methods, allowing exact sample replay.
Tests replay identical bits and Gaussian noise to compare simulation outputs.
The source BLER driver assumes one code block when comparing iteration counts;
that limitation is retained explicitly.

## Verification

The tests run original MATLAB algorithm bodies in Octave and transfer input and
output through MAT files. Discrete results, shapes and NaN positions must match;
floating LLRs use `rtol=2e-11, atol=2e-10` for platform rounding differences.
All 20 numerical functions have differential tests and an inventory assertion
prevents newly added numerical functions from escaping coverage.

Coverage includes:

* All four CRCs, random payloads/matrix sizes through 6999, zero-length input,
  valid CRCs and deliberately corrupted CRCs.
* Every one of the 188 supported QPP lengths, 40–6144; subblock padding and all
  three subblock interleavers; constituent encoding down to empty input.
* Segmentation boundaries at 512, 1024, 2048, 6144 and multiple-code-block
  boundaries; random transport lengths through 150000 (length calculation)
  and 24999 (bit-level segmentation).
* All redundancy versions, both limited-buffer settings, puncturing,
  repetition, zero output, filler bits, and modulation/layer length parameters.
* Exact and approximate max-star; finite/infinite LLRs, random noisy codewords,
  half iterations, zero iterations, CRC early stopping, and 6144-bit decoding.
* Chain constructors, setters, every derived property, setup, encoding,
  decoding, tunable changes, HARQ accumulation, reset and release/re-setup.
* Both plotting drivers with random payload lengths/rates and identical
  replayed channel samples; numerical files and random-sample consumption
  match Octave, and Python figures render successfully.

Octave does not provide `matlab.System` or a graphics toolkit in this environment.
The test-only adapter copies the three class files into a temporary directory,
changes the superclass to `handle`, exposes protected methods, substitutes
name/value assignment for `setProperties`, and fixes the upstream decoder's
misnamed `NRLDPCDecoder` constructor. Tests explicitly invoke lifecycle methods;
all coding algorithms remain original. Plot tests replace graphics calls with
stubs and RNG calls with supplied tapes. They compare numerical behavior, not
MATLAB System-object internals or pixel-identical rendering.

Reproducible fuzz controls (default seed 20260909, 16 random cases per base group):

```sh
FUZZ_SEED=731 FUZZ_CASES=64 PYTHONPATH=python \
  python3 -m unittest discover -s python/tests -v
```

Boundary cases and exhaustive QPP coverage run regardless of `FUZZ_CASES`.

For a JSON report with per-function differential case counts and Python function
execution counts, run `python3 python/verify.py --report python/verification.json`.
The checked-in report records the completed verification run, including seed,
runtime versions and test outcome. Function-call counts also include internal
calls; differential case counts count direct, paired Python/Octave inputs only.

## One encode → AWGN → decode BER comparison

```sh
PYTHONPATH=python python3 -m unittest discover -s python/tests -p test_ber_snr.py -v
python3 -m http.server 8765 --bind 127.0.0.1 --directory python/results
```

Open <http://127.0.0.1:8765/ber_snr_comparison.html> on this machine.
The chart uses Plotly's dark theme and embeds Plotly itself, so no CDN is needed.
Install the `test` dependencies above to include Plotly.

This single test sweeps Eₛ/N₀ from −8 to +2 dB in 2 dB steps, with 100 random
128-bit blocks per point, BPSK over AWGN and four max-log-MAP iterations.
Python calls Octave once per SNR; each implementation independently encodes,
applies the channel and decodes using identical payloads and Gaussian samples.
It asserts exact equality of all encoded/decoded bits, checks channel LLRs,
and reports each implementation's bit errors and BER.

The terminated turbo core is tested without CRC or rate matching: BER is
measured on every hard-decision payload bit, including failed blocks.
The effective rate is 128/396. SNR means energy per transmitted coded BPSK
symbol divided by N₀, not energy per information bit. Zero observed errors are
stored as BER=0; log-plot markers use a one-sided 95% binomial upper bound,
with the actual counts shown on hover.

Outputs are `python/results/ber_snr_comparison.html`, a JSON report with the
same basename, and `ber_snr_replay.npz` containing every payload, noise sample
and decoded output. Set `BER_BLOCKS`, `BER_SEED` or `BER_OUTPUT_DIR` to override
the number of blocks, seed or output location.
