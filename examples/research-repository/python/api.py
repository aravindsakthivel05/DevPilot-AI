from .pricing import shipping_cost


def quote_request(weight):
    """Delegate quote calculation to the pricing function."""
    return shipping_cost(weight)
