####### dev notes unrelated to steps.sh, dont touch
# flatpak run --command=vitis_hls com.github.corna.Vivado -version 
# 
# in py2v/ make a python script that you point to a folder location e.g. /home/me/verilog_rapid_prototyping/projects/eig_10
# 
# pipeline_stages: 200, what're pipeline stages? 
# 
# 

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