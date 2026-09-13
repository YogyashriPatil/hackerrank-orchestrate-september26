"""
Model 5: Affordability Engine
==============================

Buy or Wait? - HackerRank Orchestrate

Purpose
-------
Evaluate whether a requested purchase is financially safe.

This model:

    Model 2 -> FinancialState
    Model 3 -> EvidenceResolver
    Model 4 -> CashFlowForecaster

It calculates:

    - immediate affordability
    - 90-day affordability
    - amount safe to pay today
    - earliest safe date for full payment
    - risk level
    - grounded reasons/warnings

IMPORTANT
---------
Model 5 does NOT choose the final payment method.

The final payment recommendation is handled by Model 6/7.

Required final affordability statuses are decided later by
the Decision Engine:

    affordable_now
    affordable_with_plan
    affordable_later
    not_affordable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Any

import pandas as pd

from .data_loader import DatasetLoader
from .financial_state import FinancialStateBuilder
from .evidence_resolver import EvidenceResolver
from .cashflow_forecast import CashFlowForecaster


# ============================================================
# RESULT OBJECT
# ============================================================

@dataclass
class AffordabilityAssessment:
    """
    Result produced by Model 5.
    """

    user_id: str
    request_id: str
    currency: str

    purchase_price: float

    current_balance: float
    minimum_required_balance: float

    balance_after_purchase: float

    projected_minimum_before_purchase: float
    projected_minimum_after_purchase: float

    immediate_affordable: bool
    future_affordable: bool
    reserve_safe: bool

    affordability_margin: float
    projected_safety_margin: float

    risk_level: str

    # Internal Model-5 status.
    #
    # IMPORTANT:
    # This is intentionally NOT the final output status.
    #
    # Values:
    #   AFFORDABLE
    #   AFFORDABLE_WITH_CAUTION
    #   AFFORDABLE_BUT_TIGHT
    #   IMMEDIATE_ONLY
    #   FUTURE_ONLY
    #   NOT_AFFORDABLE
    affordability_status: str

    # Required by the challenge.
    #
    # This is independent of payment preferences.
    earliest_safe_date: Optional[pd.Timestamp] = None

    # Maximum amount that can safely be paid today
    # without optional spending changes.
    amount_safe_to_pay: float = 0.0

    reasons: List[str] = field(
        default_factory=list
    )

    warnings: List[str] = field(
        default_factory=list
    )


# ============================================================
# AFFORDABILITY ENGINE
# ============================================================

class AffordabilityEngine:
    """
    Evaluate purchase affordability.

    Safety rule
    -----------

    A payment is safe only if:

        resulting_balance >= minimum_balance_to_keep

    for every relevant point in the 90-day forecast.

    The engine deliberately separates:

        1. immediate affordability
        2. future affordability
        3. earliest safe payment date

    This is important because:

        future_affordable == True

    does NOT necessarily mean the purchase is affordable today.
    """

    # --------------------------------------------------------
    # PUBLIC METHOD
    # --------------------------------------------------------

    def assess(
        self,
        state: Any,
        forecast: Any,
        purchase_price: float,
        currency: Optional[str] = None,
        request_id: str = "unknown",
    ) -> AffordabilityAssessment:

        # ====================================================
        # 1. VALIDATE PURCHASE PRICE
        # ====================================================

        try:
            purchase_price = float(
                purchase_price
            )
        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                "purchase_price must be numeric."
            ) from exc

        if purchase_price < 0:
            raise ValueError(
                "purchase_price cannot be negative."
            )

        # ====================================================
        # 2. READ FINANCIAL STATE
        # ====================================================

        current_balance = self._safe_float(
            getattr(
                state,
                "current_available_balance",
                0.0,
            )
        )

        minimum_balance = self._safe_float(
            getattr(
                state,
                "minimum_balance_to_keep",
                0.0,
            )
        )

        if minimum_balance < 0:
            minimum_balance = 0.0

        resolved_currency = (
            currency
            or getattr(
                state,
                "home_currency",
                None,
            )
            or "UNKNOWN"
        )

        user_id = str(
            getattr(
                state,
                "user_id",
                "unknown",
            )
        )

        # ====================================================
        # 3. CURRENT / IMMEDIATE AFFORDABILITY
        # ====================================================

        balance_after_purchase = (
            current_balance
            - purchase_price
        )

        affordability_margin = (
            balance_after_purchase
            - minimum_balance
        )

        immediate_affordable = (
            affordability_margin >= 0
        )

        # ====================================================
        # 4. FORECAST MINIMUM
        # ====================================================

        projected_minimum = self._get_projected_minimum(
            forecast
        )

        projected_minimum_after_purchase = (
            projected_minimum
            - purchase_price
        )

        projected_safety_margin = (
            projected_minimum_after_purchase
            - minimum_balance
        )

        future_affordable = (
            projected_safety_margin >= 0
        )

        # ====================================================
        # 5. EARLIEST SAFE DATE
        # ====================================================
        #
        # This is the important correction.
        #
        # We DO NOT simply use:
        #
        #     forecast.minimum_projected_balance
        #
        # to determine the date.
        #
        # Instead, inspect every daily forecast point and
        # find the FIRST date where:
        #
        #     closing_balance - purchase_price
        #         >= minimum_balance
        #
        # This is independent of payment preferences.
        # ====================================================

        earliest_safe_date = (
            self._find_earliest_safe_date(
                forecast=forecast,
                purchase_price=purchase_price,
                minimum_balance=minimum_balance,
            )
        )

        # If the purchase is already safe today, the earliest
        # date MUST be the request/forecast start date.
        #
        # We obtain the first forecast date if available.
        if immediate_affordable:

            first_forecast_date = (
                self._first_forecast_date(
                    forecast
                )
            )

            if first_forecast_date is not None:
                earliest_safe_date = (
                    first_forecast_date
                )

        # ====================================================
        # 6. RESERVE SAFETY
        # ====================================================

        reserve_safe = (
            immediate_affordable
            and future_affordable
        )

        # ====================================================
        # 7. AMOUNT SAFE TO PAY TODAY
        # ====================================================
        #
        # The specification requires:
        #
        #     0 <= amount_safe_to_pay <= requested_amount
        #
        # The maximum amount that can be paid today without
        # violating the minimum reserve is:
        #
        #     current_balance - minimum_balance
        #
        # But the challenge also requires the 90-day safety
        # check. Therefore we use the tighter capacity:
        #
        #     minimum of:
        #         current capacity
        #         forecast capacity
        #
        # This is then capped to [0, purchase_price].
        # ====================================================

        current_safe_capacity = (
            current_balance
            - minimum_balance
        )

        forecast_safe_capacity = (
            projected_minimum
            - minimum_balance
        )

        amount_safe_to_pay = max(
            0.0,
            min(
                purchase_price,
                current_safe_capacity,
                forecast_safe_capacity,
            ),
        )

        # Avoid tiny floating-point artifacts.
        amount_safe_to_pay = self._clean_amount(
            amount_safe_to_pay
        )

        # ====================================================
        # 8. RISK LEVEL
        # ====================================================

        risk_level = self._risk_level(
            affordability_margin=affordability_margin,
            projected_safety_margin=projected_safety_margin,
            minimum_balance=minimum_balance,
        )

        # ====================================================
        # 9. INTERNAL MODEL-5 STATUS
        # ====================================================

        status = self._status(
            immediate_affordable=immediate_affordable,
            future_affordable=future_affordable,
            risk_level=risk_level,
        )

        # ====================================================
        # 10. REASONS
        # ====================================================

        reasons = self._build_reasons(
            current_balance=current_balance,
            minimum_balance=minimum_balance,
            purchase_price=purchase_price,
            balance_after_purchase=balance_after_purchase,
            projected_minimum=projected_minimum,
            projected_minimum_after_purchase=(
                projected_minimum_after_purchase
            ),
            immediate_affordable=immediate_affordable,
            future_affordable=future_affordable,
            earliest_safe_date=earliest_safe_date,
            amount_safe_to_pay=amount_safe_to_pay,
        )

        # ====================================================
        # 11. WARNINGS
        # ====================================================

        warnings = self._build_warnings(
            immediate_affordable=immediate_affordable,
            future_affordable=future_affordable,
            projected_safety_margin=(
                projected_safety_margin
            ),
            earliest_safe_date=earliest_safe_date,
            purchase_price=purchase_price,
            amount_safe_to_pay=amount_safe_to_pay,
        )

        # ====================================================
        # 12. RETURN
        # ====================================================

        return AffordabilityAssessment(
            user_id=user_id,
            request_id=str(request_id),
            currency=str(resolved_currency),

            purchase_price=purchase_price,

            current_balance=current_balance,
            minimum_required_balance=minimum_balance,

            balance_after_purchase=(
                balance_after_purchase
            ),

            projected_minimum_before_purchase=(
                projected_minimum
            ),

            projected_minimum_after_purchase=(
                projected_minimum_after_purchase
            ),

            immediate_affordable=(
                immediate_affordable
            ),

            future_affordable=(
                future_affordable
            ),

            reserve_safe=reserve_safe,

            affordability_margin=(
                affordability_margin
            ),

            projected_safety_margin=(
                projected_safety_margin
            ),

            risk_level=risk_level,

            affordability_status=status,

            earliest_safe_date=(
                earliest_safe_date
            ),

            amount_safe_to_pay=(
                amount_safe_to_pay
            ),

            reasons=reasons,

            warnings=warnings,
        )

    # ========================================================
    # PROJECTED MINIMUM
    # ========================================================

    @staticmethod
    def _get_projected_minimum(
        forecast: Any,
    ) -> float:
        """
        Get the minimum projected balance.

        Prefer the forecaster's own calculated value.

        If unavailable, calculate it from daily_forecast.
        """

        value = getattr(
            forecast,
            "minimum_projected_balance",
            None,
        )

        if value is not None:
            try:
                return float(value)
            except (
                TypeError,
                ValueError,
            ):
                pass

        daily_forecast = getattr(
            forecast,
            "daily_forecast",
            None,
        )

        balances: List[float] = []

        if daily_forecast:

            for day in daily_forecast:

                closing = getattr(
                    day,
                    "closing_balance",
                    None,
                )

                if closing is None:
                    continue

                try:
                    balances.append(
                        float(closing)
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    continue

        if balances:
            return min(balances)

        # No forecast data.
        #
        # Return zero rather than inventing a positive
        # future balance.
        return 0.0

    # ========================================================
    # EARLIEST SAFE DATE
    # ========================================================

    @classmethod
    def _find_earliest_safe_date(
        cls,
        forecast: Any,
        purchase_price: float,
        minimum_balance: float,
    ) -> Optional[pd.Timestamp]:
        """
        Find the first forecast date on which a full
        purchase can safely be made.

        Safety condition:

            closing_balance - purchase_price
                >= minimum_balance

        IMPORTANT:
        Dates are normalized to pandas Timestamp so that
        datetime.date / datetime / pandas Timestamp values
        never get compared directly.
        """

        daily_forecast = getattr(
            forecast,
            "daily_forecast",
            None,
        )

        if not daily_forecast:
            return None

        # Sort safely by normalized Timestamp.
        #
        # This also prevents errors such as:
        #
        # TypeError:
        # Cannot compare Timestamp with datetime.date
        #
        normalized_days = []

        for day in daily_forecast:

            raw_date = getattr(
                day,
                "date",
                None,
            )

            if raw_date is None:
                continue

            try:
                day_date = (
                    pd.Timestamp(
                        raw_date
                    )
                    .normalize()
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            closing_balance = getattr(
                day,
                "closing_balance",
                None,
            )

            if closing_balance is None:
                continue

            try:
                closing_balance = float(
                    closing_balance
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

            normalized_days.append(
                (
                    day_date,
                    closing_balance,
                )
            )

        normalized_days.sort(
            key=lambda item: item[0]
        )

        for day_date, closing_balance in normalized_days:

            balance_after_purchase = (
                closing_balance
                - purchase_price
            )

            if (
                balance_after_purchase
                >= minimum_balance
            ):
                return day_date

        return None

    # ========================================================
    # FIRST FORECAST DATE
    # ========================================================

    @staticmethod
    def _first_forecast_date(
        forecast: Any,
    ) -> Optional[pd.Timestamp]:
        """
        Safely retrieve the first forecast date.
        """

        daily_forecast = getattr(
            forecast,
            "daily_forecast",
            None,
        )

        if not daily_forecast:
            return None

        dates = []

        for day in daily_forecast:

            raw_date = getattr(
                day,
                "date",
                None,
            )

            if raw_date is None:
                continue

            try:
                dates.append(
                    pd.Timestamp(
                        raw_date
                    ).normalize()
                )
            except (
                TypeError,
                ValueError,
            ):
                continue

        if not dates:
            return None

        return min(dates)

    # ========================================================
    # RISK
    # ========================================================

    @staticmethod
    def _risk_level(
        affordability_margin: float,
        projected_safety_margin: float,
        minimum_balance: float,
    ) -> str:
        """
        Determine a conservative risk level.

        LOW:
            Healthy reserve after purchase.

        MEDIUM:
            Purchase is safe but leaves a relatively small
            margin.

        HIGH:
            Very small margin or negative immediate/future
            margin.
        """

        if (
            affordability_margin < 0
            or projected_safety_margin < 0
        ):
            return "HIGH"

        # Relative to the user's reserve.
        #
        # Use absolute fallback for users whose reserve is zero.
        denominator = max(
            minimum_balance,
            1.0,
        )

        smallest_margin = min(
            affordability_margin,
            projected_safety_margin,
        )

        ratio = (
            smallest_margin
            / denominator
        )

        if ratio >= 0.50:
            return "LOW"

        if ratio >= 0.10:
            return "MEDIUM"

        return "HIGH"

    # ========================================================
    # INTERNAL STATUS
    # ========================================================

    @staticmethod
    def _status(
        immediate_affordable: bool,
        future_affordable: bool,
        risk_level: str,
    ) -> str:
        """
        Model-5 internal status.

        These values intentionally remain separate from the
        final four challenge statuses.
        """

        if (
            immediate_affordable
            and future_affordable
        ):

            if risk_level == "LOW":
                return "AFFORDABLE"

            if risk_level == "MEDIUM":
                return "AFFORDABLE_WITH_CAUTION"

            return "AFFORDABLE_BUT_TIGHT"

        if immediate_affordable:
            return "IMMEDIATE_ONLY"

        if future_affordable:
            return "FUTURE_ONLY"

        return "NOT_AFFORDABLE"

    # ========================================================
    # REASONS
    # ========================================================

    @staticmethod
    def _build_reasons(
        current_balance: float,
        minimum_balance: float,
        purchase_price: float,
        balance_after_purchase: float,
        projected_minimum: float,
        projected_minimum_after_purchase: float,
        immediate_affordable: bool,
        future_affordable: bool,
        earliest_safe_date: Optional[pd.Timestamp],
        amount_safe_to_pay: float,
    ) -> List[str]:

        reasons: List[str] = []

        if immediate_affordable:

            reasons.append(
                "The requested purchase fits within "
                "the current available balance while "
                "preserving the required minimum reserve."
            )

        else:

            reasons.append(
                "The full purchase cannot be made today "
                "without reducing the balance below the "
                "required minimum reserve."
            )

        if future_affordable:

            reasons.append(
                "The 90-day forecast remains above the "
                "required reserve after accounting for "
                "the purchase."
            )

        else:

            reasons.append(
                "The 90-day forecast does not support the "
                "full purchase while preserving the "
                "required reserve."
            )

        if earliest_safe_date is not None:

            reasons.append(
                "The earliest forecast date on which the "
                "full purchase is financially safe is "
                f"{earliest_safe_date.strftime('%Y-%m-%d')}."
            )

        else:

            reasons.append(
                "The full purchase is not projected to "
                "become safe within the forecast period."
            )

        if amount_safe_to_pay > 0:

            reasons.append(
                "The calculated amount that can safely be "
                f"paid today is {amount_safe_to_pay:,.2f}."
            )

        return reasons

    # ========================================================
    # WARNINGS
    # ========================================================

    @staticmethod
    def _build_warnings(
        immediate_affordable: bool,
        future_affordable: bool,
        projected_safety_margin: float,
        earliest_safe_date: Optional[pd.Timestamp],
        purchase_price: float,
        amount_safe_to_pay: float,
    ) -> List[str]:

        warnings: List[str] = []

        if not immediate_affordable:

            warnings.append(
                "Paying the full amount today would "
                "violate the minimum reserve."
            )

        if not future_affordable:

            warnings.append(
                "Paying the full amount is not safe "
                "across the 90-day forecast."
            )

        if (
            earliest_safe_date is None
            and not immediate_affordable
        ):

            warnings.append(
                "No safe full-payment date was found "
                "within the forecast horizon."
            )

        if (
            immediate_affordable
            and projected_safety_margin < 0
        ):

            warnings.append(
                "Although the purchase fits today, "
                "future projected cash flow would "
                "cause a reserve breach."
            )

        if (
            purchase_price > 0
            and amount_safe_to_pay == 0
            and not immediate_affordable
        ):

            warnings.append(
                "No positive amount can safely be paid "
                "today under the current 90-day safety check."
            )

        return warnings

    # ========================================================
    # NUMBER HELPERS
    # ========================================================

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> float:

        try:

            number = float(value)

            if pd.isna(number):
                return 0.0

            return number

        except (
            TypeError,
            ValueError,
        ):

            return 0.0

    @staticmethod
    def _clean_amount(
        value: float,
    ) -> float:

        value = float(value)

        if abs(value) < 1e-9:
            return 0.0

        return round(
            value,
            2,
        )


# ============================================================
# REPORT
# ============================================================

def print_affordability_report(
    assessment: AffordabilityAssessment,
) -> None:

    print()
    print("=" * 70)
    print(
        "MODEL 5: AFFORDABILITY ASSESSMENT"
    )
    print("=" * 70)

    print(
        f"\nUser: "
        f"{assessment.user_id}"
    )

    print(
        f"Request: "
        f"{assessment.request_id}"
    )

    print(
        f"Currency: "
        f"{assessment.currency}"
    )

    print(
        f"\nPurchase price:"
        f" {assessment.purchase_price:,.2f}"
    )

    print(
        f"Current balance:"
        f" {assessment.current_balance:,.2f}"
    )

    print(
        f"Required reserve:"
        f" {assessment.minimum_required_balance:,.2f}"
    )

    print(
        f"\nBalance after purchase:"
        f" {assessment.balance_after_purchase:,.2f}"
    )

    print(
        f"Immediate affordability:"
        f" {assessment.immediate_affordable}"
    )

    print(
        f"\n90-day minimum before purchase:"
        f" {assessment.projected_minimum_before_purchase:,.2f}"
    )

    print(
        f"90-day minimum after purchase:"
        f" {assessment.projected_minimum_after_purchase:,.2f}"
    )

    print(
        f"Future affordability:"
        f" {assessment.future_affordable}"
    )

    print(
        f"\nAmount safe to pay today:"
        f" {assessment.amount_safe_to_pay:,.2f}"
    )

    if assessment.earliest_safe_date is not None:

        print(
            f"Earliest safe full-payment date:"
            f" {assessment.earliest_safe_date.strftime('%Y-%m-%d')}"
        )

    else:

        print(
            "Earliest safe full-payment date: NONE"
        )

    print(
        f"\nImmediate affordability margin:"
        f" {assessment.affordability_margin:,.2f}"
    )

    print(
        f"Projected safety margin:"
        f" {assessment.projected_safety_margin:,.2f}"
    )

    print(
        f"\nRisk level:"
        f" {assessment.risk_level}"
    )

    print(
        f"Model-5 affordability status:"
        f" {assessment.affordability_status}"
    )

    print(
        "\nReasons:"
    )

    for reason in assessment.reasons:

        print(
            f"  - {reason}"
        )

    if assessment.warnings:

        print(
            "\nWarnings:"
        )

        for warning in assessment.warnings:

            print(
                f"  - {warning}"
            )

    print(
        "\n" + "=" * 70
    )

    print(
        "MODEL 5 AFFORDABILITY ENGINE: SUCCESS"
    )

    print(
        "=" * 70
    )


# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        "BUY OR WAIT? - "
        "MODEL 5: AFFORDABILITY ENGINE"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Model 1
    # --------------------------------------------------------

    loader = DatasetLoader(
        "dataset"
    )

    loader.load()

    # --------------------------------------------------------
    # Request
    # --------------------------------------------------------

    request = (
        loader.data
        .sort_values("request_id")
        .iloc[0]
    )

    request_id = str(
        request["request_id"]
    )

    user_id = str(
        request["user_id"]
    )

    request_date = pd.Timestamp(
        request["request_date"]
    ).normalize()

    requested_amount = float(
        request["requested_amount"]
    )

    # --------------------------------------------------------
    # Model 2
    # --------------------------------------------------------

    state_builder = (
        FinancialStateBuilder(
            loader
        )
    )

    state = state_builder.build(
        user_id
    )

    # --------------------------------------------------------
    # Model 3
    # --------------------------------------------------------

    evidence_resolver = (
        EvidenceResolver(
            loader
        )
    )

    resolved_events = (
        evidence_resolver.resolve_state(
            state
        )
    )

    # --------------------------------------------------------
    # Model 4
    # --------------------------------------------------------

    forecaster = (
        CashFlowForecaster(
            horizon_days=90
        )
    )

    forecast = forecaster.forecast(
        state,
        resolved_events,
        request_date,
    )

    # --------------------------------------------------------
    # Model 5
    # --------------------------------------------------------

    engine = (
        AffordabilityEngine()
    )

    assessment = engine.assess(
        state=state,
        forecast=forecast,
        purchase_price=requested_amount,
        currency=getattr(
            state,
            "home_currency",
            None,
        ),
        request_id=request_id,
    )

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    print_affordability_report(
        assessment
    )
