import numpy as np

# Translation Target Function
def jacobi_eigen(A, max_iter):
    n = A.shape[0]
    V = np.eye(n, dtype=complex)

    for z in range(max_iter):
        off_diag_max = 0
        p, q = 0, 1
        for i in range(n):
            for j in range(i + 1, n):
                if abs(A[i, j]) > off_diag_max:
                    off_diag_max = abs(A[i, j])
                    p, q = i, j

        if off_diag_max < 1e-8:
            break

        a_pp, a_qq, a_pq = A[p, p], A[q, q], A[p, q]
        theta = 0.5 * np.arctan((2 * np.abs(a_pq)) / (a_pp - a_qq))
        phi = -np.angle(a_pq)

        U = np.eye(n, dtype=complex)
        U[p, p] = np.cos(theta)
        U[p, q] = np.sin(theta) * np.exp(-1j * phi)
        U[q, p] = np.sin(theta) * np.exp(1j * phi)
        U[q, q] = -np.cos(theta)

        A = U.conj().T @ A @ U
        A[p, q], A[q, p] = 0, 0
        V = V @ U

    return np.diag(A), V, z
# Translation Target End

if __name__ == "__main__":
    np.random.seed(0)
    N_size = 10
    max_iter = 1  # exactly one Jacobi sweep -- fixed trip count, no convergence loop
    BW = 14
    for i in range(10):
        vect = np.random.randint(-2**BW, 2**BW, (N_size, 100)) + np.random.randint(-2**BW, 2**BW, (N_size, 100)) * 1J
        acm = vect @ vect.conj().T / 2**14
        eigenvalues, eigenvectors, ite = jacobi_eigen(acm.copy(), max_iter)
