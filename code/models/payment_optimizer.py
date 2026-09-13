"""
MODEL 9 — PAYMENT PLAN OPTIMIZER
================================

HackerRank Orchestrate — Buy or Wait?

Responsibilities
----------------
1. Read provider-supplied payment options.
2. Respect user's accepted payment methods.
3. Respect max installment duration.
4. Respect request completion deadline.
5. Check payment schedules against the 90-day forecast.
6. Use the calculated safe amount for the first payment.
7. Select the safest eligible payment option.
8. Support partial-payment plans.
9. Normalize ALL dates to pandas.Timestamp.

Important
---------
The optimizer never invents provider payment options.

Actual payment-option columns:

    payment_option_id
    request_id
    payment_method
    payment_amount
    number_of_payments
    first_payment_date
    payment_frequency_days
    financing_fee
    total_payable_amount
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd


# ============================================================
# PAYMENT PLAN
# ============================================================

@dataclass
class PaymentPlan:
    """One valid payment candidate."""

    payment_option_id: Optional[str]

    payment_method: str

    payments: List[Dict[str, Any]]

    total_payable: float

    financing_fee: float

    first_payment_date: Optional[pd.Timestamp]

    number_of_payments: int

    @property
    def payment_plan_string(self) -> str:
        """Return required YYYY-MM-DD:amount format."""

        if not self.payments:
            return "none"

        return "|".join(
            (
                f"{self.parse_payment_date(payment['date']).strftime('%Y-%m-%d')}:"
                f"{float(payment['amount']):.2f}"
            )
            for payment in self.payments
        )

    @staticmethod
    def parse_payment_date(value) -> pd.Timestamp:
        return pd.Timestamp(value).normalize()


# ============================================================
# OPTIMIZER
# ============================================================

class PaymentPlanOptimizer:
    """
    Deterministic payment-plan optimizer.

    Supports both APIs used during development:

    New API:

        optimize(
            request=request,
            state=state,
            forecast=forecast,
            payment_options=options,
        )

    Compatibility API:

        optimize(
            request_id=...,
            request_date=...,
            requested_amount=...,
            desired_completion_date=...,
            user_payment_methods=...,
            max_installment_months=...,
            amount_safe_to_pay=...,
            earliest_date_for_full_payment=...,
            allows_partial_payment=...,
            payment_options=options,
        )
    """

    ALLOWED_METHODS = {
        "full_payment",
        "partial_payment",
        "installments",
        "wait",
        "not_recommended",
    }

    def __init__(
        self,
        financial_state=None,
        forecast=None,
        payment_options=None,
    ) -> None:

        self.financial_state = financial_state
        self.forecast = forecast
        self.payment_options = payment_options

    # ========================================================
    # DATE HELPERS
    # ========================================================

    @staticmethod
    def parse_date(value) -> Optional[pd.Timestamp]:
        """
        Convert date/date-time/string into normalized Timestamp.

        This is the important fix for:

            Cannot compare Timestamp with datetime.date
        """

        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        try:
            result = pd.Timestamp(value)

            if pd.isna(result):
                return None

            return result.normalize()

        except (TypeError, ValueError):
            return None

    @classmethod
    def format_date(cls, value) -> Optional[str]:

        date = cls.parse_date(value)

        if date is None:
            return None

        return date.strftime("%Y-%m-%d")

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

        if isinstance(obj, dict):
            return obj.get(field, default)

        if isinstance(obj, pd.Series):

            if field in obj.index:
                return obj[field]

            return default

        return getattr(
            obj,
            field,
            default,
        )

    # ========================================================
    # NUMBER HELPERS
    # ========================================================

    @staticmethod
    def _number(value) -> Optional[float]:

        if value is None:
            return None

        try:

            if pd.isna(value):
                return None

        except (TypeError, ValueError):
            pass

        try:
            return float(value)

        except (TypeError, ValueError):
            return None

    @staticmethod
    def _integer(value) -> Optional[int]:

        number = PaymentPlanOptimizer._number(value)

        if number is None:
            return None

        return int(round(number))

    # ========================================================
    # LIST HELPERS
    # ========================================================

    @staticmethod
    def _parse_methods(value) -> set[str]:

        if value is None:
            return set()

        if isinstance(value, (list, tuple, set)):

            parts = value

        else:

            text = str(value).strip()

            if not text:
                return set()

            parts = text.split("|")

        result = set()

        for part in parts:

            normalized = (
                str(part)
                .strip()
                .lower()
            )

            if normalized == "full":
                normalized = "full_payment"

            elif normalized == "full payment":
                normalized = "full_payment"

            elif normalized == "partial":
                normalized = "partial_payment"

            elif normalized == "partial payment":
                normalized = "partial_payment"

            elif normalized == "installment":
                normalized = "installments"

            if normalized:
                result.add(normalized)

        return result

    # ========================================================
    # SAFE AMOUNT
    # ========================================================

    def _safe_amount_from_state(
        self,
        state=None,
        request=None,
    ) -> Optional[float]:

        sources = [
            state,
            request,
        ]

        fields = [
            "amount_safe_to_pay",
            "safe_amount",
            "safe_spending_amount",
            "safe_spending_capacity",
        ]

        for source in sources:

            for field in fields:

                value = self._number(
                    self._get(
                        source,
                        field,
                    )
                )

                if value is not None:
                    return max(
                        0.0,
                        value,
                    )

        return None

    # ========================================================
    # MINIMUM BALANCE
    # ========================================================

    def _minimum_balance(
        self,
        state=None,
    ) -> float:

        for field in (
            "minimum_balance_to_keep",
            "minimum_balance",
            "safety_floor",
            "minimum_safe_balance",
        ):

            value = self._number(
                self._get(
                    state,
                    field,
                )
            )

            if value is not None:
                return value

        return 0.0

    # ========================================================
    # CURRENT BALANCE
    # ========================================================

    def _current_balance(
        self,
        state=None,
    ) -> Optional[float]:

        for field in (
            "current_available_balance",
            "available_balance",
            "current_balance",
            "balance",
        ):

            value = self._number(
                self._get(
                    state,
                    field,
                )
            )

            if value is not None:
                return value

        return None

    # ========================================================
    # MAIN OPTIMIZE
    # ========================================================

    def optimize(
        self,
        request=None,
        state=None,
        forecast=None,
        payment_options=None,

        # Compatibility parameters
        request_id=None,
        request_date=None,
        requested_amount=None,
        desired_completion_date=None,
        user_payment_methods=None,
        max_installment_months=None,
        amount_safe_to_pay=None,
        earliest_date_for_full_payment=None,
        allows_partial_payment=False,

        **kwargs,
    ):
        """
        Main optimizer.

        Supports both the FinancialAgent API and the older
        compatibility API.
        """

        # ----------------------------------------------------
        # Resolve state
        # ----------------------------------------------------

        if state is None:
            state = self.financial_state

        if forecast is None:
            forecast = self.forecast

        # ----------------------------------------------------
        # Resolve payment options
        # ----------------------------------------------------

        if payment_options is None:
            payment_options = self.payment_options

        # ----------------------------------------------------
        # Compatibility request construction
        # ----------------------------------------------------

        if request is None:

            request = {
                "request_id": request_id,
                "request_date": request_date,
                "requested_amount": requested_amount,
                "desired_completion_date": (
                    desired_completion_date
                ),
                "allows_partial_payment": (
                    allows_partial_payment
                ),
            }

        # ----------------------------------------------------
        # Request values
        # ----------------------------------------------------

        request_id_value = str(
            self._get(
                request,
                "request_id",
                request_id or "",
            )
        )

        requested = self._number(
            self._get(
                request,
                "requested_amount",
                requested_amount,
            )
        )

        if requested is None:
            requested = 0.0

        request_date_value = self.parse_date(
            self._get(
                request,
                "request_date",
                request_date,
            )
        )

        if request_date_value is None:
            request_date_value = pd.Timestamp.today().normalize()

        deadline = self.parse_date(
            self._get(
                request,
                "desired_completion_date",
                desired_completion_date,
            )
        )

        # ----------------------------------------------------
        # Accepted methods
        # ----------------------------------------------------

        if user_payment_methods is not None:

            accepted_methods = self._parse_methods(
                user_payment_methods
            )

        else:

            accepted_methods = self._parse_methods(
                self._get(
                    state,
                    "payment_methods_user_will_consider",
                    "",
                )
            )

        # ----------------------------------------------------
        # Max installment months
        # ----------------------------------------------------

        if max_installment_months is None:

            max_installment_months = self._number(
                self._get(
                    state,
                    "max_installment_months",
                )
            )

        else:

            max_installment_months = self._number(
                max_installment_months
            )

        # ----------------------------------------------------
        # Safe amount
        # ----------------------------------------------------

        if amount_safe_to_pay is None:

            amount_safe_to_pay = (
                self._safe_amount_from_state(
                    state=state,
                    request=request,
                )
            )

        else:

            amount_safe_to_pay = self._number(
                amount_safe_to_pay
            )

        if amount_safe_to_pay is not None:

            amount_safe_to_pay = max(
                0.0,
                min(
                    amount_safe_to_pay,
                    requested,
                ),
            )

        # ----------------------------------------------------
        # Normalize payment options
        # ----------------------------------------------------

        options = self._to_records(
            payment_options
        )

        # ----------------------------------------------------
        # No options
        # ----------------------------------------------------

        if not options:

            # Partial payment can still be generated if
            # explicitly permitted and a safe amount exists.

            partial = self._build_partial_plan(
                request=request,
                requested_amount=requested,
                request_date=request_date_value,
                deadline=deadline,
                accepted_methods=accepted_methods,
                amount_safe=amount_safe_to_pay,
                earliest_date=(
                    earliest_date_for_full_payment
                ),
                allows_partial=bool(
                    self._get(
                        request,
                        "allows_partial_payment",
                        allows_partial_payment,
                    )
                ),
                forecast=forecast,
                state=state,
            )

            if partial is not None:
                return partial

            return self._not_recommended(
                "No payment options were supplied."
            )

        # ----------------------------------------------------
        # Build candidates
        # ----------------------------------------------------

        candidates: List[PaymentPlan] = []

        # ----------------------------------------------------
        # Provider-supplied options
        # ----------------------------------------------------

        for option in options:

            candidate = self._evaluate_option(
                option=option,
                request_id=request_id_value,
                request_date=request_date_value,
                deadline=deadline,
                requested_amount=requested,
                accepted_methods=accepted_methods,
                max_installment_months=(
                    max_installment_months
                ),
                safe_amount=amount_safe_to_pay,
                forecast=forecast,
                state=state,
            )

            if candidate is not None:
                candidates.append(candidate)

        # ----------------------------------------------------
        # Partial payment
        # ----------------------------------------------------

        partial = self._build_partial_plan(
            request=request,
            requested_amount=requested,
            request_date=request_date_value,
            deadline=deadline,
            accepted_methods=accepted_methods,
            amount_safe=amount_safe_to_pay,
            earliest_date=(
                earliest_date_for_full_payment
            ),
            allows_partial=bool(
                self._get(
                    request,
                    "allows_partial_payment",
                    allows_partial_payment,
                )
            ),
            forecast=forecast,
            state=state,
        )

        if partial is not None:
            candidates.append(partial)

        # ----------------------------------------------------
        # No safe candidate
        # ----------------------------------------------------

        if not candidates:

            return self._not_recommended(
                self._no_safe_option_reason(
                    accepted_methods,
                    amount_safe_to_pay,
                )
            )

        # ----------------------------------------------------
        # Rank
        # ----------------------------------------------------

        candidates.sort(
            key=self._ranking_key
        )

        return candidates[0]

    # ========================================================
    # PROVIDER OPTION EVALUATION
    # ========================================================

    def _evaluate_option(
        self,
        option: Dict[str, Any],
        request_id: str,
        request_date: pd.Timestamp,
        deadline: Optional[pd.Timestamp],
        requested_amount: float,
        accepted_methods: set[str],
        max_installment_months: Optional[float],
        safe_amount: Optional[float],
        forecast,
        state,
    ) -> Optional[PaymentPlan]:

        option_request_id = str(
            option.get(
                "request_id",
                "",
            )
        ).strip()

        if (
            option_request_id
            and option_request_id != request_id
        ):
            return None

        method = self._normalize_method(
            option.get(
                "payment_method"
            )
        )

        # ----------------------------------------------------
        # Only recognized provider methods
        # ----------------------------------------------------

        if method not in {
            "full_payment",
            "installments",
            "partial_payment",
        }:

            return None

        # ----------------------------------------------------
        # User preference
        # ----------------------------------------------------

        if (
            accepted_methods
            and method not in accepted_methods
        ):

            return None

        # ----------------------------------------------------
        # Numbers
        # ----------------------------------------------------

        payment_amount = self._number(
            option.get(
                "payment_amount"
            )
        )

        number_of_payments = self._integer(
            option.get(
                "number_of_payments"
            )
        )

        financing_fee = self._number(
            option.get(
                "financing_fee"
            )
        )

        total_payable = self._number(
            option.get(
                "total_payable_amount"
            )
        )

        if payment_amount is None:
            return None

        if payment_amount <= 0:
            return None

        if number_of_payments is None:
            number_of_payments = 1

        if number_of_payments <= 0:
            return None

        if financing_fee is None:
            financing_fee = 0.0

        if total_payable is None:

            total_payable = (
                payment_amount
                * number_of_payments
                + financing_fee
            )

        # ----------------------------------------------------
        # Installment duration
        # ----------------------------------------------------

        if method == "installments":

            if max_installment_months is None:
                return None

            # Dataset expresses the number of payments.
            # Treat the supplied maximum as maximum number
            # of installment payments, matching the existing
            # project implementation.

            if (
                number_of_payments
                > max_installment_months
            ):
                return None

        # ----------------------------------------------------
        # First payment date
        # ----------------------------------------------------

        first_payment_date = self.parse_date(
            option.get(
                "first_payment_date"
            )
        )

        if first_payment_date is None:
            return None

        # ----------------------------------------------------
        # Frequency
        # ----------------------------------------------------

        frequency_days = self._number(
            option.get(
                "payment_frequency_days"
            )
        )

        if frequency_days is None:
            frequency_days = 0.0

        # ----------------------------------------------------
        # Build exact supplied schedule
        # ----------------------------------------------------

        schedule = self._build_schedule(
            first_payment_date=first_payment_date,
            payment_amount=payment_amount,
            number_of_payments=number_of_payments,
            frequency_days=frequency_days,
        )

        if not schedule:
            return None

        # ----------------------------------------------------
        # Deadline
        # ----------------------------------------------------

        last_payment_date = self.parse_date(
            schedule[-1]["date"]
        )

        if (
            deadline is not None
            and last_payment_date > deadline
        ):
            return None

        # ----------------------------------------------------
        # First payment must be affordable now.
        #
        # This is critical for installment plans.
        # ----------------------------------------------------

        if (
            safe_amount is not None
            and payment_amount > safe_amount + 1e-9
        ):
            return None

        # ----------------------------------------------------
        # Full payment must actually equal request amount
        # ----------------------------------------------------

        if method == "full_payment":

            if (
                abs(
                    payment_amount
                    - requested_amount
                )
                > 1e-6
            ):
                return None

            if number_of_payments != 1:
                return None

        # ----------------------------------------------------
        # Check 90-day forecast
        # ----------------------------------------------------

        plan = PaymentPlan(
            payment_option_id=str(
                option.get(
                    "payment_option_id",
                    "",
                )
            ),
            payment_method=method,
            payments=schedule,
            total_payable=float(
                total_payable
            ),
            financing_fee=float(
                financing_fee
            ),
            first_payment_date=first_payment_date,
            number_of_payments=int(
                number_of_payments
            ),
        )

        if not self._plan_is_safe(
            plan=plan,
            forecast=forecast,
            state=state,
            request_date=request_date,
        ):
            return None

        return plan

    # ========================================================
    # PARTIAL PAYMENT
    # ========================================================

    def _build_partial_plan(
        self,
        request,
        requested_amount: float,
        request_date: pd.Timestamp,
        deadline: Optional[pd.Timestamp],
        accepted_methods: set[str],
        amount_safe: Optional[float],
        earliest_date,
        allows_partial: bool,
        forecast,
        state,
    ) -> Optional[PaymentPlan]:

        # Request must allow partial payment.

        if not allows_partial:
            return None

        # User must accept partial payment.

        if (
            accepted_methods
            and "partial_payment"
            not in accepted_methods
        ):
            return None

        if amount_safe is None:
            return None

        # Must be strictly between zero and full amount.

        if amount_safe <= 0:
            return None

        if amount_safe >= requested_amount:
            return None

        # Need date for second payment.

        second_date = self.parse_date(
            earliest_date
        )

        if second_date is None:
            return None

        # Must be after today's/request date.

        if second_date < request_date:
            return None

        # Must meet deadline.

        if (
            deadline is not None
            and second_date > deadline
        ):
            return None

        remaining = (
            requested_amount
            - amount_safe
        )

        if remaining <= 0:
            return None

        schedule = [
            {
                "date": request_date,
                "amount": float(
                    amount_safe
                ),
            },
            {
                "date": second_date,
                "amount": float(
                    remaining
                ),
            },
        ]

        plan = PaymentPlan(
            payment_option_id=None,
            payment_method="partial_payment",
            payments=schedule,
            total_payable=float(
                requested_amount
            ),
            financing_fee=0.0,
            first_payment_date=request_date,
            number_of_payments=2,
        )

        if not self._plan_is_safe(
            plan=plan,
            forecast=forecast,
            state=state,
            request_date=request_date,
        ):
            return None

        return plan

    # ========================================================
    # BUILD SCHEDULE
    # ========================================================

    def _build_schedule(
        self,
        first_payment_date: pd.Timestamp,
        payment_amount: float,
        number_of_payments: int,
        frequency_days: float,
    ) -> List[Dict[str, Any]]:

        first_payment_date = self.parse_date(
            first_payment_date
        )

        if first_payment_date is None:
            return []

        result = []

        for index in range(
            max(
                1,
                int(number_of_payments),
            )
        ):

            payment_date = (
                first_payment_date
                + pd.Timedelta(
                    days=(
                        frequency_days
                        * index
                    )
                )
            )

            payment_date = self.parse_date(
                payment_date
            )

            result.append(
                {
                    "date": payment_date,
                    "amount": float(
                        payment_amount
                    ),
                }
            )

        return result

    # ========================================================
    # FORECAST SAFETY
    # ========================================================

    def _plan_is_safe(
        self,
        plan: PaymentPlan,
        forecast,
        state,
        request_date: pd.Timestamp,
    ) -> bool:

        # ----------------------------------------------------
        # No forecast
        # ----------------------------------------------------

        if forecast is None:

            current_balance = (
                self._current_balance(
                    state
                )
            )

            if current_balance is None:
                return True

            minimum_balance = (
                self._minimum_balance(
                    state
                )
            )

            running_balance = float(
                current_balance
            )

            for payment in plan.payments:

                running_balance -= float(
                    payment["amount"]
                )

                if (
                    running_balance
                    < minimum_balance
                ):
                    return False

            return True

        # ----------------------------------------------------
        # Get daily forecast
        # ----------------------------------------------------

        daily_forecast = getattr(
            forecast,
            "daily_forecast",
            None,
        )

        if daily_forecast is None:

            # Some implementations may expose
            # a DataFrame instead.

            if isinstance(
                forecast,
                pd.DataFrame,
            ):

                daily_forecast = (
                    forecast.to_dict(
                        "records"
                    )
                )

            else:

                daily_forecast = []

        if not daily_forecast:

            # Do not fail every request merely because the
            # forecast object uses a different representation.
            #
            # Fall back to current balance check.

            current_balance = (
                self._current_balance(
                    state
                )
            )

            if current_balance is None:
                return True

            minimum_balance = (
                self._minimum_balance(
                    state
                )
            )

            running_balance = float(
                current_balance
            )

            for payment in plan.payments:

                running_balance -= float(
                    payment["amount"]
                )

                if (
                    running_balance
                    < minimum_balance
                ):
                    return False

            return True

        # ----------------------------------------------------
        # Payments by normalized date
        # ----------------------------------------------------

        payments_by_date: Dict[
            pd.Timestamp,
            float,
        ] = {}

        for payment in plan.payments:

            payment_date = self.parse_date(
                payment["date"]
            )

            if payment_date is None:
                return False

            amount = float(
                payment["amount"]
            )

            payments_by_date[
                payment_date
            ] = (
                payments_by_date.get(
                    payment_date,
                    0.0,
                )
                + amount
            )

        # ----------------------------------------------------
        # Minimum reserve
        # ----------------------------------------------------

        minimum_balance = (
            self._minimum_balance(
                state
            )
        )

        cumulative_payments = 0.0

        # ----------------------------------------------------
        # Check every forecast day
        # ----------------------------------------------------

        for day in daily_forecast:

            day_date = self._forecast_value(
                day,
                "date",
            )

            day_date = self.parse_date(
                day_date
            )

            if day_date is None:
                continue

            baseline_balance = (
                self._forecast_value(
                    day,
                    "closing_balance",
                )
            )

            if baseline_balance is None:

                baseline_balance = (
                    self._forecast_value(
                        day,
                        "balance",
                    )
                )

            if baseline_balance is None:
                continue

            baseline_balance = float(
                baseline_balance
            )

            # Apply payment exactly on its date.

            if day_date in payments_by_date:

                cumulative_payments += (
                    payments_by_date[
                        day_date
                    ]
                )

            adjusted_balance = (
                baseline_balance
                - cumulative_payments
            )

            if (
                adjusted_balance
                < minimum_balance - 1e-9
            ):
                return False

        return True

    # ========================================================
    # FORECAST VALUE
    # ========================================================

    @staticmethod
    def _forecast_value(
        obj,
        field,
    ):

        if isinstance(
            obj,
            dict,
        ):
            return obj.get(
                field
            )

        if isinstance(
            obj,
            pd.Series,
        ):

            if field in obj.index:
                return obj[field]

            return None

        return getattr(
            obj,
            field,
            None,
        )

    # ========================================================
    # RANKING
    # ========================================================

    @staticmethod
    def _ranking_key(
        plan: PaymentPlan,
    ):

        # Challenge preference:
        #
        # 1. Complete by deadline
        # 2. No spending changes
        # 3. Lowest total cost
        # 4. Earlier start
        # 5. Fewer payments
        # 6. Lowest option ID
        #
        # Spending changes are not part of PaymentPlan,
        # so this model ranks the supplied plans by cost/date/count.

        try:

            option_number = int(
                str(
                    plan.payment_option_id
                ).split("_")[-1]
            )

        except Exception:

            option_number = 999999

        first_date = (
            plan.first_payment_date
            if plan.first_payment_date
            is not None
            else pd.Timestamp.max
        )

        return (
            float(
                plan.total_payable
            ),

            first_date,

            int(
                plan.number_of_payments
            ),

            option_number,
        )

    # ========================================================
    # PAYMENT METHOD NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_method(
        value,
    ) -> str:

        if value is None:
            return ""

        value = str(
            value
        ).strip().lower()

        aliases = {

            "full":
                "full_payment",

            "full payment":
                "full_payment",

            "full_payment":
                "full_payment",

            "partial":
                "partial_payment",

            "partial payment":
                "partial_payment",

            "partial_payment":
                "partial_payment",

            "installment":
                "installments",

            "installments":
                "installments",

            "wait":
                "wait",

            "not recommended":
                "not_recommended",

            "not_recommended":
                "not_recommended",
        }

        return aliases.get(
            value,
            value,
        )

    # ========================================================
    # DATAFRAME TO RECORDS
    # ========================================================

    @staticmethod
    def _to_records(
        payment_options,
    ) -> List[Dict[str, Any]]:

        if payment_options is None:
            return []

        if isinstance(
            payment_options,
            pd.DataFrame,
        ):

            if payment_options.empty:
                return []

            return payment_options.to_dict(
                "records"
            )

        if isinstance(
            payment_options,
            list,
        ):

            result = []

            for item in payment_options:

                if isinstance(
                    item,
                    dict,
                ):

                    result.append(
                        item
                    )

                elif isinstance(
                    item,
                    pd.Series,
                ):

                    result.append(
                        item.to_dict()
                    )

            return result

        if isinstance(
            payment_options,
            dict,
        ):

            return [payment_options]

        return []

    # ========================================================
    # NO RECOMMENDATION
    # ========================================================

    @staticmethod
    def _not_recommended(
        reason: str,
    ) -> PaymentPlan:

        return PaymentPlan(
            payment_option_id=None,
            payment_method="not_recommended",
            payments=[],
            total_payable=0.0,
            financing_fee=0.0,
            first_payment_date=None,
            number_of_payments=0,
        )

    @staticmethod
    def _no_safe_option_reason(
        accepted_methods,
        safe_amount,
    ) -> str:

        if accepted_methods:

            return (
                "No supplied payment option is both "
                "accepted by the user and safe under "
                "the current and forecast financial "
                "constraints."
            )

        if safe_amount is not None:

            return (
                "No supplied payment option is safe "
                "under the current and forecast "
                "financial constraints."
            )

        return (
            "No eligible payment option could be "
            "identified."
        )


# ============================================================
# COMMAND-LINE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        "BUY OR WAIT? - MODEL 9: PAYMENT PLAN OPTIMIZER"
    )
    print("=" * 70)

    print()
    print(
        "PaymentPlanOptimizer loaded successfully."
    )

    print()
    print(
        "Date normalization test:"
    )

    tests = [
        "2026-01-01",
        pd.Timestamp(
            "2026-01-02"
        ),
        pd.Timestamp(
            "2026-01-03"
        ).date(),
    ]

    for value in tests:

        parsed = (
            PaymentPlanOptimizer.parse_date(
                value
            )
        )

        print(
            f"  {value!r} -> "
            f"{parsed!r} "
            f"({type(parsed).__name__})"
        )

    print()
    print("=" * 70)
    print(
        "MODEL 9 PAYMENT OPTIMIZER: SUCCESS"
    )
    print("=" * 70)