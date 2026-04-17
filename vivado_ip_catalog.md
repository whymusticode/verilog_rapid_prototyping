# Vivado IP Catalog Summary

**Part:** xc7a35tcpg236-1 (Basys3 / Artix-7)
**Vivado:** 2025.2.1
**Generated:** Fri Apr 17 09:49:02 EDT 2026
**Total supported IPs:** 203 (195 instantiable + 8 errored)
**Source:** `/home/me/REPOS/verilog_rapid_prototyping/ip_catalog.txt`

The Basys3 is a small Artix-7 device (~33K LUTs, no GT transceivers, no hard DDR, no PCIe). Many IPs listed as "Artix-7 supported" cannot realistically fit or run on this specific part. See `Likely unusable on Basys3` below before picking.

---

## Category Counts

| Category | Count |
|---|---|
| AXI_Infrastructure | 43 |
| AXI_Peripherals | 21 |
| DSP_and_Math / General | 17 |
| DSP_and_Math / Error_Correction | 10 |
| Memory_Solutions / Internal_Memory | 9 |
| Memory_Solutions / External_Memory | 2 |
| Multimedia_and_Vision (Audio / Video / Vis / Connectivity) | 23 |
| Interfaces / Ethernet | 6 |
| Interfaces / PCI + PCIe | 5 |
| Interfaces / Serial | 2 |
| Interfaces / Data_Converters | 1 |
| Interfaces / Storage | 1 |
| Wireless | 6 |
| Foundational / Basic | 12 |
| Foundational / Clock_and_Reset | 3 |
| Foundational / Debug_and_Verification | 12 |
| Foundational / DFX | 4 |
| Foundational / High_Speed_Serial | 3 |
| Foundational / IO_Interfaces | 3 |
| Foundational / Soft_Error_Mitigation | 1 |
| Foundational / Triple_Modular_Redundancy | 5 |
| Embedded_Processors | 10 |
| Automotive_and_Industrial | (in AXI_Peripherals: CAN, CANFD) |
| Kernels | 1 |
| Standard_Bus_Interfaces | 1 |

---

## Unavailable IPs (ERR entries)

These 8 IPs exist in the catalog but cannot be instantiated for this part.

| IP | Reason |
|---|---|
| `ats_switch` | IP Integrator subcore use only (Coretcl 2-1297) |
| `fast_adapter` | No IP accessible for xc7a35tcpg236-1 (Coretcl 2-1132) |
| `ps11_vip` | IP Integrator subcore use only |
| `psx_vip` | IP Integrator subcore use only |
| `v_hdmi_rx_ss` | No IP accessible for this part |
| `v_hdmi_tx_ss` | No IP accessible for this part |
| `v_smpte_sdi` | No IP accessible for this part |
| `versal_cips_ps_vip` | IP Integrator subcore use only |

---

## Likely Unusable on Basys3

Conservative flag list. These are listed as "Artix-7 compatible" but require resources the xc7a35tcpg236-1 lacks: (a) GTP/GTX transceivers (Basys3 has none), (b) external DDR memory controller hardware (none on Basys3), (c) >30K LUTs minimum. Trying these will fail at IP-config, implementation, or on-chip.

### No chance without transceivers (Basys3 has zero GTP/GTX/GTH)
| IP | Reason |
|---|---|
| `aurora_8b10b` | Multi-lane gigabit serial, GTP required |
| `axi_10g_ethernet` | 10G needs GTP/GTH |
| `axi_chip2chip` | Aurora-based, GTP required |
| `axi_ethernet` (1G/2.5G) | SGMII/RGMII PHY + MAC, targets GT or SGMII-PHY hardware |
| `axi_pcie` | PCIe integrated block (none in xc7a35t) |
| `cpri` | Wireless GT-based link |
| `gig_ethernet_pcs_pma` | Requires GT or LVDS (Artix-7 -2 or faster); Basys3 is -1 |
| `gtwizard` | 7-Series transceiver wrapper; no GTs on this part |
| `ibert_7series_gtp` | GT BER tester |
| `mipi_csi2_rx_subsystem`, `mipi_csi2_tx_subsystem`, `mipi_dphy`, `mipi_dsi_tx_subsystem` | D-PHY requires specific I/O, generally not supported on xc7a35tcpg236-1 package |
| `pcie_7x` | 7-Series integrated PCIe block (none on xc7a35t) |
| `pci32`, `pci64` | Parallel PCI 3.0, physically impractical on Basys3 |
| `picxo_fracxo` | Uses transceiver reference clock |
| `quadsgmii` | Quad-lane SGMII, GT required |
| `srio_gen2` | Serial RapidIO, GT required |
| `ten_gig_eth_mac`, `ten_gig_eth_pcs_pma` | 10G, GT required |
| `tri_mode_ethernet_mac` | Needs external GMII PHY + PCS/PMA via GT or LVDS (Basys3 has no Ethernet PHY) |
| `v_dp_rxss1`, `v_dp_txss1` | DisplayPort 1.4, GT required |
| `vid_phy_controller` | Wraps GT for video PHY |
| `xdma` | PCIe DMA/Bridge |

### No chance without external DRAM controller hardware / DDR pins
| IP | Reason |
|---|---|
| `mig_7series` | MIG DDR3/DDR2/LPDDR2 — Basys3 has no DRAM on board |
| `axi_emc` | External memory controller; no parallel SRAM/PSRAM on Basys3 |

