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

This model does NOT make the final BUY / WAIT decision.
The final decision is handled by Model 7.
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
    """Result produced by Model 5."""

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

    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ============================================================
# AFFORDABILITY ENGINE
# ============================================================

class AffordabilityEngine:
    """
    Evaluate whether a purchase is financially safe.

    Two checks are performed:

    1. Immediate affordability

       current balance - purchase price
       must remain >= minimum reserve.

    2. Future affordability

       minimum projected balance over the forecast horizon
       - purchase price
       must remain >= minimum reserve.

    The final BUY / WAIT decision is NOT made here.
    """

    # ========================================================
    # PUBLIC API
    # ========================================================

    def assess(
        self,
        state: Any,
        forecast: Any,
        purchase_price: float,
        currency: Optional[str] = None,
        request_id: str = "unknown",
    ) -> AffordabilityAssessment:

        # ----------------------------------------------------
        # Validate purchase price
        # ----------------------------------------------------

        purchase_price = self._to_float(
            purchase_price,
            "purchase_price",
        )

        if purchase_price < 0:
            raise ValueError(
                "purchase_price cannot be negative."
            )

        # ----------------------------------------------------
        # Read financial state
        # ----------------------------------------------------

        current_balance = self._to_float(
            getattr(
                state,
                "current_available_balance",
                0.0,
            ),
            "current_available_balance",
        )

        minimum_balance = self._to_float(
            getattr(
                state,
                "minimum_balance_to_keep",
                0.0,
            ),
            "minimum_balance_to_keep",
        )

        # ----------------------------------------------------
        # Read forecast
        # ----------------------------------------------------

        projected_minimum = self._to_float(
            getattr(
                forecast,
                "minimum_projected_balance",
                current_balance,
            ),
            "minimum_projected_balance",
        )

        # ----------------------------------------------------
        # Currency
        # ----------------------------------------------------

        resolved_currency = (
            currency
            or getattr(
                state,
                "home_currency",
                None,
            )
            or "UNKNOWN"
        )

        resolved_currency = str(
            resolved_currency
        )

        # ----------------------------------------------------
        # Immediate affordability
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
        # Future affordability
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Reserve safety
        # ----------------------------------------------------

        reserve_safe = (
            immediate_affordable
            and future_affordable
        )

        # ----------------------------------------------------
        # Risk
        # ----------------------------------------------------

        risk_level = self._risk_level(
            affordability_margin=affordability_margin,
            projected_safety_margin=projected_safety_margin,
            purchase_price=purchase_price,
            minimum_balance=minimum_balance,
        )

        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------

        affordability_status = self._status(
            immediate_affordable=immediate_affordable,
            future_affordable=future_affordable,
            risk_level=risk_level,
        )

        # ----------------------------------------------------
        # Reasons
        # ----------------------------------------------------

        reasons: List[str] = []

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
                "under the cash-flow forecast."
            )
        else:
            reasons.append(
                "The purchase would cause the projected "
                "minimum balance to fall below the "
                "required reserve."
            )

        # ----------------------------------------------------
        # Warnings
        # ----------------------------------------------------

        warnings: List[str] = []

        baseline_breach = bool(
            getattr(
                forecast,
                "reserve_breached",
                False,
            )
        )

        if baseline_breach:
            warnings.append(
                "The baseline cash-flow forecast already "
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
                getattr(
                    state,
                    "user_id",
                    "unknown",
                )
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
                projected_minimum_after_purchase
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

            affordability_status=(
                affordability_status
            ),

            reasons=reasons,

            warnings=warnings,
        )

    # ========================================================
    # NUMERIC CONVERSION
    # ========================================================

    @staticmethod
    def _to_float(
        value: Any,
        field_name: str,
    ) -> float:

        try:
            result = float(value)
        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                f"{field_name} must be numeric. "
                f"Received: {value!r}"
            ) from exc

        if pd.isna(result):
            raise ValueError(
                f"{field_name} cannot be NaN."
            )

        return result

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

        # Any reserve breach = high risk.
        if (
            affordability_margin < 0
            or projected_safety_margin < 0
        ):
            return "HIGH"

        # Zero-price request.
        if purchase_price == 0:
            return "LOW"

        # If there is no reserve requirement,
        # a positive remaining balance is considered safe.
        if minimum_balance <= 0:
            return "LOW"

        margin_ratio = (
            projected_safety_margin
            / minimum_balance
        )

        # Very comfortable.
        if margin_ratio >= 1.0:
            return "LOW"

        # Some pressure but still safe.
        if margin_ratio >= 0.25:
            return "MEDIUM"

        # Close to required reserve.
        return "HIGH"

    # ========================================================
    # AFFORDABILITY STATUS
    # ========================================================

    @staticmethod
    def _status(
        immediate_affordable: bool,
        future_affordable: bool,
        risk_level: str,
    ) -> str:

        # Both immediate and future checks pass.
        if (
            immediate_affordable
            and future_affordable
        ):

            if risk_level == "LOW":
                return "AFFORDABLE"

            if risk_level == "MEDIUM":
                return "AFFORDABLE_WITH_CAUTION"

            return "AFFORDABLE_BUT_TIGHT"

        # Can afford now but not after forecast.
        if immediate_affordable:
            return "IMMEDIATE_ONLY"

        # Cannot afford now, but forecast says future
        # position can support it.
        if future_affordable:
            return "FUTURE_ONLY"

        # Neither check passes.
        return "NOT_AFFORDABLE"


