import numpy as np

# Translation Target Function
def jacobi_eigen(A, max_iter=2000):
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
    
    return z, np.diag(A), V

# Translation Target End

def show(A, tol=1e-10):
    B = A.copy()
    B.real[abs(B.real) < tol] = 0
    B.imag[abs(B.imag) < tol] = 0
    np.set_printoptions(precision=2, suppress=True)
    print(B)
    print()

np.random.seed(0)
N = 10
BW = 14
vect = np.random.randint(-2**BW, 2**BW, (N, 100)) + \
       np.random.randint(-2**BW, 2**BW, (N, 100)) * 1J

acm = vect @ vect.conj().T
ite, eigenvalues, eigenvectors = jacobi_eigen(acm.copy())
eig_val, eig_vec = np.linalg.eig(acm)

print(eigenvalues.real)
print(eig_val.real)
# print()
# show(eigenvectors)
# print()
# show(eig_vec)
