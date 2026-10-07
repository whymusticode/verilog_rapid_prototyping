# Pluto dual-RX PFB reference

This is a new, standalone rapid-prototyping project.  It does not modify the
existing FFT reference or RTL examples.

`main.py` exports `generate(samples)`, the stream `sim.py` measures: one input
sample is a complex sample from each of the two receivers (4 scalars, 16-bit
FRAC 16), and the channelizer runs continuously from one reset, so each
64-sample block's `[64 bins, 2 receivers]` output (16-bit FRAC 17) is
determined once that block has arrived and carries the four polyphase FIR
blocks of history. `target(x)` is one block after reset, for interactive use;
`pfb_reference.PolyphaseChannelizer.process` is the stateful model.

`target.sample_rate` (25.6 MS/s per receiver, one 64-sample transform every
2.5 us) at `target.frequency` (100 MHz) is the throughput contract: about 3.9
fabric cycles per input sample on average. FIFOing may add latency but cannot
relax that sustained rate. With `--rate` the harness paces input at a given
sample rate, models the buffering between the two clocks and reports the depth
that crossing needed:

```sh
python sim.py conversion_XXX/ Projects/pluto_dual_pfb --rate 25600000 --fifo 16
python sim.py conversion_XXX/ Projects/pluto_dual_pfb --drain-stall 30
python synth.py conversion_XXX/              # xc7z010 selects Vivado
```

The second run applies random backpressure to `m_axis_tready`, which the RTL
must absorb without altering an offered beat.

`generate_coeffs.py` creates a signed Q1.17 coefficient image for a
future RTL ROM.  Output is permanently bit-reversed, matching the simplest
streaming radix-2 FFT hardware and the ordering modeled by
`Projects/fft/main.py`.  Natural-order bin reordering, if wanted, belongs
after the PFB rather than in this FPGA interface contract.
