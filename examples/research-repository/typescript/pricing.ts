export function shippingCost(weight: number): number {
  if (weight <= 0) { throw new Error("weight must be positive"); }
  return weight * 5;
}
