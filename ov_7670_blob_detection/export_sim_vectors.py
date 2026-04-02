#!/usr/bin/env python3
import numpy as np
from blob_detection_sim import make_background, scene_objects, render_frame

OUT_W = 160
OUT_H = 120
DS = 4
FRAMES = 30

FG_THRESH = 18
ALPHA_Q8 = 10
FG_LEAK_Q8 = 1
GAIN_BETA_SHIFT = 4


def run():
    np.random.seed(7)
    base = make_background()
    objs = scene_objects()

    bg = np.zeros((OUT_H, OUT_W), dtype=np.int16)
    gain_q8 = int(ALPHA_Q8)
    illum_bias = 0

    pix_lines = []
    dbg_lines = []

    for t in range(FRAMES):
        frame = render_frame(base, objs, t)
        ds = frame[::DS, ::DS].astype(np.int16)

        resid_acc = 0
        fg_count = 0
        for y in range(OUT_H):
            for x in range(OUT_W):
                pix = int(ds[y, x])
                bg_old = int(bg[y, x])
                resid_illum = pix - bg_old - illum_bias
                if abs(resid_illum) > FG_THRESH:
                    fg_now = 1
                    k_use = FG_LEAK_Q8
                else:
                    fg_now = 0
                    k_use = gain_q8
                delta_bg = pix - bg_old
                step = (delta_bg * k_use) >> 8
                bg_new = bg_old + step
                if bg_new < 0:
                    bg_new = 0
                if bg_new > 255:
                    bg_new = 255
                bg[y, x] = bg_new
                resid_acc += (pix - bg_old)
                fg_count += fg_now
                pix_lines.append(f"{pix & 0xFF:02x}")

        illum_bias = resid_acc >> 14
        gain_err = int(ALPHA_Q8) - gain_q8
        gain_q8 = gain_q8 + (gain_err >> GAIN_BETA_SHIFT)
        dbg_lines.append(
            f"SIMDBG_PY frame={t:03d} gain_q8={gain_q8:03d} illum={illum_bias:04d} fg={fg_count:05d} bg0={int(bg[0,0]):03d}"
        )

    with open("ov_7670_blob_detection/sim_ds_pixels.mem", "w", encoding="ascii") as f:
        f.write("\n".join(pix_lines) + "\n")
    with open("ov_7670_blob_detection/sim_py_debug.txt", "w", encoding="ascii") as f:
        f.write("\n".join(dbg_lines) + "\n")

    print("WROTE ov_7670_blob_detection/sim_ds_pixels.mem")
    print("WROTE ov_7670_blob_detection/sim_py_debug.txt")
    for line in dbg_lines[:6]:
        print(line)


if __name__ == "__main__":
    run()
