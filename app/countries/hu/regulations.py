from dataclasses import dataclass


MNB_RULES_SOURCE = (
    "https://www.mnb.hu/penzugyi-stabilitas/makroprudencialis-politika/"
    "makroprudencialis-eszkoztar/adossagfek-szabalyok-hfm-jtm"
)
NAV_TRANSFER_TAX_SOURCE = (
    "https://nav.gov.hu/ugyfeliranytu/adokulcsok_jarulekmertekek/"
    "illetekmertekek/visszterhes-vagyonatruhazasi-illetek"
)


@dataclass(frozen=True)
class DebtBrakeResult:
    ltv_limit: float
    jtm_limit: float
    ltv: float
    jtm: float
    passes_ltv: bool
    passes_jtm: bool

    @property
    def passes(self) -> bool:
        return self.passes_ltv and self.passes_jtm


def ltv_limit(first_home: bool, green: bool) -> float:
    # HUF mortgages: 90% for qualifying first-home buyers and qualifying green
    # collateral/loan purposes; otherwise 80% under the current MNB framework.
    return 0.90 if first_home or green else 0.80


def jtm_limit(net_income_huf: float, fixation_years: int, green: bool) -> float:
    # Current threshold from 1 Jan 2026: HUF 800,000 verified monthly net income.
    if fixation_years >= 10:
        if green:
            return 0.60
        return 0.60 if net_income_huf >= 800_000 else 0.50
    if fixation_years >= 5:
        return 0.40 if net_income_huf >= 800_000 else 0.35
    return 0.30 if net_income_huf >= 800_000 else 0.25


def evaluate_debt_brake(
    *,
    property_value_huf: float,
    loan_huf: float,
    net_income_huf: float,
    new_monthly_payment_huf: float,
    existing_monthly_debt_huf: float,
    fixation_years: int,
    first_home: bool,
    green: bool,
) -> DebtBrakeResult:
    ltv = loan_huf / property_value_huf if property_value_huf > 0 else 1.0
    jtm = (
        (new_monthly_payment_huf + existing_monthly_debt_huf) / net_income_huf
        if net_income_huf > 0
        else 1.0
    )
    ltv_max = ltv_limit(first_home, green)
    jtm_max = jtm_limit(net_income_huf, fixation_years, green)
    return DebtBrakeResult(
        ltv_limit=ltv_max,
        jtm_limit=jtm_max,
        ltv=ltv,
        jtm=jtm,
        passes_ltv=ltv <= ltv_max + 1e-9,
        passes_jtm=jtm <= jtm_max + 1e-9,
    )


def transfer_tax_huf(property_value_huf: float) -> float:
    # General NAV rule: 4% up to HUF 1bn, 2% above that, capped at HUF 200m/property.
    first_band = min(max(property_value_huf, 0.0), 1_000_000_000) * 0.04
    second_band = max(property_value_huf - 1_000_000_000, 0.0) * 0.02
    return min(first_band + second_band, 200_000_000.0)
