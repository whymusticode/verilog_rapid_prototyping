# LTE SIB1 receiver on a continuous ADC stream

`main.py` is the `convert.py` / `sim.py` target. It models what a Pluto
(AD9363) sees when tuned to an LTE FDD downlink: an endless stream of 12-bit
complex ADC samples at 15.36 MS/s from one 10 MHz cell (50 RB, normal cyclic
prefix). The receiver must find the cell, decode its MIB, and decode every
SIB1 transmission: the one broadcast message every cell sends with the LTE
turbo code, scrambled only with public identities (SI-RNTI and the cell ID).
The same receiver runs on real captures with `sib1.py`, and a passing CRC24A
plus the PLMN, tracking area code and cell identity matching a phone's
field-test screen shows it works on air.

```sh
python3 Projects/lte-sib1/main.py                 # reference results per SNR
python3 sim.py -p Projects/lte-sib1                # write input/output streams only
python3 Projects/lte-sib1/sib1.py --selftest       # synthetic cells, all bandwidths
python3 Projects/lte-sib1/sib1.py --freq 739e6     # capture with a Pluto and decode
python3 convert.py -m claude -i Projects/lte-sib1
```

NumPy, SciPy and PyYAML are required; `sib1.py` capture also needs libiio's
Python bindings.

## Stream

`generate(samples)` draws one cell per run:
- PCI 0..503, a random SFN, 1, 2 or 4 CRS antenna ports;
- CFI 1..3, PHICH normal or extended duration and Ng 1/6..2;
- SIB1 scheduled by DCI format 1A (localized or distributed VRBs, gap 1 or 2)
  or 1C in the common search space (aggregation 4 or 8), with a random
  allocation and TBS below code rate `max_code_rate`;
- other users' data in each other PRB with probability `traffic`, and random
  PDCCH content in the other subframes;
- an independent two-path channel per antenna port, white noise at an SNR from
  `snr_db`, and one crystal error (`clock_ppm`) that sets both the carrier
  offset (at `carrier_hz`) and the sample-clock drift;
- quantization to 12-bit codes at `adc_rms` RMS. The stream starts at a random
  point of a frame.

Not modeled: TDD, extended cyclic prefix, other bandwidths, more than one cell,
time-varying fading, IQ imbalance, DC offset, phase noise.

## Output

Per SIB1 transmission the reference receiver finds, in time order: a 32-bit
descriptor, most significant bit first (CRC24A passed 1, PCI 9, SFN 10, TBS 12),
then TBS payload hard decisions. Measurement groups are `crc`, `pci`, `sfn`,
`tbs` and `payload` (primary).

SIB1 repeats every 20 ms (subframe 5 of even frames) with redundancy versions
0, 2, 3, 1 over each 80 ms period; versions 1 and 2 alone are often not
decodable. Like a UE, the reference soft-combines each transmission with the
earlier ones of its period, so each record's CRC and payload are those of the
combined decode. Each record is determined (`ready`) once its subframe has
arrived plus one cyclic prefix, and the reference decodes it from exactly those
samples: the reference is causal.

## Reference

`lte_dl.py` holds the transmitter and the reference receiver (section numbers
in comments refer to 3GPP TS 36.211/212/213/331):
1. PSS search over carrier-offset hypotheses on a 1.92 MS/s copy; the strongest
   distinct hypotheses are refined and the one whose SSS matches best is kept
   (Zadoff-Chu PSS correlation alone is ambiguous in whole subcarriers).
2. Fine carrier offset from cyclic-prefix correlation over every symbol, PSS
   timing every 5 ms fitted to a line (sample-clock drift), SSS for PCI and
   frame timing, then a CRS-based residual offset.
3. Per subframe: FFT, CRS channel estimates per port (3-tap smoothing,
   frequency then time interpolation), transmit-diversity (SFBC/FSTD) combining.
4. MIB from each frame (convolutional code; 1/2/4 ports from the CRC mask).
5. In SIB1 subframes: PCFICH (CFI), PHICH and PDCCH resource layout, blind
   decoding of DCI 1A/1C addressed to SI-RNTI, the PDSCH allocation, QPSK
   LLRs, descrambling, rate dematching and turbo decoding with soft combining
   (`turbo_3gpp/`, the same chain as the turbo-3gpp project; max-log, 8
   iterations, stopping early on CRC24A).

`sib1.py` runs the same receiver on Pluto captures or files, prints the parsed
SIB1, and can export the SIB1 LLRs; `--selftest` checks 1.4 to 20 MHz cells,
1/2/4 ports and every DCI allocation type.

Reference results from `python3 main.py` (40 s, 62 cells; payload bits are
compared with what was transmitted):

| SNR dB | records | CRC ok | payload BER |
|---:|---:|---:|---:|
| 0 | 30 | 28 | 4.2e-2 |
| 3 | 22 | 22 | 0 |
| 6 | 14 | 14 | 0 |
| 10 | 20 | 20 | 0 |
| 20 | 14 | 14 | 0 |
| 30 | 28 | 28 | 0 |

Throughput target: 100 MHz / 15.36 MS/s = 6.51 clock cycles per ADC sample.
