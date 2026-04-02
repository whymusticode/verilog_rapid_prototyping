import pathlib
import numpy as np

N = 10
BW = 14
W = 23
MAX_VAL = (1 << (W - 1)) - 1
MIN_VAL = -(1 << (W - 1))


def sat23(x):
    if x > MAX_VAL:
        return MAX_VAL
    if x < MIN_VAL:
        return MIN_VAL
    return x


def main():
    np.random.seed(0)
    vect = np.random.randint(-(2**BW), 2**BW, (N, 100)) + np.random.randint(
        -(2**BW), 2**BW, (N, 100)
    ) * 1j
    acm = vect @ vect.conj().T / 2**14

    out = pathlib.Path(__file__).resolve().parent / "tb_input_matrix.txt"
    with out.open("w") as f:
        for i in range(N):
            for j in range(N):
                re = sat23(int(round(float(np.real(acm[i, j])))))
                im = sat23(int(round(float(np.imag(acm[i, j])))))
                f.write(f"{re} {im}\n")
    print(f"generated {out}")


if __name__ == "__main__":
    main()
