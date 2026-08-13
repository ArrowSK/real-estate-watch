from app.services.mortgage import annuity_payment, calculate_mortgage


def test_annuity_zero_rate():
    assert annuity_payment(12_000_000, 0, 10) == 100_000


def test_mortgage_result_has_stress_scenarios():
    result = calculate_mortgage(
        purchase_price_huf=80_000_000,
        down_payment_huf=20_000_000,
        net_income_huf=1_500_000,
        existing_debt_huf=0,
        annual_rate_percent=6.5,
        term_years=20,
        fixation_years=10,
        first_home=False,
        green=False,
    )
    assert result.loan_huf == 60_000_000
    assert result.monthly_payment_huf > 400_000
    assert len(result.stress) == 4
    assert result.stress[-1].monthly_payment_huf > result.stress[0].monthly_payment_huf
    assert result.transfer_tax_huf == 3_200_000