### Too large / heavyweight soft IP (won't fit or not worth the 33K LUT budget)
| IP | Reason |
|---|---|
| `axi_usb2_device` | Large; also needs external USB PHY |
| `ldpc` | LDPC enc/dec is big — typical >20K LUTs for useful codes |
| `polar`, `convolution`, `viterbi`, `rs_decoder`, `rs_encoder`, `sid` | Doable but size-sensitive; evaluate per-config |
| `tcc_decoder_3gppmm`, `tcc_encoder_3gpp`, `tcc_encoder_3gpplte` | 3GPP Turbo codecs; heavy |
| `dft`, `lte_fft`, `pc_cfr` | Aimed at wireless baseband, large |
| `system_cache` | Multi-port cache, targets MPSoC class designs |
| `v_hdmi_*`, `v_smpte_sdi` | Also errored above — need GT + >35K LUTs anyway |
| `v_dp_*`, `v_multi_scaler`, `v_warp_*`, `v_proc_ss`, `v_mix` | Video subsystems generally too large or need GT |
| `v_frmbuf_rd`, `v_frmbuf_wr` | Need DDR — no DDR on Basys3 |
| `axi_vdma` | Needs memory-side DDR for frame buffers |
| `rtl_kernel_wizard` | Targets Alveo/XRT shells |
| `sdx_memory_subsystem`, `sdx_stream_subsystem` | SDx/XRT flow |
| `shell_utils_addr_remap` | Platform shell infrastructure |

### Probably fine but size/quality check before use
`microblaze`, `microblaze_riscv` (full MicroBlaze): fits if you keep caches small; use `microblaze_mcs` for typical Basys3 work. `axi_mcdma`, `axi_dma` with SG: large, prefer `axi_cdma` or simple DMA. `v_mix` with many layers: size grows fast.

### Safe subsystems that target hard-block-less FPGAs (usable)
`audio_formatter`, `v_tc`, `v_tpg`, `v_vid_in_axi4s`, `v_axi4s_vid_out`, `v_axi4s_remap`, `v_demosaic`, `v_gamma_lut`, `v_scenechange` are all usable for VGA-style video pipelines driving the Basys3's on-board VGA connector if you supply the pixel clock yourself.

---

## AXI Infrastructure

Bread-and-butter interconnect and utility cores for memory-mapped AXI. Most of these cost very little on Basys3.

- **ahblite_axi_bridge** v3.0 — AHB-Lite to AXI Bridge. Connects AHB-Lite masters to an AXI slave. Key: `C_S_AHB_DATA_WIDTH=32, C_M_AXI_DATA_WIDTH=32, C_EXTENDED_ADDRESS_WIDTH=32, C_AHB_AXI_TIMEOUT=0`.
- **axi_ahblite_bridge** v3.0 — AXI to AHB Bridge (reverse direction).
- **axi_apb_bridge** v3.0 — AXI Master to APB slave bridge.
- **axi4stream_vip** v1.1 — Verification IP for simulating AXI4-Stream masters/slaves.
- **axi_cdma** v4.1 — Central DMA, memory-to-memory (single AXI master). Small DMA option. Key: `C_M_AXI_DATA_WIDTH=32, C_ADDR_WIDTH=32, C_INCLUDE_SG=1, C_M_AXI_MAX_BURST_LEN=16, C_INCLUDE_DRE=0, C_USE_DATAMOVER_LITE=0`.
- **axi_chip2chip** v5.0 — AXI bridge over Aurora between two FPGAs. Requires transceivers; not for Basys3.
- **axi_clock_converter** v2.1 — CDC between AXI master/slave. Key: `ADDR_WIDTH=32, DATA_WIDTH=32, PROTOCOL=AXI4, ID_WIDTH=0`.
- **axi_crossbar** v2.1 — N-master to M-slave AXI crossbar. Key: `ADDR_WIDTH=32, DATA_WIDTH=32, CONNECTIVITY_MODE=SAMD, NUM_SI, NUM_MI, ADDR_RANGES=1`.
- **axi_data_fifo** v2.1 — Buffer FIFO between AXI master/slave. Key: `ADDR_WIDTH=32, DATA_WIDTH=32, WRITE_FIFO_DEPTH=0, READ_FIFO_DEPTH=0, PROTOCOL=AXI4, READ_WRITE_MODE=READ_WRITE`.
- **axi_datamover** v5.1 — Building block for custom DMA (MM2S and S2MM). Key: `c_m_axi_mm2s_data_width=32, c_m_axi_s2mm_data_width=32, c_addr_width=32, c_include_mm2s=Full, c_include_s2mm=Full, c_include_mm2s_dre=false`.
- **axi_dma** v7.1 — Full AXI DMA engine. Key: `c_m_axi_mm2s_data_width=32, c_m_axi_s2mm_data_width=32, c_include_sg=1, c_include_mm2s=1, c_include_s2mm=1, c_micro_dma=0, c_sg_length_width=14`.
- **axi_dwidth_converter** v2.1 — Increase/decrease AXI data width. Key: `ADDR_WIDTH=32, ACLK_ASYNC=0, ACLK_RATIO=1:2`.
- **axi_fifo_mm_s** v4.3 — MM-to-Stream FIFO bridge. Cut-through or packet mode; choose FIFO depth and AXI/AXI-Lite data interface.
- **axi_firewall** v1.2 — Protocol firewall, blocks upstream violations/timeouts.
- **axi_jtag** v1.0 — AXI-to-JTAG converter. Key: `C_S_AXI_ADDR_WIDTH=5, C_S_AXI_DATA_WIDTH=32, C_TCK_CLOCK_RATIO=8`.
- **axi_lmb_bridge** v1.0 — AXI interconnect to LMB accesses. Key: `C_ADDR_WIDTH=32, C_DATA_WIDTH=32, C_AXI_R_DEPTH=8, C_AXI_W_DEPTH=8`.
- **axi_mcdma** v1.2 — Multi-channel DMA. Larger than axi_dma; typically scatter-gather + multiple TX/RX channels.
- **axi_memory_init** v1.0 — Writes an init value to all MI address locations on reset.
- **axi_mm2s_mapper** v1.1 — Encodes/decodes AXI MM transactions into AXI-Stream. For tunneling MM traffic over a stream fabric.
- **axi_mmu** v2.1 — Address range decode and remap.
- **axi_perf_mon** v5.0 — Measures throughput/latency across AXI slots.
- **axi_protocol_checker** v2.0 — Monitors and reports AXI protocol violations.
- **axi_protocol_converter** v2.1 — AXI4 <-> AXI3 <-> AXI4-Lite protocol converter.
- **axi_register_slice** v2.1 — Pipeline stage between AXI master/slave. Key: `ADDR_WIDTH=32, DATA_WIDTH=32, ID_WIDTH=0, PROTOCOL=AXI4, SLR_CROSSING=Off, REG_*=1/auto_pipelined`.
- **axi_sideband_util** v1.0 — Insert/recover info into AXI USER signals for SmartConnect.
- **axi_switch** v1.0 — Lighter-weight crossbar alternative (RTL Interconnect).
- **axi_traffic_gen** v3.0 — Traffic generator for stress testing. Key: `C_ATG_MODE=AXI4, C_ATG_MODE_L2=Advanced, ATG_HLT_STATIC_LENGTH=16, C_ATG_REPEAT_TYPE=One_Shot`.
- **axi_vdma** v6.3 — Video DMA with frame-sync. Needs DDR memory; skip on Basys3.
- **axi_vfifo_ctrl** v2.0 — Parameterizable multi-channel virtual FIFO controller.
- **axi_vip** v1.1 — Verification IP for simulating AXI3/AXI4/AXI-Lite masters/slaves.
- **axis_accelerator_adapter** v2.1 — Bridge AXI4-Stream to BRAM/FIFO toward accelerators.
- **axis_broadcaster** v1.1 — Replicate 1 SI stream to N MI streams. `M_TDATA_NUM_BYTES`, `S_TDATA_NUM_BYTES`, `NUM_MI` set fanout.
- **axis_clock_converter** v1.1 — CDC between AXI4-Stream master/slave. Key: `TDATA_NUM_BYTES, TUSER_WIDTH`.
- **axis_combiner** v1.1 — Merge multiple SI streams into one MI stream.
- **axis_data_fifo** v2.0 — Stream-side buffering FIFO. Key: `TDATA_NUM_BYTES, FIFO_DEPTH, IS_ACLK_ASYNC=0, HAS_TLAST, HAS_TKEEP`.
- **axis_dwidth_converter** v1.1 — Change data-path width between stream master/slave.
- **axis_interconnect** v1.1 — 16×16 switch + FIFOs + reg slices + width/clock converters.
- **axis_protocol_checker** v2.0 — Monitor AXI4-Stream protocol violations.
- **axis_register_slice** v1.1 — Stream pipeline stage.
- **axis_subset_converter** v1.1 — Adjust TDATA/TUSER/TID/TDEST/TKEEP/TSTRB subsets.
- **axis_switch** v1.1 — AXI4-Stream N-to-M switch.
- **sdx_memory_subsystem** v1.0 — SDx/XRT memory subsystem (not for Basys3 standalone).
- **sdx_stream_subsystem** v1.0 — SDx/XRT stream subsystem.
- **shell_utils_addr_remap** v1.0 — Platform shell address remapper.
- **smartconnect** v1.0 — AXI SmartConnect (auto-negotiates width/clock/protocol). Prefer over `axi_interconnect` for new designs. No user-facing params beyond NUM_SI/NUM_MI/clock binding.