# ============================================================
# FULL MODEL 5 PIPELINE
# ============================================================

def run_affordability_engine(
    dataset_path: str,
    request_id: str,
) -> AffordabilityAssessment:

    # --------------------------------------------------------
    # Model 1 - Dataset Loader
    # --------------------------------------------------------

    loader = DatasetLoader(
        dataset_path
    )

    loader.load()

    # --------------------------------------------------------
    # Get request
    # --------------------------------------------------------

    request = loader.request(
        request_id
    )

    if request is None:
        raise KeyError(
            f"Request not found: {request_id}"
        )

    # --------------------------------------------------------
    # Normalize request fields
    # --------------------------------------------------------

    user_id = str(
        request["user_id"]
    )

    request_date = pd.Timestamp(
        request["request_date"]
    ).normalize()

    # --------------------------------------------------------
    # Purchase amount
    # --------------------------------------------------------

    purchase_price = None

    price_columns = [
        "requested_amount",
        "purchase_price",
        "price",
        "amount",
        "item_price",
        "product_price",
    ]

    for column in price_columns:

        if column not in request.index:
            continue

        value = request[column]

        if pd.isna(value):
            continue

        try:
            purchase_price = float(value)
            break
        except (
            TypeError,
            ValueError,
        ):
            continue

    if purchase_price is None:
        raise ValueError(
            f"No valid purchase amount found "
            f"for request {request_id}."
        )

    # --------------------------------------------------------
    # Model 2 - Financial State
    # --------------------------------------------------------

    state_builder = FinancialStateBuilder(
        loader
    )

    state = state_builder.build(
        user_id=user_id,
        as_of_date=request_date,
    )

    # --------------------------------------------------------
    # Model 3 - Evidence Resolution
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
    # Model 4 - Cash Flow Forecast
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
    # Model 5 - Affordability
    # --------------------------------------------------------

    engine = AffordabilityEngine()

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

    return assessment


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
        f"\nUser: {assessment.user_id}"
    )

    print(
        f"Request: {assessment.request_id}"
    )

    print(
        f"Currency: {assessment.currency}"
    )

    print(
        f"\nPurchase price: "
        f"{assessment.purchase_price:,.2f}"
    )

    print(
        f"Current balance: "
        f"{assessment.current_balance:,.2f}"
    )

    print(
        f"Required reserve: "
        f"{assessment.minimum_required_balance:,.2f}"
    )

    print(
        f"\nBalance after purchase: "
        f"{assessment.balance_after_purchase:,.2f}"
    )

    print(
        f"Immediate affordability: "
        f"{assessment.immediate_affordable}"
    )

    print(
        f"\n90-day minimum before purchase: "
        f"{assessment.projected_minimum_before_purchase:,.2f}"
    )

    print(
        f"90-day minimum after purchase: "
        f"{assessment.projected_minimum_after_purchase:,.2f}"
    )

    print(
        f"Future affordability: "
        f"{assessment.future_affordable}"
    )

    print(
        f"\nImmediate affordability margin: "
        f"{assessment.affordability_margin:,.2f}"
    )

    print(
        f"Projected safety margin: "
        f"{assessment.projected_safety_margin:,.2f}"
    )

    print(
        f"\nRisk level: "
        f"{assessment.risk_level}"
    )

    print(
        f"Affordability status: "
        f"{assessment.affordability_status}"
    )

    print("\nReasons:")

    for reason in assessment.reasons:
        print(
            f"  - {reason}"
        )

    if assessment.warnings:

        print("\nWarnings:")

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

    DATASET_PATH = "dataset"

    # Use the first request as the diagnostic request.
    loader = DatasetLoader(
        DATASET_PATH
    )

    loader.load()

    request = (
        loader.data.requests.iloc[0]
    )

    request_id = str(
        request["request_id"]
    )

    print(
        f"\nTest request: {request_id}"
    )

    assessment = run_affordability_engine(
        dataset_path=DATASET_PATH,
        request_id=request_id,
    )

    print_affordability_report(
        assessment
    )

