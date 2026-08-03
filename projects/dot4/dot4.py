# Translation Target Function
def dot4(a, b):
    total = 0.0
    for i in range(len(a)):
        total += a[i] * b[i]
    return total
# Translation Target End

if __name__ == "__main__":
    import random
    random.seed(0)
    for _ in range(5):
        a = [round(random.uniform(-2, 2), 3) for _ in range(4)]
        b = [round(random.uniform(-2, 2), 3) for _ in range(4)]
        dot4(a, b)