---

## AXI Peripherals

Standard embedded peripherals attached to AXI-Lite / AXI4. Mostly tiny (a few hundred LUTs) and perfect fits for Basys3.

- **amm_axi_bridge** v1.0 — Avalon master bridge to AXI4. Key: `C_AVA_ADDR_WIDTH=32, C_AVA_DATA_WIDTH=32, C_AVA_BURSTCOUNTWIDTH=11, C_NUM_MASTERS=1, C_MODE=2`.
- **axi_amm_bridge** v1.0 — AXI4/AXI4-Lite slave to Avalon traffic.
- **axi_emc** v3.0 — External memory controller (parallel flash/SRAM). Basys3 has no parallel memory device.
- **axi_epc** v2.0 — External Peripheral Controller. Generic parallel peripheral bus.
- **axi_ethernet** v8.0 — 1G/2.5G Ethernet Subsystem. Needs external PHY and GT/SGMII — not on Basys3.
- **axi_ethernetlite** v3.0 — 10/100 Ethernet MAC. Still needs external MII PHY — Basys3 has no Ethernet PHY.
- **axi_gpio** v2.0 — Simple GPIO (in/out/tri + optional second channel + optional interrupt). Key: `C_GPIO_WIDTH=32, C_GPIO2_WIDTH=32, C_IS_DUAL=0, C_ALL_INPUTS=0, C_ALL_OUTPUTS=0, C_INTERRUPT_PRESENT=0, C_DOUT_DEFAULT=0x00000000, C_TRI_DEFAULT=0xFFFFFFFF`.
- **axi_hbicap** v1.0 — HB ICAP controller for partial reconfig. Key: `C_ICAP_DWIDTH=32, C_FAMILY=artix7, C_MODE=0, C_READ_FIFO_DEPTH=64, C_WRITE_FIFO_DEPTH=64, C_INCLUDE_STARTUP=0`.
- **axi_hwicap** v3.0 — Classic ICAPE2 access. Key: `C_ICAP_DWIDTH=32, C_FAMILY=artix7, C_MODE=0, C_READ_FIFO_DEPTH=128, C_WRITE_FIFO_DEPTH=64, C_INCLUDE_STARTUP=0`.
- **axi_i3c** v1.0 — MIPI I3C v1.1.1 controller. Key: `AXI_CLK_FREQ=100000, SCL_CLK_FREQ=1000, DEVICE_ROLE=0, NUM_TARGETS=1, CMD_RESP_FIFO_DEPTH=16, HAS_STATIC_ADDRESS=0`.
- **axi_iic** v2.1 — Standard I2C controller. Key: `IIC_FREQ_KHZ=100, AXI_ACLK_FREQ_MHZ=25, TEN_BIT_ADR=7_bit, C_SCL_INERTIAL_DELAY=0, C_GPO_WIDTH=1`.
- **axi_intc** v4.1 — Interrupt controller (concentrates multiple IRQs). Key: `C_NUM_INTR_INPUTS=1, C_KIND_OF_INTR=0xFFFFFFFF, C_KIND_OF_EDGE=0xFFFFFFFF, C_KIND_OF_LVL=0xFFFFFFFF, C_ENABLE_ASYNC=0, C_HAS_FAST=0, C_HAS_IVR=1, C_HAS_SIE=1`.
- **axi_quad_spi** v3.2 — Standard/Dual/Quad SPI controller. Key: `C_SPI_MODE=0, C_NUM_SS_BITS=1, C_NUM_TRANSFER_BITS=8, C_SCK_RATIO=16, C_FIFO_DEPTH=16, C_SPI_MEMORY=1, C_SPI_MEM_ADDR_BITS=24, C_TYPE_OF_AXI4_INTERFACE=0, C_DUAL_QUAD_MODE=0, C_USE_STARTUP=1`.
- **axi_tft** v2.0 — 256k-color TFT display controller.
- **axi_timebase_wdt** v3.0 — 32-bit timebase + watchdog.
- **axi_timer** v2.0 — 32/64-bit timer. Key: `COUNT_WIDTH=32, mode_64bit=0, enable_timer2=1, GEN0_ASSERT=Active_High, TRIG0_ASSERT=Active_High`.
- **axi_uart16550** v2.0 — Full 16550-compatible UART.
- **axi_uartlite** v2.0 — Minimal UART. Key: `C_BAUDRATE=9600, C_DATA_BITS=8, C_USE_PARITY=0, C_ODD_PARITY=0, C_S_AXI_ACLK_FREQ_HZ=100000000, PARITY=No_Parity`.
- **axi_usb2_device** v5.0 — USB 2.0 device. Large; needs external USB PHY.
- **can** v5.1 — ISO 11898-1 CAN 2.0A/B, up to 1 Mbps. Requires license/purchase for non-eval.
- **canfd** v3.0 — CAN FD, >4 Mbps. Requires Bosch protocol license.

