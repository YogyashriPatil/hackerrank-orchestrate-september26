"""
Model 7: Final Decision Engine
===============================

Combines Models 2-6 and produces the final financial decision.

Possible decisions:

    affordable_now
    affordable_with_plan
    affordable_later
    not_affordable

This model does NOT modify the user's financial data.
It only evaluates the request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Any

import pandas as pd

from .data_loader import DatasetLoader
from .financial_state import FinancialStateBuilder
from .evidence_resolver import EvidenceResolver
from .cashflow_forecast import CashFlowForecaster
from .affordability_engine import AffordabilityEngine
from .payment_optimizer import PaymentPlanOptimizer


# ============================================================
# RESULT
# ============================================================

@dataclass
class DecisionResult:

    request_id: str

    user_id: str

    currency: str

    decision: str

    safe_amount: float

    requested_amount: float

    payment_method: Optional[str]

    payment_option_id: Optional[str]

    payment_plan: Optional[str]

    earliest_safe_date: Optional[pd.Timestamp]

    spending_changes: List[str] = field(
        default_factory=list
    )

    reasons: List[str] = field(
        default_factory=list
    )

    warnings: List[str] = field(
        default_factory=list
    )

    confidence: float = 0.0


# ============================================================
# DECISION ENGINE
# ============================================================

class DecisionEngine:
    """
    Final deterministic decision engine.
    """

    def decide(
        self,
        request: Any,
        state: Any,
        forecast: Any,
        affordability: Any,
        payment_result: Any,
    ) -> DecisionResult:

        request_id = str(
            self._get(
                request,
                "request_id",
                "unknown",
            )
        )

        user_id = str(
            self._get(
                request,
                "user_id",
                getattr(
                    state,
                    "user_id",
                    "unknown",
                ),
            )
        )

        requested_amount = float(
            self._get(
                request,
                "requested_amount",
                0,
            )
        )

        currency = str(
            getattr(
                state,
                "home_currency",
                "UNKNOWN",
            )
        )

        # ----------------------------------------------------
        # Check whether purchase is affordable immediately.
        # ----------------------------------------------------

        immediate_safe = (
            bool(
                affordability.immediate_affordable
            )
            and
            bool(
                affordability.future_affordable
            )
        )

        # ----------------------------------------------------
        # Existing baseline reserve breach.
        # ----------------------------------------------------

        baseline_breach = bool(
            getattr(
                forecast,
                "reserve_breached",
                False,
            )
        )

        # ----------------------------------------------------
        # Safe payment plan.
        # ----------------------------------------------------

        best_plan = getattr(
            payment_result,
            "best_plan",
            None,
        )

        plan_available = (
            best_plan is not None
        )

        # ----------------------------------------------------
        # Decision
        # ----------------------------------------------------

        if (
            immediate_safe
            and not baseline_breach
        ):

            decision = (
                "affordable_now"
            )

            safe_amount = (
                requested_amount
            )

            earliest_safe_date = (
                pd.Timestamp(
                    self._get(
                        request,
                        "request_date",
                    )
                ).normalize()
            )

            spending_changes = []

            payment_method = None
            payment_option_id = None
            payment_plan = None

            if plan_available:

                payment_method = (
                    best_plan.payment_method
                )

                payment_option_id = (
                    best_plan.payment_option_id
                )

                payment_plan = (
                    self._format_plan(
                        best_plan
                    )
                )

            reasons = [
                "The requested purchase fits "
                "within the current available balance.",
                "The purchase preserves the required "
                "minimum financial reserve.",
                "The 90-day forecast remains above "
                "the user's safety floor.",
            ]

        elif (
            plan_available
            and not baseline_breach
        ):

            decision = (
                "affordable_with_plan"
            )

            safe_amount = (
                requested_amount
            )

            earliest_safe_date = (
                best_plan.starts_on
            )

            payment_method = (
                best_plan.payment_method
            )

            payment_option_id = (
                best_plan.payment_option_id
            )

            payment_plan = (
                self._format_plan(
                    best_plan
                )
            )

            spending_changes = []

            reasons = [
                "The purchase is not safely "
                "handled as an unrestricted immediate "
                "payment.",
                "A user-accepted payment option "
                "keeps the projected balance above "
                "the required reserve.",
            ]

        else:

            # ------------------------------------------------
            # Search for a later safe date.
            # ------------------------------------------------

            later_date = (
                self._find_earliest_safe_date(
                    request=request,
                    state=state,
                    forecast=forecast,
                    requested_amount=(
                        requested_amount
                    ),
                )
            )

            if later_date is not None:

                decision = (
                    "affordable_later"
                )

                safe_amount = (
                    requested_amount
                )

                earliest_safe_date = (
                    later_date
                )

                payment_method = None
                payment_option_id = None
                payment_plan = None

                spending_changes = []

                reasons = [
                    "The purchase is not safely "
                    "affordable under the current "
                    "cash position.",
                    "Waiting until the identified "
                    "future date provides a safer "
                    "cash position.",
                ]

            else:

                decision = (
                    "not_affordable"
                )

                safe_amount = (
                    self._calculate_safe_amount(
                        state=state,
                        forecast=forecast,
                    )
                )

                earliest_safe_date = None

                payment_method = None
                payment_option_id = None
                payment_plan = None

                spending_changes = (
                    self._suggest_spending_changes(
                        state
                    )
                )

                reasons = [
                    "The requested amount cannot "
                    "be safely supported by the "
                    "current financial position.",
                    "Available payment plans do not "
                    "provide a safe solution.",
                ]

        # ----------------------------------------------------
        # Warnings
        # ----------------------------------------------------

        warnings = []

        if baseline_breach:

            warnings.append(
                "The baseline 90-day forecast "
                "already breaches the required "
                "minimum reserve."
            )

        if getattr(
            affordability,
            "warnings",
            None,
        ):

            warnings.extend(
                affordability.warnings
            )

        if getattr(
            payment_result,
            "warnings",
            None,
        ):

            warnings.extend(
                payment_result.warnings
            )

        # Remove duplicates while preserving order.

        warnings = list(
            dict.fromkeys(
                warnings
            )
        )

        # ----------------------------------------------------
        # Confidence
        # ----------------------------------------------------

        confidence = (
            self._calculate_confidence(
                affordability=affordability,
                payment_result=payment_result,
                forecast=forecast,
            )
        )

        return DecisionResult(
            request_id=request_id,
            user_id=user_id,
            currency=currency,
            decision=decision,
            safe_amount=safe_amount,
            requested_amount=requested_amount,
            payment_method=payment_method,
            payment_option_id=payment_option_id,
            payment_plan=payment_plan,
            earliest_safe_date=(
                earliest_safe_date
            ),
            spending_changes=(
                spending_changes
            ),
            reasons=reasons,
            warnings=warnings,
            confidence=confidence,
        )

    # ========================================================
    # EARLIEST SAFE DATE
    # ========================================================

    def _find_earliest_safe_date(
        self,
        request: Any,
        state: Any,
        forecast: Any,
        requested_amount: float,
    ) -> Optional[pd.Timestamp]:

        """
        Find the first forecast date where paying the
        requested amount would leave the user at or above
        the required reserve.

        This is deliberately conservative.

        We use the existing forecast and ask:

            projected balance - purchase price
            >= minimum reserve
        """

        minimum_balance = float(
            state.minimum_balance_to_keep
        )

        daily_forecast = getattr(
            forecast,
            "daily_forecast",
            [],
        )

        if not daily_forecast:

            return None

        for day in daily_forecast:

            projected_balance = float(
                day.closing_balance
            )

            if (
                projected_balance
                - requested_amount
                >= minimum_balance
            ):

                return pd.Timestamp(
                    day.date
                ).normalize()

        return None

    # ========================================================
    # SAFE AMOUNT
    # ========================================================

    @staticmethod
    def _calculate_safe_amount(
        state: Any,
        forecast: Any,
    ) -> float:

        """
        Conservative maximum amount that can be spent
        without crossing the reserve during the forecast.
        """

        minimum_balance = float(
            state.minimum_balance_to_keep
        )

        minimum_projected_balance = float(
            forecast.minimum_projected_balance
        )

        safe_amount = (
            minimum_projected_balance
            - minimum_balance
        )

        return max(
            0.0,
            safe_amount,
        )

    # ========================================================
    # SPENDING CHANGES
    # ========================================================

    @staticmethod
    def _suggest_spending_changes(
        state: Any,
    ) -> List[str]:

        suggestions = []

        reducible = getattr(
            state,
            "reducible_categories",
            [],
        )

        stoppable = getattr(
            state,
            "stoppable_categories",
            [],
        )

        if reducible:

            for category in reducible:

                suggestions.append(
                    f"Consider reducing "
                    f"spending in {category}."
                )

        if stoppable:

            for category in stoppable:

                suggestions.append(
                    f"Consider stopping "
                    f"non-essential spending "
                    f"in {category}."
                )

        return suggestions

    # ========================================================
    # CONFIDENCE
    # ========================================================

    @staticmethod
    def _calculate_confidence(
        affordability: Any,
        payment_result: Any,
        forecast: Any,
    ) -> float:

        score = 1.0

        # Existing forecast warnings reduce confidence.

        if getattr(
            forecast,
            "warnings",
            None,
        ):

            score -= 0.10

        # Affordability warnings.

        if getattr(
            affordability,
            "warnings",
            None,
        ):

            score -= min(
                0.20,
                0.05
                * len(
                    affordability.warnings
                ),
            )

        # Payment-option uncertainty.

        if (
            getattr(
                payment_result,
                "best_plan",
                None,
            )
            is None
        ):

            score -= 0.05

        return round(
            max(
                0.0,
                min(
                    1.0,
                    score,
                ),
            ),
            2,
        )

    # ========================================================
    # FORMAT PLAN
    # ========================================================

    @staticmethod
    def _format_plan(
        plan: Any,
    ) -> str:

        if plan is None:

            return ""

        payments = getattr(
            plan,
            "payments",
            [],
        )

        parts = []

        for payment in payments:

            date = pd.Timestamp(
                payment.date
            ).strftime(
                "%Y-%m-%d"
            )

            amount = float(
                payment.amount
            )

            parts.append(
                f"{date}:{amount:g}"
            )

        return "|".join(
            parts
        )

    # ========================================================
    # GENERIC GETTER
    # ========================================================

    @staticmethod
    def _get(
        obj,
        field,
        default=None,
    ):

        if obj is None:

            return default

        if isinstance(
            obj,
            dict,
        ):

            return obj.get(
                field,
                default,
            )

        try:

            return getattr(
                obj,
                field,
                default,
            )

        except Exception:

            return default


# ============================================================
# REPORT
# ============================================================

def print_decision_report(
    result: DecisionResult,
) -> None:

    print()
    print("=" * 70)
    print(
        "MODEL 7: FINAL DECISION"
    )
    print("=" * 70)

    print(
        f"\nRequest: "
        f"{result.request_id}"
    )

    print(
        f"User: "
        f"{result.user_id}"
    )

    print(
        f"Requested amount:"
        f" {result.requested_amount:,.2f} "
        f"{result.currency}"
    )

    print(
        f"\nDECISION:"
    )

    print(
        f"  {result.decision.upper()}"
    )

    print(
        f"\nSafe amount:"
        f" {result.safe_amount:,.2f} "
        f"{result.currency}"
    )

    if result.payment_method:

        print(
            f"\nPayment method:"
            f" {result.payment_method}"
        )

    if result.payment_option_id:

        print(
            f"Payment option:"
            f" {result.payment_option_id}"
        )

    if result.payment_plan:

        print(
            f"Payment plan:"
        )

        print(
            f"  {result.payment_plan}"
        )

    if result.earliest_safe_date:

        print(
            f"\nEarliest safe date:"
            f" {result.earliest_safe_date.date()}"
        )

    if result.spending_changes:

        print(
            "\nSuggested spending changes:"
        )

        for change in (
            result.spending_changes
        ):

            print(
                f"  - {change}"
            )

    print(
        "\nReasons:"
    )

    for reason in result.reasons:

        print(
            f"  - {reason}"
        )

    if result.warnings:

        print(
            "\nWarnings:"
        )

        for warning in result.warnings:

            print(
                f"  - {warning}"
            )

    print(
        f"\nConfidence:"
        f" {result.confidence:.2f}"
    )

    print(
        "\n" + "=" * 70
    )

    print(
        "MODEL 7 FINAL DECISION: SUCCESS"
    )

    print(
        "=" * 70
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        "BUY OR WAIT? - "
        "MODEL 7: FINAL DECISION ENGINE"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # MODEL 1
    # --------------------------------------------------------

    loader = DatasetLoader(
        "dataset"
    )

    loader.load()

    # --------------------------------------------------------
    # REQUEST
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
    ).normalize()

    print(
        f"\nTest request: "
        f"{request_id}"
    )

    print(
        f"Test user: "
        f"{user_id}"
    )

    print(
        f"Request date: "
        f"{request_date.date()}"
    )

    # --------------------------------------------------------
    # MODEL 2
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
    # MODEL 3
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
    # MODEL 4
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
    # MODEL 5
    # --------------------------------------------------------

    purchase_amount = float(
        request.get(
            "requested_amount",
            0,
        )
    )

    affordability_engine = (
        AffordabilityEngine()
    )

    affordability = (
        affordability_engine.assess(
            state=state,
            forecast=forecast,
            purchase_price=purchase_amount,
            currency=getattr(
                state,
                "home_currency",
                None,
            ),
            request_id=request_id,
        )
    )

    # --------------------------------------------------------
    # MODEL 6
    # --------------------------------------------------------
    #
    # Model 6 needs request payment options.
    # Use the same compatibility approach as Model 6.
    # --------------------------------------------------------

    payment_options = None

    possible_names = [
        "request_payment_options",
        "payment_option",
        "payment_options_df",
        "request_payment_option",
    ]

    for name in possible_names:

        if hasattr(
            loader.data,
            name,
        ):

            value = getattr(
                loader.data,
                name,
            )

            if isinstance(
                value,
                pd.DataFrame,
            ):

                payment_options = value
                break

    if payment_options is None:

        path = (
            "dataset/"
            "request_payment_options.csv"
        )

        payment_options = pd.read_csv(
            path
        )

    optimizer = (
        PaymentPlanOptimizer()
    )

    payment_result = optimizer.optimize(
        request=request,
        state=state,
        forecast=forecast,
        payment_options=payment_options,
    )

    # --------------------------------------------------------
    # MODEL 7
    # --------------------------------------------------------

    engine = DecisionEngine()

    result = engine.decide(
        request=request,
        state=state,
        forecast=forecast,
        affordability=affordability,
        payment_result=payment_result,
    )

    # --------------------------------------------------------
    # REPORT
    # --------------------------------------------------------

    print_decision_report(
        result
    )