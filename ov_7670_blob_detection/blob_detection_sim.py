#!/usr/bin/env python3
import argparse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

W = 640
H = 480
FRAMES = 180
FG_THRESH = 24
MIN_AREA = 140

def make_background():
    y = np.arange(H, dtype=np.uint16)[:, None]
    x = np.arange(W, dtype=np.uint16)[None, :]
    road = 55 + (y * 50) // H
    lane_marks = ((x // 48) % 2) * 6
    vignette = ((np.abs(x - W // 2) + np.abs(y - H // 2)) // 24).astype(np.uint16)
    bg = road + lane_marks - np.minimum(vignette, 30)
    return np.clip(bg, 0, 255).astype(np.uint8)


def scene_objects():
    return [
        {"kind": "person", "x": 80, "y": 280, "w": 18, "h": 48, "vx": 1, "tone": 210},
        {"kind": "person", "x": 500, "y": 300, "w": 20, "h": 52, "vx": -1, "tone": 165},
        {"kind": "bike", "x": 0, "y": 330, "w": 44, "h": 24, "vx": 2, "tone": 120},
        {"kind": "car", "x": 610, "y": 350, "w": 84, "h": 34, "vx": -3, "tone": 85},
    ]


def render_frame(bg, objs, t):
    frame = bg.copy().astype(np.int16)
    # Smooth lighting drift (no hard wrap discontinuity).
    light = int(20.0 * np.sin((2.0 * np.pi * t) / 240.0))
    frame += light
    for o in objs:
        x = o["x"] + o["vx"] * t
        y = o["y"]
        if x < -o["w"] or x >= W:
            continue
        x0 = max(0, x)
        x1 = min(W, x + o["w"])
        y0 = max(0, y)
        y1 = min(H, y + o["h"])
        tone = o["tone"]
        frame[y0:y1, x0:x1] = tone
    noise = np.random.randint(-5, 6, (H, W), dtype=np.int16)
    frame += noise
    return np.clip(frame, 0, 255).astype(np.uint8)


def majority3(mask):
    m = mask.astype(np.uint8)
    p = np.pad(m, ((1, 1), (1, 1)), constant_values=0)
    s = (
        p[:-2, :-2]
        + p[:-2, 1:-1]
        + p[:-2, 2:]
        + p[1:-1, :-2]
        + p[1:-1, 1:-1]
        + p[1:-1, 2:]
        + p[2:, :-2]
        + p[2:, 1:-1]
        + p[2:, 2:]
    )
    return s >= 5


def runs_from_row(row):
    idx = np.flatnonzero(row)
    if idx.size == 0:
        return []
    gaps = np.flatnonzero(np.diff(idx) > 1)
    starts = np.r_[idx[0], idx[gaps + 1]]
    ends = np.r_[idx[gaps], idx[-1]]
    return list(zip(starts.tolist(), ends.tolist()))


def ccl_runs(mask):
    parent = {}
    next_label = 1
    prev_runs = []
    stats = {}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    for y in range(mask.shape[0]):
        cur_runs = []
        for x0, x1 in runs_from_row(mask[y]):
            overlaps = []
            for px0, px1, pl in prev_runs:
                if not (x1 < px0 or x0 > px1):
                    overlaps.append(pl)
            if overlaps:
                label = min(overlaps)
                for pl in overlaps:
                    union(label, pl)
            else:
                label = next_label
                parent[label] = label
                next_label += 1
            cur_runs.append((x0, x1, label))
            if label not in stats:
                stats[label] = [x0, y, x1, y, 0]
            st = stats[label]
            st[0] = min(st[0], x0)
            st[1] = min(st[1], y)
            st[2] = max(st[2], x1)
            st[3] = max(st[3], y)
            st[4] += x1 - x0 + 1
        prev_runs = cur_runs

    merged = {}
    for label, st in stats.items():
        root = find(label)
        if root not in merged:
            merged[root] = st.copy()
            continue
        m = merged[root]
        m[0] = min(m[0], st[0])
        m[1] = min(m[1], st[1])
        m[2] = max(m[2], st[2])
        m[3] = max(m[3], st[3])
        m[4] += st[4]
    return list(merged.values())


def classify(area, w, h):
    if area < MIN_AREA:
        return None
    ar = w / max(h, 1)
    if area < 1200 and 0.2 <= ar <= 0.9:
        return "person"
    if 600 <= area <= 2600 and 1.2 <= ar <= 3.8:
        return "bike"
    if area >= 1600 and 1.4 <= ar <= 4.8:
        return "car"
    return "unknown"


def detect(frame, bg, p, q, r, fg_leak):
    f32 = frame.astype(np.float32)
    resid = f32 - bg
    illum = float(np.mean(resid))
    diff = np.abs(resid - illum)
    fg = diff > FG_THRESH
    clean = majority3(fg)
    blobs = []
    for x0, y0, x1, y1, area in ccl_runs(clean):
        w = x1 - x0 + 1
        h = y1 - y0 + 1
        label = classify(area, w, h)
        if label is not None:
            blobs.append((label, x0, y0, x1, y1, area))
    # Scalar Kalman filter (per pixel, shared q/r):
    # p_pred = p + q
    # k      = p_pred / (p_pred + r)
    # bg     = bg + k * (z - bg)
    # p      = (1 - k) * p_pred
    p_pred = p + q
    k = p_pred / (p_pred + r)
    bg_upd = bg + k * (f32 - bg)
    p_upd = (1.0 - k) * p_pred
    # Foreground uses a very slow leak update so old object locations decay out.
    bg_fg = bg + fg_leak * (f32 - bg)
    bg_next = np.where(clean, bg_fg, bg_upd)
    p_next = np.where(clean, p_pred, p_upd)
    stats = {
        "k_mean": float(np.mean(k)),
        "k_min": float(np.min(k)),
        "k_max": float(np.max(k)),
        "fg_ratio": float(np.mean(clean)),
        "illum": illum,
        "diff_mean": float(np.mean(diff)),
        "diff_p95": float(np.percentile(diff, 95)),
        "bg_mean": float(np.mean(bg_next)),
        "frame_mean": float(np.mean(f32)),
    }
    return bg_next, p_next, blobs, clean, stats


def overlay_boxes(gray, blobs):
    rgb = np.repeat(gray[:, :, None], 3, axis=2)
    colors = {
        "person": np.array([255, 70, 70], dtype=np.uint8),
        "bike": np.array([80, 220, 80], dtype=np.uint8),
        "car": np.array([80, 140, 255], dtype=np.uint8),
        "unknown": np.array([255, 255, 80], dtype=np.uint8),
    }
    for label, x0, y0, x1, y1, _ in blobs:
        c = colors.get(label, colors["unknown"])
        rgb[y0 : y0 + 2, x0 : x1 + 1] = c
        rgb[y1 - 1 : y1 + 1, x0 : x1 + 1] = c
        rgb[y0 : y1 + 1, x0 : x0 + 2] = c
        rgb[y0 : y1 + 1, x1 - 1 : x1 + 1] = c
    return rgb


def setup_view():
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.5))
    im0 = ax[0].imshow(np.zeros((H, W, 3), dtype=np.uint8), vmin=0, vmax=255)
    ax[0].set_title("Frame + blobs")
    im1 = ax[1].imshow(np.zeros((H, W), dtype=np.uint8), cmap="gray", vmin=0, vmax=255)
    ax[1].set_title("Foreground mask")
    im2 = ax[2].imshow(np.zeros((H, W), dtype=np.uint8), cmap="gray", vmin=0, vmax=255)
    ax[2].set_title("Estimated background")
    for a in ax:
        a.axis("off")
    fig.tight_layout()
    return fig, im0, im1, im2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nogui", action="store_true", help="text mode only")
    ap.add_argument("--frames", type=int, default=FRAMES)
    ap.add_argument("--interval", type=int, default=35, help="ms between frames")
    ap.add_argument("--save", type=str, default="", help="optional output gif path")
    ap.add_argument(
        "--alpha",
        type=float,
        default=0.04,
        help="target steady-state Kalman gain (0<alpha<1)",
    )
    ap.add_argument(
        "--bg-init",
        type=str,
        default="clean",
        choices=["clean", "first", "zeros"],
        help="background initialization mode",
    )
    ap.add_argument(
        "--warmup",
        type=int,
        default=20,
        help="object-free warmup frames for background init",
    )
    ap.add_argument("--fg-leak", type=float, default=0.002, help="foreground bg leak rate")
    ap.add_argument("--debug-every", type=int, default=0, help="print debug stats every N frames")
    args = ap.parse_args()

    np.random.seed(7)
    base = make_background()
    objs = scene_objects()
    if args.bg_init == "zeros":
        bg = np.zeros((H, W), dtype=np.float32)
    elif args.bg_init == "first":
        bg = render_frame(base, objs, 0).astype(np.float32)
    else:
        bg = render_frame(base, [], 0).astype(np.float32)
    alpha = min(max(args.alpha, 1e-4), 0.999)
    r = 1.0
    q = r * (alpha * alpha) / (1.0 - alpha)
    p = np.full((H, W), 100.0 * r, dtype=np.float32)
    if args.bg_init == "clean" and args.warmup > 0:
        for t in range(args.warmup):
            frame0 = render_frame(base, [], t)
            bg, p, _, _, _ = detect(frame0, bg, p, q, r, args.fg_leak)
    print("frame, detections[label:x0,y0,x1,y1,area]")
    if args.nogui:
        for t in range(args.frames):
            frame = render_frame(base, objs, t)
            bg, p, blobs, _, st = detect(frame, bg, p, q, r, args.fg_leak)
            if args.debug_every > 0 and t % args.debug_every == 0:
                print(
                    f"DBG t={t:03d} k={st['k_mean']:.4f}({st['k_min']:.4f},{st['k_max']:.4f}) "
                    f"fg={st['fg_ratio']*100:.2f}% illum={st['illum']:.2f} diff={st['diff_mean']:.2f}/p95={st['diff_p95']:.2f} "
                    f"bg={st['bg_mean']:.2f} frame={st['frame_mean']:.2f}"
                )
            if blobs:
                msg = " | ".join(
                    f"{b[0]}:{b[1]},{b[2]},{b[3]},{b[4]},{b[5]}" for b in blobs[:8]
                )
                print(f"{t:03d}, k={st['k_mean']:.4f}, {msg}")
        return

    fig, im0, im1, im2 = setup_view()
    state = {"bg": bg, "p": p}

    def tick(t):
        frame = render_frame(base, objs, t)
        bg_next, p_next, blobs, clean, st = detect(
            frame, state["bg"], state["p"], q, r, args.fg_leak
        )
        state["bg"] = bg_next
        state["p"] = p_next
        if args.debug_every > 0 and t % args.debug_every == 0:
            print(
                f"DBG t={t:03d} k={st['k_mean']:.4f}({st['k_min']:.4f},{st['k_max']:.4f}) "
                f"fg={st['fg_ratio']*100:.2f}% illum={st['illum']:.2f} diff={st['diff_mean']:.2f}/p95={st['diff_p95']:.2f} "
                f"bg={st['bg_mean']:.2f} frame={st['frame_mean']:.2f}"
            )
        if blobs:
            msg = " | ".join(
                f"{b[0]}:{b[1]},{b[2]},{b[3]},{b[4]},{b[5]}" for b in blobs[:8]
            )
            print(f"{t:03d}, k={st['k_mean']:.4f}, {msg}")
        im0.set_data(overlay_boxes(frame, blobs))
        im1.set_data((clean.astype(np.uint8)) * 255)
        im2.set_data(np.clip(bg_next, 0, 255).astype(np.uint8))
        fig.suptitle(f"t={t:03d} blobs={len(blobs)} k={st['k_mean']:.4f} alpha={alpha:.4f}")
        return im0, im1, im2

    ani = FuncAnimation(
        fig,
        tick,
        frames=args.frames,
        interval=args.interval,
        blit=False,
        repeat=False,
    )
    if args.save:
        ani.save(args.save, writer="pillow", fps=max(1, 1000 // args.interval))
        print(f"saved animation: {args.save}")
    else:
        plt.show()


if __name__ == "__main__":
    main()