---

## Memory Solutions

- **axi_bram_ctrl** v4.1 — AXI -> BRAM wrapper. Key: `DATA_WIDTH=32, MEM_DEPTH=8192, PROTOCOL=AXI4, ID_WIDTH=0, SINGLE_PORT_BRAM=0, ECC_TYPE=0, USE_ECC=0, READ_LATENCY=1, SUPPORTS_NARROW_BURST=1`.
- **blk_mem_gen** v8.4 — Block Memory Generator, primary BRAM IP. Key: `Memory_Type=Single_Port_RAM, Write_Width_A=16, Read_Width_A=16, Write_Depth_A=16, Operating_Mode_A=WRITE_FIRST, Algorithm=Minimum_Area, Interface_Type=Native, Enable_A=Use_ENA_Pin, Load_Init_File=false, ecctype=No_ECC, Register_PortA_Output_of_Memory_Primitives=true, Byte_Size=9, use_bram_block=Stand_Alone`. Supports ROM/RAM, single/dual/true-dual/simple-dual port, AXI or Native interface.
- **dist_mem_gen** v8.0 — Distributed (LUT-based) memory. Key: `memory_type=single_port_ram, data_width=16, depth=64, Pipeline_Stages=0, input_options=non_registered, output_options=non_registered, coefficient_file=no_coe_file_loaded`. Use for small, fast memories (<1024 words typically).
- **ecc** v2.0 — Hamming or HSIAO encoder/decoder for arbitrary data widths.
- **fifo_generator** v13.2 — Parameterizable FIFO (sync/async, BRAM/distributed/built-in, AXI or Native). Key: `Fifo_Implementation=Common_Clock_Block_RAM, Input_Data_Width=18, Input_Depth=1024, Output_Data_Width=18, Output_Depth=1024, Performance_Options=Standard_FIFO, INTERFACE_TYPE=Native, PROTOCOL=AXI4, Reset_Type=Synchronous_Reset, Enable_ECC=false, Read_Data_Count=false, Programmable_Full_Type=No_Programmable_Full_Threshold`.
- **lmb_bram_if_cntlr** v4.0 — LMB-to-BRAM controller (for MicroBlaze local memory).
- **lmb_v10** v3.0 — LMB bus itself (connects MicroBlaze I/D ports to BRAM).
- **mig_7series** v4.2 — DDR3/DDR2/LPDDR2 memory controller. Not usable — Basys3 has no external DRAM.
- **soft_ecc_proxy** v1.1 — Proxy for soft-ECC integration.

---

## DSP and Math

### General

