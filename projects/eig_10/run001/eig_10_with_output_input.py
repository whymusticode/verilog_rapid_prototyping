import numpy as np
import subprocess
import os

Q = 16  # fractional bits (S32Q16)

def to_hex32(x):
    v = int(round(x * (1 << Q)))
    v = max(-(1 << 31), min((1 << 31) - 1, v))
    return format(v & 0xFFFFFFFF, '08X')

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
        theta = 0.5 * np.arctan((2 * np.abs(a_pq)) / (a_pp.real - a_qq.real))
        phi = -np.angle(a_pq)
        U = np.eye(n, dtype=complex)
        U[p, p] = np.cos(theta)
        U[p, q] = np.sin(theta) * np.exp(-1j * phi)
        U[q, p] = np.sin(theta) * np.exp(1j * phi)
        U[q, q] = -np.cos(theta)
        A = U.conj().T @ A @ U
        A[p, q], A[q, p] = 0, 0
        V = V @ U
    return np.diag(A), V

def write_line(f, arr):
    f.write(' '.join(to_hex32(x) for x in arr.ravel()) + '\n')

np.random.seed(0)
N = 10
BW = 14
vect = np.random.randint(-2**BW, 2**BW, (N, 100)) + np.random.randint(-2**BW, 2**BW, (N, 100)) * 1J
acm = vect @ vect.conj().T/2**14
# np.max(np.abs(np.real(acm))) / 2**23
# 0.1429764071435784  so about 3 extra bits, good enough scaling for now 
acm_i = np.real(acm)
acm_q = np.imag(acm)
max_iter = 1

# Save inputs (one test case)
with open('eig_10__acm_i.txt', 'w') as f:
    write_line(f, acm_i)
with open('eig_10__acm_q.txt', 'w') as f:
    write_line(f, acm_q)
with open('eig_10__max_iter.txt', 'w') as f:
    f.write(format(max_iter & 0xFFFF, '04X') + '\n')

# Python reference
eigenvalues, eigenvectors = jacobi_eigen(acm.copy(), max_iter=max_iter)
ev_i, ev_q = np.real(eigenvalues), np.imag(eigenvalues)
vec_i, vec_q = np.real(eigenvectors), np.imag(eigenvectors)

with open('py_eigenvalues_i.txt', 'w') as f:
    write_line(f, ev_i.reshape(10, 1))
with open('py_eigenvalues_q.txt', 'w') as f:
    write_line(f, ev_q.reshape(10, 1))
with open('py_eigenvectors_i.txt', 'w') as f:
    write_line(f, vec_i)
with open('py_eigenvectors_q.txt', 'w') as f:
    write_line(f, vec_q)

# Run VHDL (expect eig_10_fxp.vhd + global_types_pkg.vhd + run_tb.vhd in this dir)
if os.path.isfile('eig_10_fxp.vhd') and os.path.isfile('global_types_pkg.vhd') and os.path.isfile('run_tb.vhd'):
    d = os.path.dirname(os.path.abspath(__file__)) or '.'
    subprocess.run(['ghdl', '-a', '--std=08', 'global_types_pkg.vhd', 'eig_10_fxp.vhd', 'run_tb.vhd'], check=True)
    subprocess.run(['ghdl', '-e', '--std=08', 'run_tb'], check=True)
    subprocess.run(['ghdl', '-r', '--std=08', 'run_tb', '--ieee-asserts=disable'], check=True)
    # Compare
    with open('vhdl_eigenvalues_i.txt') as f:
        vhdl_ev_i = f.read()
    with open('py_eigenvalues_i.txt') as f:
        py_ev_i = f.read()
    print('Match eigenvalues_i:', vhdl_ev_i.strip() == py_ev_i.strip())
else:
    print('Input/output saved. Copy eig_10_fxp.vhd and global_types_pkg.vhd here, then re-run to compare with VHDL.')
