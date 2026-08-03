# Translation Target Function
def add_scale(x, y):
    return x + y * 2
# Translation Target End

if __name__ == "__main__":
    for i in range(5):
        add_scale(float(i) * 0.5, float(i) * 0.25)
