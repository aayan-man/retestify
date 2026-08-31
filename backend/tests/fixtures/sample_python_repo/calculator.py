def add(a, b):
    """Add two numbers."""
    return a + b


def divide(a, b):
    """Divide a by b, raising ValueError on a zero denominator."""
    if b == 0:
        raise ValueError("cannot divide by zero")
    return a / b


class Calculator:
    def __init__(self, start=0):
        self.value = start

    def add(self, n):
        self.value += n
        return self.value