- **c_accum** v12.0 — Accumulator (signed/unsigned, 1-256 bit inputs, 1-258 bit outputs).
- **c_addsub** v12.0 — Adder / subtractor / adder-subtractor (signed or unsigned, 1-256 bit). Can target DSP48.
- **c_counter_binary** v12.0 — Up / down / up-down counter, output up to 256 bits, programmable count limit, external or constant increment.
- **cic_compiler** v4.0 — Cascaded Integrator-Comb filter. Key: `Filter_Type=Interpolation, Input_Data_Width=18, Output_Data_Width=22, Number_Of_Channels=1, Number_Of_Stages=3, Fixed_Or_Initial_Rate=4, Maximum_Rate=4, Minimum_Rate=4, Differential_Delay=1, Quantization=Full_Precision, Sample_Rate_Changes=Fixed, Use_Xtreme_DSP_Slice=true`.
- **cmpy** v6.0 — Complex multiplier, signed two's complement, widths up to 63 bits.
- **cordic** v6.0 — CORDIC for trig/hyp/sqrt/atan2/rotate. Key: `Functional_Selection=Rotate, Architectural_Configuration=Parallel, Input_Width=16, Output_Width=16, Data_Format=SignedFraction, Phase_Format=Radians, Round_Mode=Truncate, Pipelining_Mode=Maximum, Coarse_Rotation=true, Iterations=0`.
- **dds_compiler** v6.0 — Direct Digital Synthesis / NCO. Key: `Channels=1, Output_Selection=Sine_and_Cosine, Mode_of_Operation=Standard, Amplitude_Mode=Full_Range, OUTPUT_FORM=Twos_Complement, Memory_Type=Auto, DSP48_Use=Minimal, Noise_Shaping=Auto, Frequency_Resolution=0.4, DDS_Clock_Rate=100, Has_Phase_Out=true`.
- **dft** v4.2 — Discrete Fourier Transform (LTE/5G point sizes). Larger than xfft.
- **div_gen** v5.1 — Divider (LUT-Mult / Radix-2 / High Radix). Key: `algorithm_type=Radix2, dividend_and_quotient_width=16, divisor_width=16, fractional_width=16, operand_sign=Signed, remainder_type=Remainder, latency=20, latency_configuration=Automatic, clocks_per_division=1, divide_by_zero_detect=false, FlowControl=NonBlocking`.
- **dsp_macro** v1.0 — User-defined DSP48 operation from symbolic expressions.
- **fir_compiler** v7.2 — Multi-rate FIR filter. Key: `Filter_Type=Single_Rate, Filter_Architecture=Systolic_Multiply_Accumulate, CoefficientSource=Vector, Coefficient_Width=16, Data_Width=16, Output_Width=24, Coefficient_Sets=1, Number_Channels=1, Number_Paths=1, Decimation_Rate=1, Interpolation_Rate=1, Coefficient_Reload=false, Data_Sign=Signed, Coefficient_Sign=Signed, Output_Rounding_Mode=Full_Precision, Quantization=Integer_Coefficients`.
- **floating_point** v7.1 — Single/double/half precision add/sub/mul/div/sqrt/compare/convert/log/exp/FMA. Key: `Operation_Type=Add_Subtract, A_Precision_Type=Single, Result_Precision_Type=Single, C_A_Exponent_Width=8, C_A_Fraction_Width=24, C_Optimization=Speed_Optimized, C_Mult_Usage=Full_Usage, C_Latency=12, C_Rate=1, Flow_Control=Blocking, Maximum_Latency=true`.
- **lte_fft** v2.1 — LTE FFT (1536-pt, runtime-configurable length/prefix/scale).
- **mult_gen** v12.0 — Parallel / constant-coefficient multiplier (DSP48 or LUT). Key: `MultType=Parallel_Multiplier, Multiplier_Construction=Use_LUTs, PortAWidth=18, PortBWidth=18, PortAType=Signed, PortBType=Signed, OptGoal=Speed, PipeStages=1, OutputWidthHigh=35, OutputWidthLow=0, UseRounding=false, RoundPoint=0, CcmImp=Distributed_Memory, ConstValue=129`.
- **xbip_multadd** v3.0 — Multiply-add in DSP48 slices.
- **xfft** v9.1 — FFT core (8 to 65536 pt, 1–12 channels, fixed-point or single-precision float). Key: `transform_length=1024, input_width=16, phase_factor_width=16, data_format=fixed_point, scaling_options=scaled, channels=1, output_ordering=bit_reversed_order, implementation_options=automatically_select, butterfly_type=use_luts, complex_mult_type=use_mults_resources, memory_options_data=block_ram, run_time_configurable_transform_length=false, target_clock_frequency=250, target_data_throughput=50, rounding_modes=truncation, cyclic_prefix_insertion=false, super_sample_rates=1`.

### Error Correction (Note: many exceed Basys3 budget for production-scale codes)

- **convolution** v9.0 — Convolutional Encoder with optional puncturing.
- **ldpc** v2.0 — LDPC encoder or decoder for Quasi-Cyclic codes.
- **polar** v1.1 — Polar Encoder or Decoder.
- **rs_decoder** v9.0 — Reed-Solomon Decoder.
- **rs_encoder** v9.0 — Reed-Solomon Encoder.
- **sid** v8.0 — Interleaver / De-interleaver (Forney Convolutional or Rectangular Block, up to 256-bit symbols).
- **tcc_decoder_3gppmm** v2.0 — 3GPP Mixed Mode Turbo Decoder (LTE + UMTS).
- **tcc_encoder_3gpp** v5.0 — 3GPP Turbo Encoder (UMTS).
- **tcc_encoder_3gpplte** v4.0 — 3GPPLTE Turbo Encoder.
- **viterbi** v9.1 — Viterbi Decoder (parameterizable constraint length / traceback).

---

## Embedded Processors

- **microblaze** v11.0 — Full MicroBlaze 32/64-bit soft CPU. Cache, MMU, FPU, fault tolerance optional. Key: `C_DATA_SIZE=32, C_ADDR_SIZE=32, C_AREA_OPTIMIZED=0, C_DCACHE_BYTE_SIZE=8192, C_ICACHE_BASEADDR/HIGHADDR, C_D_AXI=0, C_I_AXI=0, C_D_LMB=1, C_I_LMB=1, C_DEBUG_ENABLED=1, C_FAULT_TOLERANT=0, C_FREQ=0, C_ENDIANNESS=1, C_INTERCONNECT=2, C_FSL_LINKS=0, C_ENABLE_CONVERSION=1`. Can fit on Basys3 but keep caches small.
- **microblaze_riscv** v1.0 — MicroBlaze V (RISC-V ISA). Same footprint class.
- **microblaze_mcs** v3.0 — Light MCU wrapper around MicroBlaze with peripherals bundled. Recommended for Basys3 simple control use. Key: `MEMSIZE=16384, FREQ=100.0, OPTIMIZATION=0, USE_UART_RX=0, USE_UART_TX=0, UART_BAUDRATE=9600, USE_GPI1..4, USE_GPO1..4, USE_FIT1..4, USE_PIT1..4, INTC_USE_EXT_INTR=0, DEBUG_ENABLED=0, TRACE=0, JTAG_CHAIN=2, USE_BSCAN=0, USE_IO_BUS=0, ECC=0`.
- **microblaze_mcs_riscv** v1.0 — MCS V with RISC-V core. Same interface, same parameter family as `microblaze_mcs`.
- **mdm** v3.2 — MicroBlaze Debug Module (MDM). Connects MicroBlaze cores to JTAG.
- **mdm_riscv** v1.0 — MDM implementing RISC-V debug protocol (for microblaze_riscv).
- **system_cache** v5.0 — Multi-port MicroBlaze cache with ACE/CCIX. Oversized for Basys3.
- **mailbox** v2.1 — Inter-processor mailbox communication.
- **mutex** v2.1 — Inter-processor mutex. Multiple AXI slave ports (S0..S7).
- **pmcbridge** v1.0 — AXI4 bridge for Spartan US+ devices (not Artix-7).

