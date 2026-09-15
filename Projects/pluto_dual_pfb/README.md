# Pluto dual-RX PFB reference

This is a new, standalone rapid-prototyping project.  It does not modify the
existing FFT reference or RTL examples.

`main.py` follows the established project contract: it loads `params.yaml`,
exports `target(x)`, and exports an `inputs(rng, count)` generator.  A target
transaction contains a `[64 samples, 2 receivers]` complex frame and returns
`[64 bins, 2 receivers]`.  The target starts with zero FIR history so each
transaction is deterministic under the generic test harness.

`target.frequency` and `target.cycles` are the non-negotiable implementation
throughput contract: 200 MHz and 500 cycles per dual-RX frame.  A 64-sample
frame arrives every 2.5 us at 25.6 MS/s, so the RTL must finish on average one
complete transform in those 500 fabric-clock cycles.  FIFOing may add latency,
but cannot relax that sustained-rate requirement.

For continuous operation, use `pfb_reference.PolyphaseChannelizer` and call
`process(frame)` repeatedly; that preserves the four polyphase FIR frames of
history.  `main.py` exports that as `stream(frames)`, and the streaming
harness uses it in preference to `target`: hardware resets once and then runs
forever, so every frame after the first carries FIR history and does not match
the reset-per-frame `target`.  `target` stays as the memoryless single-frame
definition.

Under `sim.py` the throughput contract above is checked directly.  Beats arrive
at `N * target.frequency / target.cycles` = 25.6 MS/s while the DUT runs at 200
MHz, the harness models the buffering between those two rates, and it reports
the depth that crossing needed:

```sh
python sim.py Projects/pluto_dual_pfb conversion_XXX/rtl --fifo 16
python sim.py Projects/pluto_dual_pfb conversion_XXX/rtl --drain-stall 30
python synth.py conversion_XXX/rtl          # xc7z010 selects Vivado
```

The second run applies random backpressure to `m_axis_tready`, which the RTL
must absorb without altering an offered beat.

`generate_coeffs.py` creates a signed Q1.17 coefficient image for a
future RTL ROM.  Output is permanently bit-reversed, matching the simplest
streaming radix-2 FFT hardware and the ordering modeled by
`Projects/fft/main.py`.  Natural-order bin reordering, if wanted, belongs
after the PFB rather than in this FPGA interface contract.
