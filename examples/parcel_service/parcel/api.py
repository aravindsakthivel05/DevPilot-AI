from .models import Parcel
from .pricing import calculate_quote


def shipping_quote(weight_kg, destination):
    """Public entry point for obtaining a shipping quote."""
    parcel = Parcel(weight_kg, destination)
    return {"currency": "USD", "amount": calculate_quote(parcel)}