---

## Foundational Elements

### Clock and Reset

- **clk_wiz** v6.0 — Clocking Wizard, MMCM/PLL-based clock generator. Key: `AUTO_PRIMITIVE=MMCM, CLKIN1_JITTER_PS=100.0, CLKOUT1_REQUESTED_OUT_FREQ=100.000, CLKOUT1_REQUESTED_DUTY_CYCLE=50.000, CLKOUT1_REQUESTED_PHASE=0.000, CLKOUT1_USED=true, CLKOUT[2-7]_USED=false, CLKOUT[n]_DRIVES=BUFG, CLK_OUT1_USE_FINE_PS_GUI=false, AXI_DRP=false, CLKIN2_JITTER_PS=100.0`. Up to 7 output clocks.
- **proc_sys_reset** v5.0 — Synchronized system reset with interconnect/peripheral/processor domains.
- **xpm_cdc_gen** v1.0 — XPM clock-domain-crossing primitives (generator wrapper).

### Basic

- **c_shift_ram** v12.0 — RAM-based shift register (up to 256 wide / 1024 deep).
- **c_counter_binary** v12.0 — See DSP.
- **fit_timer** v2.0 — Fixed-Interval Timer (periodic interrupt).
- **mailbox** v2.1 — See Embedded Processors.
- **mutex** v2.1 — See Embedded Processors.
- **util_ds_buf** v2.2 — BUFG/BUFR/differential I/O buffers wrapper.
- **util_ff** v1.0 — Instantiates FDRE/FDSE/FDCE/FDPE/LDCE/LDPE flip-flops.
- **util_idelay_ctrl** v1.0 — IDELAYCTRL primitive wrapper.
- **util_reduced_logic** v2.0 — Reduction logic (AND/OR/XOR) N-bit -> 1-bit.
- **util_vector_logic** v2.0 — Bitwise logic N-bit and N-bit -> N-bit.
- **xlconcat** v2.1 — Concat up to 128 ports into one vector.
- **xlconstant** v1.1 — Constant driver.
- **xlslice** v1.0 — Bus slicer (`dout = din[from:to]`).

### IO Interfaces

- **iomodule** v3.1 — LMB module with bundled I/O peripherals (UART, INTC, GPIO, timers) for MicroBlaze systems.
- **oddr** v1.0 — Output DDR flip-flop wrapper.
- **selectio_wiz** v5.1 — SelectIO wizard for SERDES / IODELAY blocks.

### Debug and Verification

- **bs_switch** v1.0 — BSCAN switch.
- **bscan_jtag** v1.0 — BSCAN-to-JTAG converter.
- **clk_vip** v1.0 — Clock VIP (sim testbench). Key: `FREQ_HZ=100000000, INTERFACE_MODE=PASS_THROUGH`.
- **debug_bridge** v3.0 — Debug bridge for DFX/XVC-based debug.
- **ila** v6.2 — Integrated Logic Analyzer. Probes, depth, trigger ports configured via many C_PROBE* params. Essential for on-chip debug.
- **ibert_7series_gtp** v3.0 — IBERT GT tester; GT not available on Basys3.
- **jtag_axi** v1.2 — JTAG-to-AXI master (drive AXI from Vivado tcl). Indispensable for bring-up.
- **rst_vip** v1.0 — Reset VIP (sim).
- **sim_clk_gen** v1.0 — Simulation-only clock generator (diff or single-ended).
- **system_ila** v1.1 — Interface-aware ILA (attaches to AXI/AXIS interfaces by name).
- **vio** v3.0 — Virtual I/O. Drives/monitors signals via Vivado hardware manager. Also critical for bring-up.
- **axi_perf_mon** v5.0 — Listed under AXI Infrastructure; also a debug utility.

### DFX (Dynamic Function eXchange)

- **dfx_axi_shutdown_manager** v1.0 — Gracefully terminates AXI transactions before RM removal.
- **dfx_bitstream_monitor** v1.0 — Debugs partial bitstream flow in a PR design.
- **dfx_controller** v1.0 — Loads / removes Reconfigurable Modules via ICAP.
- **dfx_decoupler** v1.0 — Maintains stable Static/RP boundary during partial reconfiguration.

### High-Speed Serial

- **gtwizard** v3.6 — 7-Series transceivers wizard. Not usable — no GTs on xc7a35tcpg236-1.
- **ibert_7series_gtp** v3.0 — See above.
- **picxo_fracxo** v2.0 — Digital VCXO (XAPP589/1241/1276); transceiver-based.

### Soft Error Mitigation

- **sem** v4.1 — Soft Error Mitigation controller (config-memory scrubber).

### Triple Modular Redundancy

- **tmr_comparator** v1.0 — Compares outputs from triplicated logic.
- **tmr_inject** v1.0 — Fault injection for TMR subsystems.
- **tmr_manager** v1.0 — Central TMR controller (with TMR Voter/Comparator/SEM).
- **tmr_sem** v1.0 — Bridge between TMR Manager and SEM.
- **tmr_voter** v1.0 — TMR majority voter.

---

## Interfaces and Interconnect (non-AXI)

### PCI / PCIe

