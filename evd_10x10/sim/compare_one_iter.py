import pathlib
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
        theta = 0.5 * np.arctan((2.0 * np.abs(apq)) / (app.real - aqq.real))
        phi = -np.angle(apq)
        c = np.cos(theta)
        s = np.sin(theta)
        u = np.eye(n, dtype=complex)
        u[p, p] = c
        u[p, q] = s * np.exp(-1j * phi)
        u[q, p] = s * np.exp(1j * phi)
        u[q, q] = -c
        a = u.conj().T @ a @ u
        a[p, q] = 0
        a[q, p] = 0
        v = v @ u
    return np.diag(a), v


def read_input_matrix(path):
    vals = []
    for line in pathlib.Path(path).read_text().strip().splitlines():
        i, q = line.strip().split()
        vals.append(int(i) + 1j * int(q))
    arr = np.array(vals, dtype=complex).reshape((N, N))
    return arr


def expected_diag(input_path):
    a = read_input_matrix(input_path)
    diag, _ = jacobi_eigen(a, max_iter=1)
    return [(int(round(np.real(x))), int(round(np.imag(x)))) for x in diag]


def read_sim(path):
    out = []
    for line in pathlib.Path(path).read_text().strip().splitlines():
        i, q = line.strip().split()
        out.append((int(i), int(q)))
    return out


def main():
    sim_path = pathlib.Path(__file__).resolve().parent / "sim_diag_out.txt"
    in_path = pathlib.Path(__file__).resolve().parent / "tb_input_matrix.txt"
    got = read_sim(sim_path)
    exp = expected_diag(in_path)
    tol = 5
    worst = 0
    for (gi, gq), (ei, eq) in zip(got, exp):
        worst = max(worst, abs(gi - ei), abs(gq - eq))
    if worst > tol:
        print("compare_fail")
        print("expected:", exp)
        print("got:", got)
        print("worst_abs_err:", worst)
        raise SystemExit(1)
    print(f"compare_pass one_iteration_match worst_abs_err={worst}")


if __name__ == "__main__":
    main()
