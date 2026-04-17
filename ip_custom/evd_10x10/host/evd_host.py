import argparse
import numpy as np
import serial

from fixed23 import pack_complex23, unpack_complex23, quant23

N = 10
RX_BYTES = 604
TX_BYTES = 65


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


def generate_matrix(seed):
    rng = np.random.default_rng(seed)
    bw = 14
    vec = rng.integers(-(1 << bw), 1 << bw, (N, 100)) + 1j * rng.integers(
        -(1 << bw), 1 << bw, (N, 100)
    )
    return (vec @ vec.conj().T) / (1 << 14)


def encode_matrix(a):
    payload = bytearray()
    for i in range(N):
        for j in range(N):
            payload += pack_complex23(quant23(np.real(a[i, j])), quant23(np.imag(a[i, j])))
    return payload


def decode_diag(pkt):
    vals = []
    for i in range(N):
        base = 4 + i * 6
        ii, qq = unpack_complex23(pkt[base : base + 6])
        vals.append(ii + 1j * qq)
    return np.array(vals, dtype=complex)


def make_frame(a, max_iter):
    frame = bytearray()
    frame.append(0xA5)
    frame.append(max_iter & 0xFF)
    frame.append((max_iter >> 8) & 0xFF)
    frame += encode_matrix(a)
    crc = 0
    for b in frame:
      crc ^= b
    frame.append(crc & 0xFF)
    return frame


def run_once(port, baud, seed, max_iter):
    a = generate_matrix(seed)
    frame = make_frame(a, max_iter)
    assert len(frame) == RX_BYTES

    s = serial.Serial(port=port, baudrate=baud, timeout=2.0)
    s.reset_input_buffer()
    s.reset_output_buffer()
    s.write(frame)
    resp = s.read(TX_BYTES)
    s.close()

    if len(resp) != TX_BYTES:
        print(f"short response: {len(resp)} bytes")
        return 1
    if resp[0] != 0x5A:
        print(f"bad sof: 0x{resp[0]:02X}")
        return 1
    if resp[1] != 0:
        print(f"fpga status error: 0x{resp[1]:02X}")
        return 1

    fpga_diag = decode_diag(resp)
    hw_iter = resp[2] | (resp[3] << 8)
    py_diag, _ = jacobi_eigen(a.copy(), max_iter=hw_iter)
    order_py = np.argsort(np.real(py_diag))
    order_fpga = np.argsort(np.real(fpga_diag))
    err = np.max(np.abs(py_diag[order_py] - fpga_diag[order_fpga]))

    print(f"iter_count={hw_iter}")
    print(f"max_diag_error={err:.4e}")
    print("python_diag=", py_diag)
    print("fpga_diag=", fpga_diag)
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max_iter", type=int, default=512)
    args = p.parse_args()
    raise SystemExit(run_once(args.port, args.baud, args.seed, args.max_iter))


if __name__ == "__main__":
    main()
