# Conversion evaluator tools

Run from the conversion root. These commands already connect to the host
toolchain; no server startup, package installation or socket probing is needed.

    sim                       # random stream, precision and cycle measurements
    sim --samples 20000        # measure a longer (or shorter) stream prefix
    sim --drain-stall 20       # additionally test randomized output backpressure
    sim --rate 50000000        # optional paced-input experiment (samples/second)
    synth                     # resource counts and synthesis-estimated Fmax
    synth --paths 5            # show worst timing paths to guide pipelining
    synth --implement         # place and route: measured routed timing

Both accept --top MODULE if automatic top detection is ambiguous. No positional
paths are needed or accepted. sim always uses this conversion's Python copy;
the runner separately tests the original Python when you finish.

An exit status of zero from sim means it obtained a measurement, not that the
design is good. Precision = log2(peak reference magnitude / RMS error).
Every additional bit matters: 14 bits is better than 13. Cycles, precision,
resources and Fmax are continuous measurements, without performance cutoffs.
First get the computation right and cycles low, but design for the target clock
from the start: routed timing (synth --implement) is a hard requirement because
the design shares the FPGA with other logic. Stimuli are fresh and unseeded.
By default input is unthrottled so cycles/sample measures design capacity rather
than an input generator deliberately paced at the target. --rate sets a paced
run in input samples per second. Latency is measured from the input beat that
completes an output's data to the beat that carries it.

IO/tb.sv contains the instantiated parameters, lane counts and widths, AXI
signal names and testbench. IO/vectors.hex holds the packed input beats;
input.log/output.log hold each accepted beat's index and cycle (output also
its packed data). IO/errors.json holds per-group measurements and the worst
mismatches. Precision is log2(peak / RMSE) per output group. These files are
plain text: write Python to decode and analyze them yourself (which output
values differ, error statistics, handshake timing) and import python/main.py
to compute generate() and its intermediate values for comparison with your RTL.
Lane 0 is least significant; complex values pack real then imaginary lanes.
For framed projects FRAC is dynamic and N is the frame length, not the inner
algorithm block size.

Synthesis Fmax is an estimate until --implement routes the design. A successful
tool execution does not alone imply timing closure: compare Fmax with target
frequency. LUT/DSP/RAM report used, available and percentage. Serial evaluations
can take several minutes; wait for the current command, do not start another.

Each evaluation appends its measurements to evald.jsonl. IO/ and synthesis/
(reports and logs) hold the most recent sim and synth run.