- **ats_switch** (ERR) — Subcore only.
- **axi_pcie** v2.9 — AXI MM to PCIe bridge. Unusable on Basys3.
- **pci32** v5.0 — Parallel PCI 32-bit. Unusable on Basys3.
- **pci64** v5.0 — Parallel PCI 64-bit. Unusable on Basys3.
- **pcie_7x** v3.3 — 7-Series integrated PCIe block. xc7a35t has no PCIe hard block.
- **xdma** v4.2 — PCIe DMA / Bridge subsystem. Unusable.

### Ethernet (All need external PHY + usually GT/SGMII — Basys3 has no Ethernet PHY)

- **axi_10g_ethernet** v3.1 — 10G MAC + PCS/PMA. Unusable.
- **axi_ethernet** v8.0 — 1G/2.5G Ethernet subsystem.
- **axi_ethernetlite** v3.0 — 10/100 MAC.
- **gig_ethernet_pcs_pma** v17.0 — 1G PCS/PMA (GT or LVDS).
- **quadsgmii** v4.0 — Quad SGMII.
- **ten_gig_eth_mac** v15.1 — 10G MAC.
- **ten_gig_eth_pcs_pma** v6.0 — 10G PCS/PMA.
- **tri_mode_ethernet_mac** v9.0 — 10/100/1000 MAC.

### Serial Interfaces

- **aurora_8b10b** v11.1 — GT-based serial link.
- **axi_chip2chip** v5.0 — AXI over Aurora.

### Data Converters

- **xadc_wiz** v3.3 — XADC wizard. Configures the on-chip 12-bit ADC for temperature/voltage/alarm monitoring and user channels on VP/VN and VAUXP/N[0..15]. Key: `ACQUISITION_TIME=4, ADC_CONVERSION_RATE=1000, ADC_OFFSET_AND_GAIN_CALIBRATION=true, ADDR_WIDTH=32, AVERAGE_ENABLE_*`. Usable and practical on Basys3 for reading supply/temp plus the XADC header pins.

### Storage

- **fast_adapter** (ERR) — Not accessible on xc7a35tcpg236-1.

### Standard Bus Interfaces

- **ltpi** v3.0 — LVDS Tunnelling Protocol Interface (HPM/SCM modes). Niche.

---

## Multimedia and Vision

### General

- **v_axi4s_remap** v1.1 — Video AXI4-Stream remapper (pixel reorder).
- **v_axi4s_vid_out** v4.0 — AXI4-Stream to native video out (with sync gen).
- **v_tc** v6.2 — Video Timing Controller. Generates/detects hsync/vsync/active. Usable for VGA on Basys3.
- **v_tpg** v8.2 — Video Test Pattern Generator (bars, ramps, etc.). Useful.
- **v_vid_in_axi4s** v5.0 — Parallel video to AXI4-Stream.

### Audio

- **audio_clock_recovery_unit** v1.0 — Recovers audio clock for HDMI/DP/SDI/I2S.
- **audio_formatter** v1.0 — High-bandwidth DMA between memory and AXI4-Stream audio.
- **i2s_receiver** v1.0 — I2S RX, up to 8 channels, 16/24-bit samples.
- **i2s_transmitter** v1.0 — I2S TX, up to 8 channels, 16/24-bit samples.
- **spdif** v2.0 — SPDIF/AES3 TX or RX (32 kHz to 192 kHz).

### Video Processing (Most need DDR for frame buffers — not viable on Basys3 without external memory)

- **v_demosaic** v1.1 — Bayer demosaic.
- **v_frmbuf_rd** v3.0 — Frame buffer reader (needs DDR).
- **v_frmbuf_wr** v3.0 — Frame buffer writer (needs DDR).
- **v_gamma_lut** v1.1 — Gamma correction LUT.
- **v_mix** v6.0 — Up to 17-layer video mixer.
- **v_multi_scaler** v1.2 — Memory-based multi-scaler.
- **v_proc_ss** v2.3 — Video Processing Subsystem.
- **v_scenechange** v1.1 — Scene change detection.
- **v_warp_filter** v1.1 — Warp filter.
- **v_warp_init** v1.1 — Warp initializer.

### Video Connectivity (All require GT; NONE usable on Basys3)

- **mipi_csi2_rx_subsystem** v6.0 — MIPI CSI-2 Rx (D-PHY + CSI).
- **mipi_csi2_tx_subsystem** v2.2 — MIPI CSI-2 Tx.
- **mipi_dphy** v4.3 — MIPI D-PHY.
- **mipi_dsi_tx_subsystem** v3.0 — MIPI DSI Tx.
- **v_dp_rxss1** v3.1 — DisplayPort 1.4 RX.
- **v_dp_txss1** v3.1 — DisplayPort 1.4 TX.
- **v_hdmi_rx_ss** v3.2 — ERR (not accessible).
- **v_hdmi_tx_ss** v3.2 — ERR (not accessible).
- **v_smpte_sdi** v3.0 — ERR (not accessible).
- **vid_phy_controller** v2.2 — Video PHY wrapper over GT.

---

## Wireless

All of these are heavyweight signal-processing cores aimed at wireless base-station designs. Evaluate size carefully before using on Basys3; many won't fit.

- **cpri** v8.12 — CPRI v7.0 layer 1/2 (needs GT).
- **ldpc** v2.0 — LDPC codec.
- **lte_fft** v2.1 — LTE FFT.
- **pc_cfr** v8.0 — Peak Cancellation CFR.
- **polar** v1.1 — Polar codec.
- **srio_gen2** v4.1 — Serial RapidIO (needs GT).
- **tcc_decoder_3gppmm** v2.0 — Turbo decoder.
- **tcc_encoder_3gpp** v5.0 — Turbo encoder.
- **tcc_encoder_3gpplte** v4.0 — LTE turbo encoder.
- **viterbi** v9.1 — Viterbi.

---

## Kernels

- **rtl_kernel_wizard** v1.0 — RTL kernel wrapper for Vitis acceleration (Alveo/XRT). Not applicable to Basys3.

---

## Quick-Reference "I need X" Index

