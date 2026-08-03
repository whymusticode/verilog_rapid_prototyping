####### dev notes unrelated to steps.sh, dont touch
# flatpak run --command=vitis_hls com.github.corna.Vivado -version 
# 
# in py2v/ make a python script that you point to a folder location e.g. /home/me/verilog_rapid_prototyping/projects/eig_10
# 
# pipeline_stages: 200, what're pipeline stages? 
# 
# 

##### TODO:
# do research for implementations, ideas how to get good performance 
# start with bit true python simulation
# convert metric of bits error to bits precision 
# fundamentally need to change the scope to allow/encourage the AI to try entirely new algorithms 
# encourage wide bitwidths internally when we start, those won't dominate performance and might only double area in worst case, we can optimize down bitwidths as the very last step
##### end todo 

# simulation: basic first pass,
# synthesis: if I actually built this out of Xilinx logic cells, would signals settle in time for a 5ns clock? gives WNS. needs to be <= 0 for success at a clock speed. 

# do PnR to feedback hw info 
# run again with context (timing info): give model ability to modify current file, including print statements that it can collect 
# channelizer Project: 
#   pluto: ZYNQ 7010 
#   look at the IP catalog too
# harness sim output?


### manual notes: 
# grep -n "\\\$display\|sidx\b" /home/mbenton/verilog_rapid_prototyping/conversion_manual_000/build/hls/kernel.sv

# cd /home/mbenton/verilog_rapid_prototyping/conversion_manual_000/build/hls
# iverilog -g2012 -o ../sim.out kernel.sv tb.sv 2>&1 | tail -40
# vvp ../sim.out 2>&1 | tail -20


# proc = subprocess.run(
#     [hls_bin, "-f", "run_csim.tcl"],
# ...<3 lines>...
#     text=True,
# )

# between vscode+ssh+claude+xylinx, there're a lot of runaway files 
# look in /tmp/ and ~/Xilinx/
# sudo du -sh /*/  2>/dev/null | sort -h

# STEP 1: find the next free conversion_NNN folder (000, 001, ...) and copy the project into it
project=projects/eig_10
name=$(basename "$project")   # eig_10

n=0; while [ -d "conversion_$(printf %03d $n)" ]; do n=$((n+1)); done
conv="conversion_$(printf %03d $n)"; cp -r "$project" "$conv"; echo "$conv"
# conv="conversion_009"

# STEP 2: capture target fn inputs/outputs (generic, no edits to the reference) + record in params.yaml
python py2v/capture.py "$conv/$name.py"   # -> $conv/${name}_io/ (*.txt + manifest.json)
python -c "import json; m=json.load(open('$conv/${name}_io/manifest.json')); t=next(x for x in m['tensors'] if x['role']=='in'); open('$conv/params.yaml','a').write(f'\nname: $name\ninput:\n  name: {t[\"name\"]}\n  shape: {t[\"shape\"]}\n  dtype: {t[\"dtype\"]}\n')"

# STEP 3: LLM → HLS C++, csim, compare against captured I/O
python py2v/convert.py "$conv"
rc=$?

# STEP 4: optimization loop — runs whether or not step 3 passed.
# Give the optimizer fewer rounds when the first draft failed (numerical issues need bigger
# changes; if it can't fix it in 5 rounds it likely needs a full regeneration).
if [ $rc -eq 0 ]; then
    python py2v/optimize.py "$conv"
else
    echo "Step 3 failed (rc=$rc) — running optimizer in repair mode (5 rounds max)."
    python py2v/optimize.py "$conv" --max-rounds 5
fi

# python py2v/convert.py conversion_020 --from-response

