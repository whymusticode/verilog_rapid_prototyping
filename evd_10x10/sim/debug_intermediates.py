import pathlib
import numpy as np

N = 10
Q = 20


def idiv_tz(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    if (a < 0) ^ (b < 0):
        return -q
    return q


def isqrt64(x: int) -> int:
    op = x
    res = 0
    one = 1 << 62
    for _ in range(32):
        if one > op:
            one >>= 2
    for _ in range(32):
        if one != 0:
            if op >= res + one:
                op -= res + one
                res = (res >> 1) + one
            else:
                res >>= 1
            one >>= 2
    return res & 0xFFFFFFFF


def qmul(a: int, b: int) -> int:
    t = a * b
    if t >= 0:
        return (t + (1 << (Q - 1))) >> Q
    return -(((-t) + (1 << (Q - 1))) >> Q)


def clamp_unit_q(x: int) -> int:
    lim = 1 << Q
    if x > lim:
        return lim
    if x < -lim:
        return -lim
    return x


def read_input_matrix(path: pathlib.Path):
    vals = []
    for line in path.read_text().strip().splitlines():
        i, q = line.strip().split()
        vals.append((int(i), int(q)))
    re = np.array([v[0] for v in vals], dtype=np.int64).reshape((N, N))
    im = np.array([v[1] for v in vals], dtype=np.int64).reshape((N, N))
    return re, im


def read_kv(path: pathlib.Path):
    out = {}
    for line in path.read_text().strip().splitlines():
        k, v = line.split()
        out[k] = int(v)
    return out


def compute_py_like_intermediates(re: np.ndarray, im: np.ndarray):
    max_mag_sq = -1
    p = 0
    q = 1
    for i in range(N):
        for j in range(i + 1, N):
            m = int(re[i, j] * re[i, j] + im[i, j] * im[i, j])
            if m > max_mag_sq:
                max_mag_sq = m
                p, q = i, j
    apq_mag = isqrt64(max_mag_sq)
    app_i = int(re[p, p])
    aqq_i = int(re[q, q])
    apq_re_i = int(re[p, q])
    apq_im_i = int(im[p, q])
    cp_q = clamp_unit_q(idiv_tz(apq_re_i << Q, apq_mag)) if apq_mag else 0
    sp_q = clamp_unit_q(-idiv_tz(apq_im_i << Q, apq_mag)) if apq_mag else 0
    delta_i = app_i - aqq_i
    if delta_i == 0:
        t_q = 1 << Q
        r_q = 0
    else:
        r_q = idiv_tz(apq_mag << (Q + 1), delta_i)
        sqrt_term_q = isqrt64(r_q * r_q + (1 << (2 * Q)))
        den_t = (1 << Q) + int(sqrt_term_q)
        t_q = idiv_tz(r_q << Q, den_t) if den_t != 0 else 0
    c_q = clamp_unit_q((1 << (2 * Q)) // isqrt64(t_q * t_q + (1 << (2 * Q))))
    s_q = clamp_unit_q(qmul(t_q, c_q))
    c2_q = qmul(c_q, c_q)
    s2_q = qmul(s_q, s_q)
    cs2_q = qmul(c_q, s_q) << 1
    bmag = apq_mag
    diag_p = qmul(c2_q, app_i) + qmul(s2_q, aqq_i) + qmul(cs2_q, bmag)
    diag_q = qmul(s2_q, app_i) + qmul(c2_q, aqq_i) - qmul(cs2_q, bmag)
    return {
        "p": p,
        "q": q,
        "apq_mag": apq_mag,
        "app_i": app_i,
        "aqq_i": aqq_i,
        "apq_re_i": apq_re_i,
        "apq_im_i": apq_im_i,
        "cp_q": cp_q,
        "sp_q": sp_q,
        "r_q": r_q,
        "t_q": t_q,
        "c_q": c_q,
        "s_q": s_q,
        "diag_p": diag_p,
        "diag_q": diag_q,
    }


def main():
    base = pathlib.Path(__file__).resolve().parent
    re, im = read_input_matrix(base / "tb_input_matrix.txt")
    py_vals = compute_py_like_intermediates(re, im)
    rtl_vals = read_kv(base / "sim_intermediates.txt")
    keys = [
        "p",
        "q",
        "apq_mag",
        "app_i",
        "aqq_i",
        "apq_re_i",
        "apq_im_i",
        "cp_q",
        "sp_q",
        "r_q",
        "t_q",
        "c_q",
        "s_q",
        "diag_p",
        "diag_q",
    ]
    for k in keys:
        pv = py_vals[k]
        rv = rtl_vals.get(k)
        if pv != rv:
            print(f"first_diff {k} py={pv} rtl={rv}")
            return
    print("intermediates_match")


if __name__ == "__main__":
    main()
