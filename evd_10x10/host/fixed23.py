W = 23
MAX_VAL = (1 << (W - 1)) - 1
MIN_VAL = -(1 << (W - 1))
MASK24 = (1 << 24) - 1


def sat23(x: int) -> int:
    if x > MAX_VAL:
        return MAX_VAL
    if x < MIN_VAL:
        return MIN_VAL
    return x


def round_even(x: float) -> int:
    return int(round(x))


def quant23(x: float) -> int:
    return sat23(round_even(x))


def to_u24_signed(x: int) -> int:
    return x & MASK24


def from_u24_signed(x: int) -> int:
    x &= MASK24
    if x & (1 << 23):
        return x - (1 << 24)
    return x


def pack_lane23(x: int) -> bytes:
    u = to_u24_signed(sat23(x))
    return bytes((u & 0xFF, (u >> 8) & 0xFF, (u >> 16) & 0xFF))


def unpack_lane23(b: bytes) -> int:
    u = b[0] | (b[1] << 8) | (b[2] << 16)
    return from_u24_signed(u)


def pack_complex23(i_val: int, q_val: int) -> bytes:
    return pack_lane23(i_val) + pack_lane23(q_val)


def unpack_complex23(b: bytes) -> tuple[int, int]:
    return unpack_lane23(b[0:3]), unpack_lane23(b[3:6])
