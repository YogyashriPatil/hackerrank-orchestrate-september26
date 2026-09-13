"""
Model 5: Affordability Engine
==============================

Purpose
-------
Determine whether a requested purchase is financially affordable.

Model 5 consumes:

    Model 2 -> Financial State
    Model 3 -> Evidence Resolution
    Model 4 -> 90-Day Cash-Flow Forecast

It produces an affordability assessment.

Important:
------------
This model does NOT make the final BUY / WAIT decision.

It answers:

    "Can this purchase fit safely inside the user's
     financial position?"

The final decision is handled later by Model 7.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import pandas as pd

from .data_loader import DatasetLoader
from .financial_state import FinancialStateBuilder
from .evidence_resolver import (
    EvidenceResolver,
)
from .cashflow_forecast import (
    CashFlowForecaster,
)


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

    affordability_status: str

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

    The engine uses two safety checks:

    1. Immediate affordability
       -----------------------
       Current balance - purchase price
       must remain above the minimum reserve.

    2. Future affordability
       --------------------
       The projected 90-day minimum balance after
       subtracting the purchase price must remain
       above the minimum reserve.

    The second check is more important for the
    final financial decision.
    """

    def assess(
        self,
        state,
        forecast,
        purchase_price: float,
        currency: Optional[str] = None,
        request_id: str = "unknown",
    ) -> AffordabilityAssessment:

        # ----------------------------------------------------
        # Validate price
        # ----------------------------------------------------

        try:

            purchase_price = float(
                purchase_price
            )

        except (
            TypeError,
            ValueError,
        ):

            raise ValueError(
                "purchase_price must be numeric."
            )

        if purchase_price < 0:

            raise ValueError(
                "purchase_price cannot be negative."
            )

        # ----------------------------------------------------
        # Basic financial values
        # ----------------------------------------------------

        current_balance = float(
            state.current_available_balance
        )

        minimum_balance = float(
            state.minimum_balance_to_keep
        )

        projected_minimum = float(
            forecast.minimum_projected_balance
        )

        resolved_currency = (
            currency
            or getattr(
                state,
                "home_currency",
                None,
            )
            or "UNKNOWN"
        )

        # ----------------------------------------------------
        # Immediate calculation
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Future calculation
        # ----------------------------------------------------

        projected_after_purchase = (
            projected_minimum
            - purchase_price
        )

        projected_safety_margin = (
            projected_after_purchase
            - minimum_balance
        )

        future_affordable = (
            projected_safety_margin >= 0
        )

        # ----------------------------------------------------
        # Overall reserve safety
        # ----------------------------------------------------

        reserve_safe = (
            immediate_affordable
            and future_affordable
        )

        # ----------------------------------------------------
        # Determine risk
        # ----------------------------------------------------

        risk_level = self._risk_level(
            affordability_margin=(
                affordability_margin
            ),
            projected_safety_margin=(
                projected_safety_margin
            ),
            purchase_price=purchase_price,
            minimum_balance=minimum_balance,
        )

        # ----------------------------------------------------
        # Determine status
        # ----------------------------------------------------

        status = self._status(
            immediate_affordable=(
                immediate_affordable
            ),
            future_affordable=(
                future_affordable
            ),
            risk_level=risk_level,
        )

        # ----------------------------------------------------
        # Reasons
        # ----------------------------------------------------

        reasons = []

        if immediate_affordable:

            reasons.append(
                "The purchase can be paid immediately "
                "while preserving the minimum balance."
            )

        else:

            reasons.append(
                "Paying the full purchase price now "
                "would breach the minimum balance reserve."
            )

        if future_affordable:

            reasons.append(
                "The purchase remains affordable "
                "under the 90-day cash-flow projection."
            )

        else:

            reasons.append(
                "The purchase would cause the projected "
                "90-day minimum balance to fall below "
                "the required reserve."
            )

        # ----------------------------------------------------
        # Warnings
        # ----------------------------------------------------

        warnings = []

        if getattr(
            forecast,
            "reserve_breached",
            False,
        ):

            warnings.append(
                "The baseline 90-day forecast already "
                "contains a reserve breach before "
                "considering this purchase."
            )

        if purchase_price == 0:

            warnings.append(
                "Purchase price is zero."
            )

        # ----------------------------------------------------
        # Return
        # ----------------------------------------------------

        return AffordabilityAssessment(
            user_id=str(
                state.user_id
            ),

            request_id=str(
                request_id
            ),

            currency=resolved_currency,

            purchase_price=purchase_price,

            current_balance=current_balance,

            minimum_required_balance=(
                minimum_balance
            ),

            balance_after_purchase=(
                balance_after_purchase
            ),

            projected_minimum_before_purchase=(
                projected_minimum
            ),

            projected_minimum_after_purchase=(
                projected_after_purchase
            ),

            immediate_affordable=(
                immediate_affordable
            ),

            future_affordable=(
                future_affordable
            ),

            reserve_safe=(
                reserve_safe
            ),

            affordability_margin=(
                affordability_margin
            ),

            projected_safety_margin=(
                projected_safety_margin
            ),

            risk_level=risk_level,

            affordability_status=status,

            reasons=reasons,

            warnings=warnings,
        )

    # ========================================================
    # RISK LEVEL
    # ========================================================

    @staticmethod
    def _risk_level(
        affordability_margin: float,
        projected_safety_margin: float,
        purchase_price: float,
        minimum_balance: float,
    ) -> str:

        # ----------------------------------------------------
        # Hard failure
        # ----------------------------------------------------

        if (
            affordability_margin < 0
            or projected_safety_margin < 0
        ):

            return "HIGH"

        # ----------------------------------------------------
        # Free purchase
        # ----------------------------------------------------

        if purchase_price == 0:

            return "LOW"

        # ----------------------------------------------------
        # Relative safety margin
        # ----------------------------------------------------

        if minimum_balance > 0:

            margin_ratio = (
                projected_safety_margin
                / minimum_balance
            )

        else:

            margin_ratio = 1.0

        # ----------------------------------------------------
        # Very comfortable
        # ----------------------------------------------------

        if margin_ratio >= 1.0:

            return "LOW"

        # ----------------------------------------------------
        # Some pressure
        # ----------------------------------------------------

        if margin_ratio >= 0.25:

            return "MEDIUM"

        # ----------------------------------------------------
        # Close to reserve
        # ----------------------------------------------------

        return "HIGH"

    # ========================================================
    # STATUS
    # ========================================================

    @staticmethod
    def _status(
        immediate_affordable: bool,
        future_affordable: bool,
        risk_level: str,
    ) -> str:

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
        f"Affordability status:"
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
        loader.data.requests.iloc[0]
    )

    request_id = str(
        request["request_id"]
    )

    user_id = str(
        request["user_id"]
    )

    request_date = pd.to_datetime(
        request["request_date"]
    )

    print(
        f"\nTest request: {request_id}"
    )

    print(
        f"Test user:    {user_id}"
    )

    print(
        f"Request date: {request_date.date()}"
    )

    # --------------------------------------------------------
    # Get purchase price
    # --------------------------------------------------------
    #
    # Different datasets can name this column differently.
    # We therefore search common names.
    #

    purchase_price = None

    possible_price_columns = [
        "purchase_price",
        "price",
        "amount",
        "item_price",
        "product_price",
        "requested_amount",
    ]

    for column in possible_price_columns:

        if column in request.index:

            value = request[column]

            if pd.notna(value):

                try:

                    purchase_price = float(
                        value
                    )

                    break

                except (
                    ValueError,
                    TypeError,
                ):

                    pass

    # --------------------------------------------------------
    # If request does not directly contain price
    # --------------------------------------------------------

    if purchase_price is None:

        print(
            "\nWARNING:"
        )

        print(
            "No purchase price column was found "
            "in the evaluation request."
        )

        print(
            "Using 0.0 only for the diagnostic run."
        )

        purchase_price = 0.0

    # --------------------------------------------------------
    # Model 2
    # --------------------------------------------------------

    state_builder = (
        FinancialStateBuilder(
            loader
        )
    )

    state = state_builder.build(
        user_id=user_id,
        as_of_date=request_date,
    )

    # --------------------------------------------------------
    # Model 3
    # --------------------------------------------------------

    resolver = EvidenceResolver(
        loader
    )

    resolved_events = (
        resolver.resolve_state(
            state
        )
    )

    # --------------------------------------------------------
    # Model 4
    # --------------------------------------------------------

    forecaster = CashFlowForecaster(
        horizon_days=90
    )

    forecast = forecaster.forecast(
        state=state,
        resolved_events=resolved_events,
        as_of_date=request_date,
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
        purchase_price=purchase_price,
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