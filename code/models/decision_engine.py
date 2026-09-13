"""
Model 7: Final Decision Engine
==============================

Buy or Wait?

Combines:
    - FinancialState
    - CashFlowForecast
    - AffordabilityAssessment
    - PaymentPlan

Produces:
    affordable_now
    affordable_with_plan
    affordable_later
    not_affordable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional

import pandas as pd


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
# ENGINE
# ============================================================

class DecisionEngine:

    VALID_DECISIONS = {
        "affordable_now",
        "affordable_with_plan",
        "affordable_later",
        "not_affordable",
    }

    VALID_PAYMENT_METHODS = {
        "full_payment",
        "partial_payment",
        "installments",
        "wait",
        "not_recommended",
    }

    # ========================================================
    # GENERIC GET
    # ========================================================

    @staticmethod
    def _get(
        obj: Any,
        name: str,
        default: Any = None,
    ) -> Any:

        if obj is None:
            return default

        if isinstance(obj, dict):
            return obj.get(
                name,
                default,
            )

        try:
            value = getattr(
                obj,
                name,
            )
        except Exception:
            return default

        if value is None:
            return default

        return value

    # ========================================================
    # SAFE FLOAT
    # ========================================================

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        try:

            if value is None:
                return default

            value = float(value)

            if pd.isna(value):
                return default

            return value

        except (
            TypeError,
            ValueError,
        ):

            return default

    # ========================================================
    # DATE NORMALIZATION
    # ========================================================

    @staticmethod
    def _to_timestamp(
        value: Any,
    ) -> Optional[pd.Timestamp]:

        if value is None:
            return None

        try:

            ts = pd.Timestamp(
                value
            )

            if pd.isna(ts):
                return None

            return ts.normalize()

        except (
            TypeError,
            ValueError,
        ):

            return None

    # ========================================================
    # PAYMENT PLAN EXTRACTION
    # ========================================================

    def _extract_best_plan(
        self,
        payment_result: Any,
    ) -> Any:

        if payment_result is None:
            return None

        # New optimizer:
        #
        # optimize(...) -> PaymentPlan
        #
        if hasattr(
            payment_result,
            "payment_method",
        ):

            method = getattr(
                payment_result,
                "payment_method",
                None,
            )

            if method not in (
                None,
                "",
                "not_recommended",
            ):

                return payment_result

        # Old optimizer:
        #
        # optimize(...) ->
        # PaymentOptimizationResult
        #
        best_plan = getattr(
            payment_result,
            "best_plan",
            None,
        )

        if best_plan is not None:
            return best_plan

        # Dictionary compatibility

        if isinstance(
            payment_result,
            dict
        ):

            plan = payment_result.get(
                "best_plan"
            )

            if plan is not None:
                return plan

            if payment_result.get(
                "payment_method"
            ) not in (
                None,
                "",
                "not_recommended",
            ):

                return payment_result

        return None

    # ========================================================
    # PAYMENT METHOD
    # ========================================================

    def _payment_method(
        self,
        plan: Any,
    ) -> Optional[str]:

        if plan is None:
            return None

        value = self._get(
            plan,
            "payment_method",
        )

        if value is None:
            value = self._get(
                plan,
                "method",
            )

        if value is None:
            return None

        value = str(
            value
        ).strip()

        if value not in self.VALID_PAYMENT_METHODS:
            return None

        return value

    # ========================================================
    # OPTION ID
    # ========================================================

    def _payment_option_id(
        self,
        plan: Any,
    ) -> Optional[str]:

        if plan is None:
            return None

        value = self._get(
            plan,
            "payment_option_id",
        )

        if value is None:
            return None

        return str(
            value
        )

    # ========================================================
    # PLAN TO STRING
    # ========================================================

    def _plan_to_string(
        self,
        plan: Any,
    ) -> Optional[str]:

        if plan is None:
            return None

        payments = self._get(
            plan,
            "payments",
            [],
        )

        if not payments:
            return None

        result = []

        for payment in payments:

            date = self._get(
                payment,
                "date",
            )

            amount = self._safe_float(
                self._get(
                    payment,
                    "amount",
                    0,
                )
            )

            date = self._to_timestamp(
                date
            )

            if date is None:
                continue

            result.append(
                f"{date.strftime('%Y-%m-%d')}:{amount:g}"
            )

        if not result:
            return None

        return "|".join(
            result
        )

    # ========================================================
    # PLAN IS SAFE
    # ========================================================

    def _plan_is_safe(
        self,
        plan: Any,
    ) -> bool:

        if plan is None:
            return False

        safe = self._get(
            plan,
            "safe",
            True,
        )

        return bool(
            safe
        )

    # ========================================================
    # PLAN DEADLINE
    # ========================================================

    def _plan_completes_by_deadline(
        self,
        plan: Any,
    ) -> bool:

        if plan is None:
            return False

        value = self._get(
            plan,
            "completes_by_deadline",
            True,
        )

        return bool(
            value
        )

    # ========================================================
    # MAIN DECISION
    # ========================================================

    def decide(
        self,
        request: Any,
        state: Any,
        forecast: Any,
        affordability: Any,
        payment_result: Any,
    ) -> DecisionResult:

        # ----------------------------------------------------
        # REQUEST
        # ----------------------------------------------------

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
                self._get(
                    state,
                    "user_id",
                    "unknown",
                ),
            )
        )

        requested_amount = self._safe_float(
            self._get(
                request,
                "requested_amount",
                0,
            )
        )

        request_date = self._to_timestamp(
            self._get(
                request,
                "request_date",
            )
        )

        desired_completion_date = self._to_timestamp(
            self._get(
                request,
                "desired_completion_date",
            )
        )

        currency = str(
            self._get(
                state,
                "home_currency",
                "UNKNOWN",
            )
        )

        # ----------------------------------------------------
        # AFFORDABILITY
        # ----------------------------------------------------

        immediate_affordable = bool(
            self._get(
                affordability,
                "immediate_affordable",
                False,
            )
        )

        future_affordable = bool(
            self._get(
                affordability,
                "future_affordable",
                False,
            )
        )

        safe_amount = self._safe_float(
            self._get(
                affordability,
                "amount_safe_to_pay",
                0,
            )
        )

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # amount_safe_to_pay must always be:
        #
        # 0 <= safe_amount <= requested_amount
        # ----------------------------------------------------

        safe_amount = max(
            0.0,
            min(
                safe_amount,
                requested_amount,
            ),
        )

        # ----------------------------------------------------
        # FORECAST
        # ----------------------------------------------------

        reserve_breached = bool(
            self._get(
                forecast,
                "reserve_breached",
                False,
            )
        )

        # ----------------------------------------------------
        # EARLIEST FULL PAYMENT DATE
        # ----------------------------------------------------

        earliest_safe_date = (
            self._to_timestamp(
                self._get(
                    affordability,
                    "earliest_safe_date",
                    None,
                )
            )
        )

        if (
            earliest_safe_date is None
            and immediate_affordable
        ):
            earliest_safe_date = request_date

        # ----------------------------------------------------
        # PAYMENT PLAN
        # ----------------------------------------------------

        best_plan = (
            self._extract_best_plan(
                payment_result
            )
        )

        payment_method = (
            self._payment_method(
                best_plan
            )
        )

        payment_option_id = (
            self._payment_option_id(
                best_plan
            )
        )

        payment_plan = (
            self._plan_to_string(
                best_plan
            )
        )

        plan_safe = (
            self._plan_is_safe(
                best_plan
            )
        )

        plan_by_deadline = (
            self._plan_completes_by_deadline(
                best_plan
            )
        )

        # ----------------------------------------------------
        # USER PAYMENT PREFERENCES
        # ----------------------------------------------------

        accepted_methods = self._get(
            state,
            "accepted_payment_methods",
            [],
        )

        if accepted_methods is None:
            accepted_methods = []

        if isinstance(
            accepted_methods,
            str,
        ):

            accepted_methods = [
                x.strip()
                for x in accepted_methods.split(
                    "|"
                )
                if x.strip()
            ]

        accepted_methods = [
            str(x).strip()
            for x in accepted_methods
        ]

        # ====================================================
        # DEFAULT RESULT
        # ====================================================

        decision = "not_affordable"

        final_method = None
        final_option_id = None
        final_plan = None

        spending_changes = []

        reasons = []

        warnings = []

        # ====================================================
        # CASE 1
        #
        # FULL AMOUNT SAFE NOW
        # ====================================================

        if (
            immediate_affordable
            and future_affordable
            and not reserve_breached
        ):

            decision = (
                "affordable_now"
            )

            safe_amount = requested_amount

            earliest_safe_date = (
                request_date
            )

            # ------------------------------------------------
            # Prefer optimizer's eligible plan.
            # ------------------------------------------------

            if (
                best_plan is not None
                and plan_safe
                and plan_by_deadline
                and payment_method
                in accepted_methods
            ):

                final_method = (
                    payment_method
                )

                final_option_id = (
                    payment_option_id
                )

                final_plan = (
                    payment_plan
                )

            elif (
                "full_payment"
                in accepted_methods
            ):

                final_method = (
                    "full_payment"
                )

                final_plan = (
                    f"{request_date.strftime('%Y-%m-%d')}:"
                    f"{requested_amount:g}"
                )

            else:

                decision = (
                    "not_affordable"
                )

                warnings.append(
                    "The purchase is financially "
                    "affordable now, but no eligible "
                    "payment method is accepted by "
                    "the user."
                )

            if decision == "affordable_now":

                reasons.extend([
                    "The requested amount is safely "
                    "affordable on the request date.",
                    "The 90-day forecast remains above "
                    "the required minimum reserve.",
                ])

        # ====================================================
        # CASE 2
        #
        # SAFE PLAN EXISTS
        # ====================================================

        if (
            decision == "not_affordable"
            and best_plan is not None
            and plan_safe
            and plan_by_deadline
            and payment_method in accepted_methods
        ):

            decision = (
                "affordable_with_plan"
            )

            final_method = (
                payment_method
            )

            final_option_id = (
                payment_option_id
            )

            final_plan = (
                payment_plan
            )

            reasons.extend([
                "The full request can be completed "
                "safely using an eligible payment plan.",
                "The recommended plan stays within "
                "the user's financial safety constraints.",
            ])

        # ====================================================
        # CASE 3
        #
        # AFFORDABLE LATER
        # ====================================================

        if (
            decision == "not_affordable"
            and future_affordable
            and earliest_safe_date is not None
        ):

            # Only use a future date if it is actually
            # within the desired completion date.

            deadline_ok = True

            if desired_completion_date is not None:

                deadline_ok = (
                    earliest_safe_date
                    <= desired_completion_date
                )

            if deadline_ok:

                decision = (
                    "affordable_later"
                )

                if (
                    "full_payment"
                    in accepted_methods
                ):

                    final_method = (
                        "wait"
                    )

                    final_plan = None

                    reasons.extend([
                        "The full amount is not safely "
                        "payable today.",
                        "The forecast indicates that the "
                        "full amount becomes safe later.",
                    ])

                else:

                    warnings.append(
                        "The full amount becomes safe later, "
                        "but the user does not accept "
                        "full payment."
                    )

        # ====================================================
        # CASE 4
        #
        # NO SAFE OPTION
        # ====================================================

        if decision == "not_affordable":

            final_method = (
                "not_recommended"
            )

            final_option_id = None
            final_plan = None

            safe_amount = max(
                0.0,
                min(
                    safe_amount,
                    requested_amount,
                ),
            )

            reasons.extend([
                "The full request cannot be completed "
                "safely under the current financial "
                "constraints.",
                "No safe eligible payment method can "
                "complete the request by the required "
                "deadline.",
            ])

        # ====================================================
        # SPECIAL RULE:
        #
        # affordable_later must use wait.
        # ====================================================

        if (
            decision == "affordable_later"
            and final_method is None
        ):

            if (
                "full_payment"
                in accepted_methods
            ):

                final_method = "wait"

            else:

                final_method = (
                    "not_recommended"
                )

        # ====================================================
        # SAFETY CHECK FOR PAYMENT METHOD
        # ====================================================

        if final_method not in (
            "full_payment",
            "partial_payment",
            "installments",
            "wait",
            "not_recommended",
        ):

            final_method = (
                "not_recommended"
            )

            final_plan = None

        # ====================================================
        # PAYMENT PLAN VALIDATION
        # ====================================================

        if final_method == "not_recommended":

            final_plan = None

        # ====================================================
        # FULL PAYMENT PLAN
        # ====================================================

        if (
            final_method == "full_payment"
            and final_plan is None
        ):

            if request_date is not None:

                final_plan = (
                    f"{request_date.strftime('%Y-%m-%d')}:"
                    f"{requested_amount:g}"
                )

        # ====================================================
        # WAIT
        # ====================================================

        if final_method == "wait":

            final_plan = None

        # ====================================================
        # CONFIDENCE
        # ====================================================

        confidence = 0.90

        if decision == "not_affordable":
            confidence = 0.95

        elif decision == "affordable_now":
            confidence = 0.95

        elif decision == "affordable_with_plan":
            confidence = 0.90

        elif decision == "affordable_later":
            confidence = 0.88

        # ====================================================
        # FINAL CLAMP
        # ====================================================

        safe_amount = max(
            0.0,
            min(
                safe_amount,
                requested_amount,
            ),
        )

        # ====================================================
        # RETURN
        # ====================================================

        return DecisionResult(

            request_id=request_id,

            user_id=user_id,

            currency=currency,

            decision=decision,

            safe_amount=safe_amount,

            requested_amount=requested_amount,

            payment_method=final_method,

            payment_option_id=final_option_id,

            payment_plan=final_plan,

            earliest_safe_date=earliest_safe_date,

            spending_changes=spending_changes,

            reasons=reasons,

            warnings=warnings,

            confidence=confidence,
        )


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        "BUY OR WAIT? - MODEL 7: DECISION ENGINE"
    )
    print("=" * 70)

    engine = DecisionEngine()

    print()
    print(
        "DecisionEngine loaded successfully."
    )

    print()
    print("=" * 70)
    print(
        "MODEL 7 DECISION ENGINE: SUCCESS"
    )
    print("=" * 70)