#!/usr/bin/env bash
set -o pipefail
mkdir -p sim
cd sim
{
  xvlog -sv ../tb/tb_top.v ../rtl/eigenvalue_decomposition.v ../rtl/top.v \
    && xelab tb_top -s tb_top_sim -debug typical \
    && xsim tb_top_sim -runall ;
} 2>&1 | tee xsim.log
