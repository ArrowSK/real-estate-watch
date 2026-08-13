from app.countries.hu.regulations import evaluate_debt_brake, jtm_limit, ltv_limit, transfer_tax_huf


def test_ltv_limits():
    assert ltv_limit(first_home=False, green=False) == 0.80
    assert ltv_limit(first_home=True, green=False) == 0.90
    assert ltv_limit(first_home=False, green=True) == 0.90


def test_jtm_2026_threshold_long_fixation():
    assert jtm_limit(799_999, 10, False) == 0.50
    assert jtm_limit(800_000, 10, False) == 0.60
    assert jtm_limit(500_000, 10, True) == 0.60


def test_transfer_tax_general_rule():
    assert transfer_tax_huf(100_000_000) == 4_000_000
    assert transfer_tax_huf(1_100_000_000) == 42_000_000
    assert transfer_tax_huf(20_000_000_000) == 200_000_000


def test_debt_brake_combines_existing_debt():
    result = evaluate_debt_brake(
        property_value_huf=100_000_000,
        loan_huf=80_000_000,
        net_income_huf=1_000_000,
        new_monthly_payment_huf=500_000,
        existing_monthly_debt_huf=50_000,
        fixation_years=10,
        first_home=False,
        green=False,
    )
    assert result.passes_ltv
    assert result.passes_jtm
    assert round(result.jtm, 2) == 0.55
