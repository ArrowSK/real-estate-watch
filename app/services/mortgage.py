from dataclasses import dataclass

from app.countries.hu.regulations import DebtBrakeResult, evaluate_debt_brake, transfer_tax_huf


@dataclass(frozen=True)
class MortgageScenario:
    rate_percent: float
    monthly_payment_huf: float


@dataclass(frozen=True)
class MortgageResult:
    loan_huf: float
    monthly_payment_huf: float
    total_repayment_huf: float
    total_interest_huf: float
    transfer_tax_huf: float
    estimated_cash_required_huf: float
    debt_brake: DebtBrakeResult
    stress: tuple[MortgageScenario, ...]


def annuity_payment(principal: float, annual_rate_percent: float, years: int) -> float:
    if principal <= 0:
        return 0.0
    months = years * 12
    if months <= 0:
        raise ValueError("Term must be positive")
    monthly_rate = annual_rate_percent / 100 / 12
    if monthly_rate == 0:
        return principal / months
    factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1)


def calculate_mortgage(
    *,
    purchase_price_huf: float,
    down_payment_huf: float,
    net_income_huf: float,
    existing_debt_huf: float,
    annual_rate_percent: float,
    term_years: int,
    fixation_years: int,
    first_home: bool,
    green: bool,
) -> MortgageResult:
    if purchase_price_huf <= 0:
        raise ValueError("Purchase price must be positive")
    if not 0 <= down_payment_huf <= purchase_price_huf:
        raise ValueError("Down payment must be between zero and the purchase price")
    if annual_rate_percent < 0 or annual_rate_percent > 30:
        raise ValueError("Interest rate must be between 0% and 30%")
    if term_years < 1 or term_years > 40:
        raise ValueError("Term must be between 1 and 40 years")

    loan = purchase_price_huf - down_payment_huf
    payment = annuity_payment(loan, annual_rate_percent, term_years)
    total_repayment = payment * term_years * 12
    tax = transfer_tax_huf(purchase_price_huf)
    debt_brake = evaluate_debt_brake(
        property_value_huf=purchase_price_huf,
        loan_huf=loan,
        net_income_huf=net_income_huf,
        new_monthly_payment_huf=payment,
        existing_monthly_debt_huf=existing_debt_huf,
        fixation_years=fixation_years,
        first_home=first_home,
        green=green,
    )
    stress = tuple(
        MortgageScenario(rate_percent=annual_rate_percent + bump, monthly_payment_huf=annuity_payment(loan, annual_rate_percent + bump, term_years))
        for bump in (0, 1, 2, 3)
    )
    # Known universal cash components only. Legal, valuation, bank and insurance fees differ
    # by transaction/product and are deliberately not invented here.
    estimated_cash = down_payment_huf + tax
    return MortgageResult(
        loan_huf=loan,
        monthly_payment_huf=payment,
        total_repayment_huf=total_repayment,
        total_interest_huf=max(total_repayment - loan, 0.0),
        transfer_tax_huf=tax,
        estimated_cash_required_huf=estimated_cash,
        debt_brake=debt_brake,
        stress=stress,
    )
