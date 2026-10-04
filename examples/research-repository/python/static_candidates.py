"""Intentional static diagnostic fixture; never execute this file."""

def combine(left, right):
    return left + right

combine(1, 2, 3)


def unreachable_example():
    return 1
    print("unreachable")