| Need | Use |
|---|---|
| UART | `axi_uartlite` (simple) or `axi_uart16550` (full 16550) |
| I2C | `axi_iic` |
| I3C | `axi_i3c` |
| SPI / Quad SPI | `axi_quad_spi` |
| GPIO | `axi_gpio` |
| Timer | `axi_timer` (32/64-bit), `fit_timer` (fixed-interval IRQ) |
| Watchdog | `axi_timebase_wdt` |
| Interrupt controller | `axi_intc` |
| BRAM (AXI-attached) | `axi_bram_ctrl` + `blk_mem_gen` |
| BRAM (native) | `blk_mem_gen` |
| Distributed (LUT) RAM/ROM | `dist_mem_gen` |
| FIFO | `fifo_generator` (most flexible), `axi_data_fifo` (AXI4), `axis_data_fifo` (AXI-Stream) |
| Clocking (MMCM/PLL) | `clk_wiz` |
| Processor-system reset | `proc_sys_reset` |
| CDC utilities | `xpm_cdc_gen`, `axi_clock_converter`, `axis_clock_converter` |
| DMA (MM<->MM) | `axi_cdma` |
| DMA (MM<->Stream) | `axi_dma`, `axi_datamover` |
| AXI interconnect | `smartconnect` (new designs), `axi_crossbar`, `axi_switch` |
| AXI-Stream switch | `axis_switch`, `axis_interconnect` |
| MM<->Stream bridge | `axi_fifo_mm_s`, `axi_mm2s_mapper` |
| Protocol bridges | `axi_protocol_converter` (AXI3/4/Lite), `axi_apb_bridge`, `axi_ahblite_bridge`, `ahblite_axi_bridge`, `axi_lmb_bridge`, `axi_amm_bridge`, `amm_axi_bridge` |
| Data width conversion | `axi_dwidth_converter`, `axis_dwidth_converter` |
| Floating-point math | `floating_point` |
| Fixed-point math: add/sub | `c_addsub` |
| Accumulator | `c_accum` |
| Counter | `c_counter_binary` |
| Multiplier | `mult_gen`, `xbip_multadd`, `cmpy` (complex), `dsp_macro` |
| Divider | `div_gen` |
| Trig / rotate / sqrt / atan2 | `cordic` |
| Sine/cosine / NCO / DDS | `dds_compiler` |
| FFT | `xfft` (general), `lte_fft` (LTE specific) |
| FIR / IIR / decimation / interpolation | `fir_compiler`, `cic_compiler` |
| Shift register (deep/wide) | `c_shift_ram` |
| Forward error correction | `rs_encoder`, `rs_decoder`, `viterbi`, `convolution`, `ldpc`, `polar`, `sid` (interleaver) |
| ECC on memory | `ecc`, `soft_ecc_proxy` |
| Soft CPU (full) | `microblaze`, `microblaze_riscv` (RISC-V) |
| Soft CPU (light) | `microblaze_mcs`, `microblaze_mcs_riscv` |
| CPU debug module | `mdm`, `mdm_riscv` |
| Inter-CPU comms | `mailbox`, `mutex` |
| ADC (on-chip XADC) | `xadc_wiz` |
| Pattern generator / video timing | `v_tpg`, `v_tc` |
| I2S audio | `i2s_receiver`, `i2s_transmitter` |
| SPDIF audio | `spdif` |
| CAN | `can`, `canfd` |
| ICAP / partial reconfig | `axi_hwicap`, `axi_hbicap`, `dfx_controller`, `dfx_decoupler`, `dfx_axi_shutdown_manager` |
| SEU / radiation mitigation | `sem`, TMR family (`tmr_manager`, `tmr_voter`, `tmr_comparator`, `tmr_inject`, `tmr_sem`) |
| Verification IP (sim) | `axi_vip`, `axi4stream_vip`, `clk_vip`, `rst_vip`, `sim_clk_gen` |
| On-chip debug | `ila`, `system_ila`, `vio`, `jtag_axi`, `debug_bridge` |
| AXI monitoring | `axi_perf_mon`, `axi_protocol_checker`, `axis_protocol_checker` |
| Traffic stress test | `axi_traffic_gen` |
| Constants / slicers / concat | `xlconstant`, `xlslice`, `xlconcat` |
| Basic logic utils | `util_vector_logic`, `util_reduced_logic`, `util_ff`, `util_ds_buf`, `util_idelay_ctrl`, `oddr` |
| SERDES / IO wizardry | `selectio_wiz` |
| LMB (MicroBlaze local bus) | `lmb_v10`, `lmb_bram_if_cntlr`, `axi_lmb_bridge`, `iomodule` |

### Do NOT use on Basys3 (transceivers / DDR / too big)

Ethernet: `axi_10g_ethernet`, `axi_ethernet`, `axi_ethernetlite`, `gig_ethernet_pcs_pma`, `quadsgmii`, `ten_gig_eth_*`, `tri_mode_ethernet_mac`.
PCI / PCIe: `axi_pcie`, `pci32`, `pci64`, `pcie_7x`, `xdma`.
Transceiver-based serial: `aurora_8b10b`, `axi_chip2chip`, `gtwizard`, `ibert_7series_gtp`, `picxo_fracxo`, `cpri`, `srio_gen2`.
Video connectivity: `mipi_*`, `v_dp_*`, `v_hdmi_*` (ERR), `v_smpte_sdi` (ERR), `vid_phy_controller`.
External memory: `mig_7series`, `axi_emc`.
DDR-backed video: `axi_vdma`, `v_frmbuf_rd`, `v_frmbuf_wr`, `v_multi_scaler`, `v_mix` (big), `v_proc_ss`, `v_warp_*`.
SDx/XRT/Alveo: `sdx_memory_subsystem`, `sdx_stream_subsystem`, `rtl_kernel_wizard`, `shell_utils_addr_remap`.
IPI-subcore-only (ERR): `ats_switch`, `ps11_vip`, `psx_vip`, `versal_cips_ps_vip`, `fast_adapter`, `pmcbridge`.
