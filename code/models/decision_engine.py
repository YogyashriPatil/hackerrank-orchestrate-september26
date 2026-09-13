"""
MODEL 7 — FINAL DECISION ENGINE
===============================

Buy or Wait? - HackerRank Orchestrate

This module combines the outputs of:

    Model 2 -> Financial State
    Model 3 -> Evidence Resolution
    Model 4 -> Cash-Flow Forecast
    Model 5 -> Affordability Engine
    Model 6 -> Payment Plan Optimizer

and produces the final decision.

Supported decisions:

    affordable_now
    affordable_with_plan
    affordable_later
    not_affordable

Important compatibility rule
----------------------------
The current PaymentPlanOptimizer returns a PaymentPlan directly.

Older versions returned an object containing:

    result.best_plan

This implementation supports BOTH formats.
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
    """
    Final result produced by Model 7.
    """

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
    Deterministic final decision engine.

    This class does not modify financial data.

    It only combines the results produced by previous models.
    """

    # ========================================================
    # PUBLIC DECISION METHOD
    # ========================================================

    def decide(
        self,
        request: Any,
        state: Any,
        forecast: Any,
        affordability: Any,
        payment_result: Any,
    ) -> DecisionResult:
        """
        Produce the final financial decision.

        Parameters
        ----------
        request:
            Request row from requests.csv.

        state:
            Financial state produced by Model 2.

        forecast:
            90-day forecast produced by Model 4.

        affordability:
            Affordability result produced by Model 5.

        payment_result:
            Result from Model 6.

        Returns
        -------
        DecisionResult
        """

        # ----------------------------------------------------
        # BASIC REQUEST INFORMATION
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
                getattr(
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

        currency = str(
            getattr(
                state,
                "home_currency",
                "UNKNOWN",
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

        # ----------------------------------------------------
        # AFFORDABILITY INFORMATION
        # ----------------------------------------------------

        immediate_affordable = bool(
            getattr(
                affordability,
                "immediate_affordable",
                False,
            )
        )

        future_affordable = bool(
            getattr(
                affordability,
                "future_affordable",
                False,
            )
        )

        # ----------------------------------------------------
        # BASELINE FORECAST SAFETY
        # ----------------------------------------------------

        baseline_breach = bool(
            getattr(
                forecast,
                "reserve_breached",
                False,
            )
        )

        # ----------------------------------------------------
        # GET PAYMENT PLAN
        #
        # Current optimizer:
        #
        #     PaymentPlan
        #
        # Old optimizer:
        #
        #     PaymentOptimizationResult.best_plan
        # ----------------------------------------------------

        best_plan = self._extract_best_plan(
            payment_result
        )

        plan_available = (
            best_plan is not None
            and self._valid_payment_method(
                getattr(
                    best_plan,
                    "payment_method",
                    None,
                )
            )
        )

        # ----------------------------------------------------
        # DEFAULT VALUES
        # ----------------------------------------------------

        decision = "not_affordable"

        safe_amount = 0.0

        payment_method = None
        payment_option_id = None
        payment_plan = None

        earliest_safe_date = None

        spending_changes: List[str] = []

        reasons: List[str] = []

        # ====================================================
        # CASE 1 — FULL REQUEST IS AFFORDABLE NOW
        # ====================================================

        if (
            immediate_affordable
            and future_affordable
            and not baseline_breach
        ):

            decision = "affordable_now"

            safe_amount = requested_amount

            earliest_safe_date = request_date

            reasons = [
                "The requested amount is safely affordable "
                "on the request date.",
                "The 90-day forecast remains above the "
                "required minimum reserve.",
            ]

            # -----------------------------------------------
            # IMPORTANT:
            #
            # Even when full payment is affordable, the
            # user's preferred payment method must be used.
            #
            # If Model 6 found a safe eligible plan,
            # use it.
            # -----------------------------------------------

            if plan_available:

                payment_method = self._clean_string(
                    getattr(
                        best_plan,
                        "payment_method",
                        None,
                    )
                )

                payment_option_id = self._clean_string(
                    getattr(
                        best_plan,
                        "payment_option_id",
                        None,
                    )
                )

                payment_plan = self._format_plan(
                    best_plan
                )

                # If the optimizer selected full payment,
                # make the result explicit.

                if payment_method == "full_payment":
                    reasons.append(
                        "Full payment is an eligible and safe "
                        "payment method."
                    )

                elif payment_method == "installments":
                    reasons.append(
                        "An eligible installment plan is "
                        "available and safe."
                    )

                elif payment_method == "partial_payment":
                    decision = "affordable_with_plan"

                    reasons.append(
                        "The requested amount is affordable "
                        "through the selected partial-payment plan."
                    )

            else:

                # ------------------------------------------------
                # FALLBACK:
                #
                # If no optimizer plan was returned but the
                # purchase is fully affordable now, full payment
                # is still the mathematically safe method.
                #
                # This is only used when the optimizer failed
                # to provide a plan.
                # ------------------------------------------------

                payment_method = "full_payment"

                payment_plan = self._build_full_payment_plan(
                    request_date,
                    requested_amount,
                )

                reasons.append(
                    "No separate payment option was returned "
                    "by the optimizer, so the safe full-payment "
                    "method is used."
                )

        # ====================================================
        # CASE 2 — NOT AFFORDABLE NOW, BUT SAFE PLAN EXISTS
        # ====================================================

        elif plan_available and not baseline_breach:

            payment_method = self._clean_string(
                getattr(
                    best_plan,
                    "payment_method",
                    None,
                )
            )

            payment_option_id = self._clean_string(
                getattr(
                    best_plan,
                    "payment_option_id",
                    None,
                )
            )

            candidate_plan = self._format_plan(
                best_plan
            )

            # ------------------------------------------------
            # Check whether the selected plan actually has
            # payments.
            # ------------------------------------------------

            has_payments = bool(
                candidate_plan
                and candidate_plan != "none"
            )

            if has_payments:

                # --------------------------------------------
                # Find the last payment date.
                # --------------------------------------------

                last_payment_date = (
                    self._last_payment_date(
                        best_plan
                    )
                )

                # --------------------------------------------
                # A plan is only valid if it completes by the
                # requested deadline.
                # --------------------------------------------

                completes_by_deadline = True

                if (
                    last_payment_date is not None
                    and desired_completion_date is not None
                ):
                    completes_by_deadline = (
                        last_payment_date
                        <= desired_completion_date
                    )

                # --------------------------------------------
                # Partial payment must satisfy the challenge
                # contract.
                # --------------------------------------------

                if payment_method == "partial_payment":

                    partial_valid = (
                        self._valid_partial_payment(
                            request=request,
                            best_plan=best_plan,
                            requested_amount=requested_amount,
                            request_date=request_date,
                            desired_completion_date=(
                                desired_completion_date
                            ),
                        )
                    )

                    if partial_valid:

                        decision = (
                            "affordable_with_plan"
                        )

                        safe_amount = (
                            self._extract_safe_amount(
                                affordability,
                                requested_amount,
                            )
                        )

                        earliest_safe_date = (
                            self._extract_earliest_date(
                                affordability,
                                forecast,
                                request,
                                requested_amount,
                            )
                        )

                        payment_plan = (
                            candidate_plan
                        )

                        reasons = [
                            "The full request is not safely "
                            "affordable as a single immediate payment.",
                            "A valid partial-payment plan can "
                            "complete the request safely by the "
                            "requested deadline.",
                        ]

                    else:

                        payment_method = None
                        payment_option_id = None
                        payment_plan = None

                # --------------------------------------------
                # Installment plan
                # --------------------------------------------

                elif payment_method == "installments":

                    if completes_by_deadline:

                        decision = (
                            "affordable_with_plan"
                        )

                        safe_amount = (
                            self._extract_safe_amount(
                                affordability,
                                requested_amount,
                            )
                        )

                        earliest_safe_date = (
                            self._extract_earliest_date(
                                affordability,
                                forecast,
                                request,
                                requested_amount,
                            )
                        )

                        payment_plan = (
                            candidate_plan
                        )

                        reasons = [
                            "The full request is not safely "
                            "affordable as a single immediate "
                            "payment.",
                            "A supplied installment option "
                            "provides a safe way to complete "
                            "the request.",
                        ]

                    else:

                        payment_method = None
                        payment_option_id = None
                        payment_plan = None

        # ====================================================
        # CASE 3 — FULL AMOUNT BECOMES SAFE LATER
        # ====================================================

        if decision == "not_affordable":

            later_date = (
                self._find_earliest_safe_date(
                    request=request,
                    state=state,
                    forecast=forecast,
                    requested_amount=requested_amount,
                )
            )

            if later_date is not None:

                decision = "affordable_later"

                safe_amount = (
                    self._extract_safe_amount(
                        affordability,
                        requested_amount,
                    )
                )

                earliest_safe_date = later_date

                payment_method = "wait"

                payment_option_id = None

                payment_plan = "none"

                reasons = [
                    "The full requested amount is not "
                    "safely affordable on the request date.",
                    "The forecast identifies a later date "
                    "when the full amount can be paid while "
                    "maintaining the required reserve.",
                ]

        # ====================================================
        # CASE 4 — NOT AFFORDABLE WITHIN FORECAST
        # ====================================================

        if decision == "not_affordable":

            safe_amount = (
                self._calculate_safe_amount(
                    state=state,
                    forecast=forecast,
                    requested_amount=requested_amount,
                )
            )

            earliest_safe_date = None

            payment_method = "not_recommended"

            payment_option_id = None

            payment_plan = "none"

            spending_changes = (
                self._suggest_spending_changes(
                    state
                )
            )

            reasons = [
                "The requested amount cannot be safely "
                "supported within the current forecast.",
                "No eligible payment plan provides a "
                "safe solution within the requested deadline.",
            ]

        # ====================================================
        # SAFETY CLAMP
        # ====================================================

        safe_amount = max(
            0.0,
            min(
                safe_amount,
                requested_amount,
            ),
        )

        # ====================================================
        # WARNINGS
        # ====================================================

        warnings: List[str] = []

        if baseline_breach:

            warnings.append(
                "The baseline 90-day forecast already "
                "breaches the required minimum reserve."
            )

        affordability_warnings = getattr(
            affordability,
            "warnings",
            None,
        )

        if affordability_warnings:

            warnings.extend(
                str(x)
                for x in affordability_warnings
            )

        payment_warnings = getattr(
            payment_result,
            "warnings",
            None,
        )

        if payment_warnings:

            warnings.extend(
                str(x)
                for x in payment_warnings
            )

        warnings = list(
            dict.fromkeys(
                warnings
            )
        )

        # ====================================================
        # CONFIDENCE
        # ====================================================

        confidence = self._calculate_confidence(
            affordability=affordability,
            payment_result=payment_result,
            forecast=forecast,
            decision=decision,
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
            earliest_safe_date=earliest_safe_date,
            spending_changes=spending_changes,
            reasons=reasons,
            warnings=warnings,
            confidence=confidence,
        )

    # ========================================================
    # PAYMENT RESULT COMPATIBILITY
    # ========================================================

    @staticmethod
    def _extract_best_plan(
        payment_result: Any,
    ) -> Any:
        """
        Support both current and old optimizer APIs.

        Current:

            PaymentPlan

        Old:

            PaymentOptimizationResult.best_plan
        """

        if payment_result is None:
            return None

        # Current PaymentPlan object.
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

        # Old wrapper object.
        best_plan = getattr(
            payment_result,
            "best_plan",
            None,
        )

        if best_plan is not None:

            method = getattr(
                best_plan,
                "payment_method",
                None,
            )

            if method not in (
                None,
                "",
                "not_recommended",
            ):
                return best_plan

        return None

    # ========================================================
    # PAYMENT METHOD VALIDATION
    # ========================================================

    @staticmethod
    def _valid_payment_method(
        method: Any,
    ) -> bool:

        return (
            str(method).strip().lower()
            in {
                "full_payment",
                "partial_payment",
                "installments",
            }
        )

    # ========================================================
    # PARTIAL PAYMENT VALIDATION
    # ========================================================

    def _valid_partial_payment(
        self,
        request: Any,
        best_plan: Any,
        requested_amount: float,
        request_date: Optional[pd.Timestamp],
        desired_completion_date: Optional[pd.Timestamp],
    ) -> bool:
        """
        Validate a partial-payment schedule.

        The challenge requires exactly two payments:

            request_date : safe amount

        followed by:

            earliest_safe_date : remaining amount
        """

        payments = getattr(
            best_plan,
            "payments",
            [],
        )

        if len(payments) != 2:
            return False

        first = payments[0]
        second = payments[1]

        first_date = self._to_timestamp(
            self._payment_value(
                first,
                "date",
            )
        )

        second_date = self._to_timestamp(
            self._payment_value(
                second,
                "date",
            )
        )

        first_amount = self._safe_float(
            self._payment_value(
                first,
                "amount",
                0,
            )
        )

        second_amount = self._safe_float(
            self._payment_value(
                second,
                "amount",
                0,
            )
        )

        if (
            request_date is not None
            and first_date is not None
            and first_date != request_date
        ):
            return False

        if first_amount <= 0:
            return False

        if first_amount >= requested_amount:
            return False

        if abs(
            (
                first_amount
                + second_amount
            )
            - requested_amount
        ) > 0.01:

            return False

        if (
            second_date is not None
            and request_date is not None
            and second_date < request_date
        ):
            return False

        if (
            desired_completion_date is not None
            and second_date is not None
            and second_date > desired_completion_date
        ):
            return False

        return True

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
        Find the first forecast date on which the user could
        make the full payment and remain above the reserve.

        This is independent of payment preferences.
        """

        minimum_balance = self._safe_float(
            getattr(
                state,
                "minimum_balance_to_keep",
                0,
            )
        )

        daily_forecast = getattr(
            forecast,
            "daily_forecast",
            [],
        )

        if daily_forecast is None:
            return None

        request_date = self._to_timestamp(
            self._get(
                request,
                "request_date",
            )
        )

        for day in daily_forecast:

            day_date = self._to_timestamp(
                getattr(
                    day,
                    "date",
                    None,
                )
            )

            projected_balance = self._safe_float(
                getattr(
                    day,
                    "projected_balance",
                    getattr(
                        day,
                        "balance",
                        0,
                    ),
                )
            )

            if day_date is None:
                continue

            if (
                request_date is not None
                and day_date < request_date
            ):
                continue

            if (
                projected_balance
                - requested_amount
                >= minimum_balance
            ):

                return day_date

        return None

    # ========================================================
    # SAFE AMOUNT
    # ========================================================

    def _calculate_safe_amount(
        self,
        state: Any,
        forecast: Any,
        requested_amount: float,
    ) -> float:
        """
        Calculate the maximum amount that can be paid now
        while preserving the minimum reserve.

        Uses the most conservative projected balance.
        """

        minimum_balance = self._safe_float(
            getattr(
                state,
                "minimum_balance_to_keep",
                0,
            )
        )

        daily_forecast = getattr(
            forecast,
            "daily_forecast",
            [],
        )

        if daily_forecast:

            balances = []

            for day in daily_forecast:

                value = getattr(
                    day,
                    "projected_balance",
                    getattr(
                        day,
                        "balance",
                        None,
                    ),
                )

                if value is not None:

                    balances.append(
                        self._safe_float(
                            value
                        )
                    )

            if balances:

                minimum_projected = min(
                    balances
                )

                safe = (
                    minimum_projected
                    - minimum_balance
                )

                return max(
                    0.0,
                    min(
                        safe,
                        requested_amount,
                    ),
                )

        # Fallback to current available balance.

        current_balance = self._safe_float(
            getattr(
                state,
                "available_balance",
                getattr(
                    state,
                    "current_balance",
                    0,
                ),
            )
        )

        safe = (
            current_balance
            - minimum_balance
        )

        return max(
            0.0,
            min(
                safe,
                requested_amount,
            ),
        )

    # ========================================================
    # EXTRACT SAFE AMOUNT FROM AFFORDABILITY
    # ========================================================

    def _extract_safe_amount(
        self,
        affordability: Any,
        requested_amount: float,
    ) -> float:
        """
        Read the safe amount from Model 5 when available.
        """

        possible_fields = [
            "amount_safe_to_pay",
            "safe_amount",
            "max_safe_amount",
            "safe_payment_amount",
        ]

        for field_name in possible_fields:

            value = getattr(
                affordability,
                field_name,
                None,
            )

            if value is not None:

                value = self._safe_float(
                    value
                )

                return max(
                    0.0,
                    min(
                        value,
                        requested_amount,
                    ),
                )

        return 0.0

    # ========================================================
    # EXTRACT EARLIEST DATE
    # ========================================================

    def _extract_earliest_date(
        self,
        affordability: Any,
        forecast: Any,
        request: Any,
        requested_amount: float,
    ) -> Optional[pd.Timestamp]:
        """
        Try Model 5 first, then calculate from forecast.
        """

        possible_fields = [
            "earliest_safe_date",
            "earliest_date_for_full_payment",
            "future_safe_date",
        ]

        for field_name in possible_fields:

            value = getattr(
                affordability,
                field_name,
                None,
            )

            if value is not None:

                timestamp = self._to_timestamp(
                    value
                )

                if timestamp is not None:
                    return timestamp

        return self._find_earliest_safe_date(
            request=request,
            state=type(
                "StateProxy",
                (),
                {
                    "minimum_balance_to_keep": 0
                },
            )(),
            forecast=forecast,
            requested_amount=requested_amount,
        )

    # ========================================================
    # FORMAT PAYMENT PLAN
    # ========================================================

    @staticmethod
    def _format_plan(
        plan: Any,
    ) -> str:
        """
        Convert PaymentPlan into required output format.

        Required format:

            YYYY-MM-DD:amount|YYYY-MM-DD:amount
        """

        if plan is None:
            return "none"

        payments = getattr(
            plan,
            "payments",
            [],
        )

        if not payments:
            return "none"

        parts = []

        for payment in payments:

            date_value = (
                DecisionEngine._payment_value(
                    payment,
                    "date",
                )
            )

            amount_value = (
                DecisionEngine._payment_value(
                    payment,
                    "amount",
                    0,
                )
            )

            timestamp = (
                DecisionEngine._to_timestamp(
                    date_value
                )
            )

            if timestamp is None:
                continue

            amount = DecisionEngine._safe_float(
                amount_value
            )

            parts.append(
                f"{timestamp.strftime('%Y-%m-%d')}:{amount:g}"
            )

        if not parts:
            return "none"

        return "|".join(parts)

    # ========================================================
    # FULL PAYMENT PLAN
    # ========================================================

    @staticmethod
    def _build_full_payment_plan(
        request_date: Optional[pd.Timestamp],
        amount: float,
    ) -> str:
        """
        Build a simple full-payment schedule.
        """

        if request_date is None:
            return "none"

        return (
            f"{request_date.strftime('%Y-%m-%d')}:"
            f"{amount:g}"
        )

    # ========================================================
    # LAST PAYMENT DATE
    # ========================================================

    @staticmethod
    def _last_payment_date(
        plan: Any,
    ) -> Optional[pd.Timestamp]:

        payments = getattr(
            plan,
            "payments",
            [],
        )

        dates = []

        for payment in payments:

            value = (
                DecisionEngine._payment_value(
                    payment,
                    "date",
                )
            )

            timestamp = (
                DecisionEngine._to_timestamp(
                    value
                )
            )

            if timestamp is not None:
                dates.append(timestamp)

        if not dates:
            return None

        return max(dates)

    # ========================================================
    # SPENDING CHANGES
    # ========================================================

    @staticmethod
    def _suggest_spending_changes(
        state: Any,
    ) -> List[str]:
        """
        Return spending-change suggestions if the state model
        exposes them.

        This method deliberately does not invent event IDs.
        """

        possible_fields = [
            "recommended_spending_changes",
            "spending_changes",
            "suggested_spending_changes",
        ]

        for field_name in possible_fields:

            value = getattr(
                state,
                field_name,
                None,
            )

            if value:

                if isinstance(
                    value,
                    str,
                ):
                    return [
                        value
                    ]

                try:

                    return [
                        str(x)
                        for x in value
                        if str(x).strip()
                    ]

                except TypeError:
                    pass

        return []

    # ========================================================
    # CONFIDENCE
    # ========================================================

    @staticmethod
    def _calculate_confidence(
        affordability: Any,
        payment_result: Any,
        forecast: Any,
        decision: str,
    ) -> float:
        """
        Calculate deterministic confidence.
        """

        score = 0.90

        if getattr(
            forecast,
            "warnings",
            None,
        ):
            score -= 0.10

        affordability_warnings = getattr(
            affordability,
            "warnings",
            None,
        )

        if affordability_warnings:

            score -= min(
                0.20,
                0.05
                * len(
                    affordability_warnings
                ),
            )

        if payment_result is None:

            score -= 0.10

        else:

            best_plan = (
                DecisionEngine._extract_best_plan(
                    payment_result
                )
            )

            if best_plan is None:

                score -= 0.05

        if decision == "not_affordable":

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
    # GENERIC GETTER
    # ========================================================

    @staticmethod
    def _get(
        obj: Any,
        field: str,
        default: Any = None,
    ) -> Any:

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

    # ========================================================
    # PAYMENT VALUE
    # ========================================================

    @staticmethod
    def _payment_value(
        payment: Any,
        field: str,
        default: Any = None,
    ) -> Any:

        if payment is None:
            return default

        if isinstance(
            payment,
            dict,
        ):

            return payment.get(
                field,
                default,
            )

        return getattr(
            payment,
            field,
            default,
        )

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

            if pd.isna(value):
                return None

        except (
            TypeError,
            ValueError,
        ):
            pass

        try:

            return pd.Timestamp(
                value
            ).normalize()

        except (
            TypeError,
            ValueError,
        ):

            return None

    # ========================================================
    # SAFE FLOAT
    # ========================================================

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0,
    ) -> float:

        if value is None:
            return default

        try:

            if pd.isna(value):
                return default

        except (
            TypeError,
            ValueError,
        ):
            pass

        try:

            return float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            return default

    # ========================================================
    # STRING CLEANING
    # ========================================================

    @staticmethod
    def _clean_string(
        value: Any,
    ) -> Optional[str]:

        if value is None:
            return None

        text = str(
            value
        ).strip()

        if not text:
            return None

        return text

    # ========================================================
    # SAFE PAYMENT METHOD CHECK
    # ========================================================

    @staticmethod
    def _payment_method_from_plan(
        plan: Any,
    ) -> Optional[str]:

        if plan is None:
            return None

        method = getattr(
            plan,
            "payment_method",
            None,
        )

        if method is None:
            return None

        method = str(
            method
        ).strip().lower()

        if method in {
            "full_payment",
            "partial_payment",
            "installments",
        }:
            return method

        return None


# ============================================================
# REPORT
# ============================================================

def print_decision_report(
    result: DecisionResult,
) -> None:
    """
    Human-readable Model 7 report.
    """

    print()
    print("=" * 70)
    print("MODEL 7: FINAL DECISION")
    print("=" * 70)

    print(
        f"\nRequest: {result.request_id}"
    )

    print(
        f"User: {result.user_id}"
    )

    print(
        f"Requested amount: "
        f"{result.requested_amount:,.2f} "
        f"{result.currency}"
    )

    print(
        f"\nDECISION:"
    )

    print(
        f"  {result.decision.upper()}"
    )

    print(
        f"\nSafe amount: "
        f"{result.safe_amount:,.2f} "
        f"{result.currency}"
    )

    if result.payment_method:

        print(
            f"\nPayment method: "
            f"{result.payment_method}"
        )

    if result.payment_option_id:

        print(
            f"Payment option: "
            f"{result.payment_option_id}"
        )

    if result.payment_plan:

        print(
            "\nPayment plan:"
        )

        print(
            f"  {result.payment_plan}"
        )

    if result.earliest_safe_date:

        print(
            f"\nEarliest safe date: "
            f"{result.earliest_safe_date.strftime('%Y-%m-%d')}"
        )

    if result.spending_changes:

        print(
            "\nSuggested spending changes:"
        )

        for change in result.spending_changes:

            print(
                f"  - {change}"
            )

    if result.reasons:

        print(
            "\nWHY:"
        )

        for reason in result.reasons:

            print(
                f"  - {reason}"
            )

    if result.warnings:

        print(
            "\nWARNINGS:"
        )

        for warning in result.warnings:

            print(
                f"  - {warning}"
            )

    print(
        f"\nConfidence: "
        f"{result.confidence:.2f}"
    )

    print(
        "\n" + "=" * 70
    )


# ============================================================
# MODULE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        "BUY OR WAIT? - MODEL 7: DECISION ENGINE"
    )
    print("=" * 70)

    print()
    print(
        "DecisionEngine loaded successfully."
    )

    print()
    print(
        "PaymentPlan compatibility:"
    )

    print(
        "  Current PaymentPlan API: supported"
    )

    print(
        "  Legacy best_plan API: supported"
    )

    print()
    print("=" * 70)
    print(
        "MODEL 7 DECISION ENGINE: SUCCESS"
    )
    print("=" * 70)