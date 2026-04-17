import numpy as np

N = 10


def jacobi_eigen(a, max_iter=1):
    n = a.shape[0]
    v = np.eye(n, dtype=complex)
    for _ in range(max_iter):
        off_diag_max = 0.0
        p, q = 0, 1
        for i in range(n):
            for j in range(i + 1, n):
                if abs(a[i, j]) > off_diag_max:
                    off_diag_max = abs(a[i, j])
                    p, q = i, j
        if off_diag_max < 1e-8:
            break
        app = a[p, p]
        aqq = a[q, q]
        apq = a[p, q]
        theta = 0.5 * np.arctan2(2.0 * np.abs(apq), (app.real - aqq.real))
        phi = -np.angle(apq)
        c = np.cos(theta)
        s = np.sin(theta)
        e = np.exp(1j * phi)
        u = np.eye(n, dtype=complex)
        u[p, p] = c
        u[q, q] = c
        u[p, q] = s * np.conj(e)
        u[q, p] = -s * e
        a = u.conj().T @ a @ u
        a[p, q] = 0
        a[q, p] = 0
        v = v @ u
    return a, v


def offdiag_max(a):
    m = 0.0
    for i in range(N):
        for j in range(i + 1, N):
            m = max(m, abs(a[i, j]))
    return m


def gen(seed):
    rng = np.random.default_rng(seed)
    bw = 14
    vec = rng.integers(-(1 << bw), 1 << bw, (N, 100)) + 1j * rng.integers(
        -(1 << bw), 1 << bw, (N, 100)
    )
    return (vec @ vec.conj().T) / (1 << 14)


def main():
    seeds = [0, 1, 2, 7, 42]
    for seed in seeds:
      a0 = gen(seed)
      a1, _ = jacobi_eigen(a0.copy(), max_iter=1)
      e0 = offdiag_max(a0)
      e1 = offdiag_max(a1)
      print(f"seed={seed} offdiag_before={e0:.4e} offdiag_after={e1:.4e}")
      if e1 > e0 + 1e-9:
          raise SystemExit(1)
    print("regression_pass")


if __name__ == "__main__":
    main()
