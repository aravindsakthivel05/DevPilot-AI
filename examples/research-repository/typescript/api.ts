import {shippingCost} from './pricing';
export function quoteRequest(weight: number): number {
  return shippingCost(weight);
}
