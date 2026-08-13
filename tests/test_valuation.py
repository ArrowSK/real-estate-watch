from app.services.valuation import value_property


def test_valuation_applies_visible_factors():
    result = value_property(
        floor_area_m2=80,
        baseline_huf_m2=1_200_000,
        factors=["ground_floor", "needs_renovation", "balcony"],
    )
    assert round(result.adjustment, 2) == -0.13
    assert result.estimated_value_huf == 80 * 1_200_000 * 0.87


def test_duplicate_factor_is_not_counted_twice():
    result = value_property(
        floor_area_m2=50,
        baseline_huf_m2=1_000_000,
        factors=["balcony", "balcony"],
    )
    assert result.adjustment == 0.05
