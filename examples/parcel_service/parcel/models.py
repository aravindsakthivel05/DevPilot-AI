from dataclasses import dataclass


@dataclass
class Parcel:
    weight_kg: float
    destination: str

    def validate(self):
        if self.weight_kg <= 0:
            raise ValueError("Weight must be positive")
        if self.destination not in ("domestic", "international"):
            raise ValueError("Unsupported destination")
