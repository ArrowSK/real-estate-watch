from dataclasses import dataclass


DEFAULT_ADJUSTMENTS = {
    "ground_floor": -0.06,
    "top_floor": -0.03,
    "no_lift": -0.04,
    "needs_renovation": -0.12,
    "renovated": 0.08,
    "courtyard": -0.04,
    "balcony": 0.05,
}


@dataclass(frozen=True)
class ValuationResult:
    baseline_huf_m2: float
    adjusted_huf_m2: float
    adjustment: float
    estimated_value_huf: float
    low_huf: float
    high_huf: float


def value_property(*, floor_area_m2: float, baseline_huf_m2: float, factors: list[str]) -> ValuationResult:
    if floor_area_m2 <= 0 or floor_area_m2 > 5000:
        raise ValueError("Floor area is outside the supported range")
    if baseline_huf_m2 <= 0:
        raise ValueError("Baseline must be positive")
    adjustment = sum(DEFAULT_ADJUSTMENTS.get(f, 0.0) for f in set(factors))
    adjustment = max(-0.40, min(0.40, adjustment))
    adjusted = baseline_huf_m2 * (1 + adjustment)
    estimate = adjusted * floor_area_m2
    # The range is intentionally broad until coefficients can be calibrated from microdata.
    return ValuationResult(
        baseline_huf_m2=baseline_huf_m2,
        adjusted_huf_m2=adjusted,
        adjustment=adjustment,
        estimated_value_huf=estimate,
        low_huf=estimate * 0.93,
        high_huf=estimate * 1.07,
    )
