"""Small research fixture. Positive weight is part of the public contract."""

def shipping_cost(weight):
    """Return five currency units per unit weight; reject nonpositive weights."""
    if weight <= 0:
        raise ValueError("weight must be positive")
    return weight * 5
