#-----------------------------------------------------------------
# Vitis v2025.2 (64-bit)
# Start of session at: Wed Jun 10 15:40:09 2026
# Current directory: /home/mbenton/verilog_rapid_prototyping
# Command line: vitis -i
# Journal file: vitis_journal.py
# Batch mode: $XILINX_VITIS/bin/vitis -s /home/mbenton/verilog_rapid_prototyping/vitis_journal.py
#-----------------------------------------------------------------

#!/usr/bin/env python3
import vitis
import vitis, tempfile
td=tempfile.mkdtemp()
c=vitis.create_client()
c.set_workspace(td)
#[Out]# True
comp=c.create_hls_component(name='test')
print(type(comp))
print([m for m in dir(comp) if not m.startswith('_')])
c.close()
#[Out]# True
vitis.dispose()
