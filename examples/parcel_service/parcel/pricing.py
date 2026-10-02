from .models import Parcel


def base_rate(parcel: Parcel):
    """International parcels have a higher per-kilogram rate."""
    return 12.0 if parcel.destination == "international" else 5.0


def calculate_quote(parcel: Parcel):
    """Validate the parcel and calculate the shipping price, minimum 10."""
    parcel.validate()
    return round(max(10.0, parcel.weight_kg * base_rate(parcel)), 2)
