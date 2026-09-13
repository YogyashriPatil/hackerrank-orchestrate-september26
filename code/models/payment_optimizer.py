"""
Model 6: Payment Plan Optimizer
================================

Buy or Wait? - HackerRank Orchestrate

Purpose
-------
Compare all payment approaches that are actually available and
acceptable to the user.

Inputs
------
1. FinancialState from Model 2
2. CashFlowForecast from Model 4
3. Current request from requests.csv
4. Payment options from request_payment_options.csv

Outputs
-------
A ranked set of safe payment plans and the best eligible plan.

Important project rules
-----------------------
- Never invent a payment option.
- Immediate payment methods are eligible only when the user accepts them.
- Installments must match a supplied payment option exactly.
- Installments must respect max_installment_months.
- A plan must never make the balance fall below minimum_balance_to_keep.
- A plan must finish by desired_completion_date.
- Full-payment capacity is calculated independently from user preference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Any

import pandas as pd

from .data_loader import DatasetLoader
from .financial_state import FinancialStateBuilder
from .evidence_resolver import EvidenceResolver
from .cashflow_forecast import CashFlowForecaster


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class PlannedPayment:
    """
    One payment in a payment plan.
    """

    date: pd.Timestamp

    amount: float


@dataclass
class PaymentPlan:
    """
    Candidate payment plan.
    """

    payment_method: str

    payment_option_id: str

    payments: List[PlannedPayment]

    total_paid: float

    financing_fee: float

    safe: bool

    completes_by_deadline: bool

    starts_on: pd.Timestamp

    number_of_payments: int

    reason: str = ""


@dataclass
class PaymentOptimizationResult:
    """
    Complete result from Model 6.
    """

    request_id: str

    requested_amount: float

    currency: str

    accepted_payment_methods: List[str]

    max_installment_months: Optional[int]

    candidates: List[PaymentPlan] = field(
        default_factory=list
    )

    safe_candidates: List[PaymentPlan] = field(
        default_factory=list
    )

    best_plan: Optional[PaymentPlan] = None

    status: str = "no_safe_plan"

    warnings: List[str] = field(
        default_factory=list
    )


# ============================================================
# OPTIMIZER
# ============================================================

class PaymentPlanOptimizer:
    """
    Compare and rank payment plans.

    The optimizer is deterministic.

    Ranking follows the challenge rules:

        1. Complete by desired completion date
        2. No spending changes
        3. Minimize total amount paid
        4. Start earlier
        5. Fewer payments
        6. Lowest payment_option_id
    """

    def optimize(
        self,
        request: Any,
        state: Any,
        forecast: Any,
        payment_options: pd.DataFrame,
    ) -> PaymentOptimizationResult:

        request_id = str(
            self._get(
                request,
                "request_id",
                "unknown",
            )
        )

        requested_amount = self._number(
            self._get(
                request,
                "requested_amount",
                0,
            )
        )

        request_date = pd.Timestamp(
            self._get(
                request,
                "request_date",
            )
        ).normalize()

        desired_completion_date = (
            pd.Timestamp(
                self._get(
                    request,
                    "desired_completion_date",
                )
            ).normalize()
        )

        accepted_methods = (
            self._parse_list(
                self._get(
                    state,
                    "payment_methods_user_will_consider",
                    "",
                )
            )
        )

        max_installment_months = (
            self._optional_int(
                self._get(
                    state,
                    "max_installment_months",
                    None,
                )
            )
        )

        currency = str(
            self._get(
                state,
                "home_currency",
                "UNKNOWN",
            )
        )

        result = PaymentOptimizationResult(
            request_id=request_id,
            requested_amount=requested_amount,
            currency=currency,
            accepted_payment_methods=(
                accepted_methods
            ),
            max_installment_months=(
                max_installment_months
            ),
        )

        # ----------------------------------------------------
        # Build supplied payment-option candidates.
        # ----------------------------------------------------

        supplied_candidates = (
            self._build_supplied_candidates(
                payment_options=payment_options,
                request_id=request_id,
                request_date=request_date,
                deadline=desired_completion_date,
                accepted_methods=accepted_methods,
                max_installment_months=(
                    max_installment_months
                ),
            )
        )

        result.candidates.extend(
            supplied_candidates
        )

        # ----------------------------------------------------
        # Partial payment is NOT required to match an option.
        # It is generated separately later by the final
        # decision engine.
        #
        # Model 6 only records that it is a possible method
        # when the request and user preferences permit it.
        # ----------------------------------------------------

        # ----------------------------------------------------
        # Check every supplied candidate against the
        # actual 90-day forecast.
        # ----------------------------------------------------

        safe_candidates = []

        for candidate in result.candidates:

            candidate.safe = (
                self._plan_is_safe(
                    candidate,
                    forecast=forecast,
                    minimum_balance=float(
                        state.minimum_balance_to_keep
                    ),
                    request_date=request_date,
                )
            )

            candidate.completes_by_deadline = (
                all(
                    payment.date
                    <= desired_completion_date
                    for payment
                    in candidate.payments
                )
            )

            if candidate.safe:

                safe_candidates.append(
                    candidate
                )

        result.safe_candidates = (
            safe_candidates
        )

        # ----------------------------------------------------
        # Rank safe candidates.
        # ----------------------------------------------------

        if safe_candidates:

            ranked = sorted(
                safe_candidates,
                key=lambda plan:
                self._ranking_key(
                    plan
                ),
            )

            result.best_plan = ranked[0]

            result.status = "safe_plan_found"

        else:

            result.status = "no_safe_plan"

            result.warnings.append(
                "No supplied payment option is both "
                "user-accepted and safe under the "
                "90-day cash-flow forecast."
            )

        return result

    # ========================================================
    # BUILD SUPPLIED OPTIONS
    # ========================================================

    def _build_supplied_candidates(
        self,
        payment_options: pd.DataFrame,
        request_id: str,
        request_date: pd.Timestamp,
        deadline: pd.Timestamp,
        accepted_methods: List[str],
        max_installment_months: Optional[int],
    ) -> List[PaymentPlan]:

        if payment_options is None:

            return []

        if payment_options.empty:

            return []

        candidates = []

        # ----------------------------------------------------
        # Only options belonging to this request.
        # ----------------------------------------------------

        if "request_id" in payment_options.columns:

            rows = payment_options[
                payment_options[
                    "request_id"
                ].astype(str)
                == request_id
            ]

        else:

            rows = payment_options

        for _, row in rows.iterrows():

            payment_option_id = str(
                row.get(
                    "payment_option_id",
                    "",
                )
            )

            payment_method = (
                str(
                    row.get(
                        "payment_method",
                        "",
                    )
                )
                .strip()
                .lower()
            )

            # ------------------------------------------------
            # User preference check
            # ------------------------------------------------

            if (
                payment_method
                not in accepted_methods
            ):

                continue

            # ------------------------------------------------
            # Installment duration check
            # ------------------------------------------------

            number_of_payments = (
                self._number(
                    row.get(
                        "number_of_payments",
                        1,
                    )
                )
            )

            if (
                payment_method
                == "installments"
            ):

                if (
                    max_installment_months
                    is None
                ):

                    continue

                if (
                    number_of_payments
                    > max_installment_months
                ):

                    continue

            # ------------------------------------------------
            # First payment date
            # ------------------------------------------------

            first_payment_date = (
                self._parse_date(
                    row.get(
                        "first_payment_date"
                    )
                )
            )

            if first_payment_date is None:

                continue

            # ------------------------------------------------
            # Payment amount
            # ------------------------------------------------

            payment_amount = (
                self._number(
                    row.get(
                        "payment_amount",
                        0,
                    )
                )
            )

            total_payable = (
                self._number(
                    row.get(
                        "total_payable_amount",
                        0,
                    )
                )
            )

            financing_fee = (
                self._number(
                    row.get(
                        "financing_fee",
                        0,
                    )
                )
            )

            if (
                payment_amount <= 0
                or number_of_payments <= 0
            ):

                continue

            # ------------------------------------------------
            # Frequency
            # ------------------------------------------------

            frequency = (
                self._number(
                    row.get(
                        "payment_frequency_days",
                        0,
                    )
                )
            )

            # ------------------------------------------------
            # Construct exact supplied schedule.
            # ------------------------------------------------

            payments = []

            for index in range(
                int(number_of_payments)
            ):

                if index == 0:

                    payment_date = (
                        first_payment_date
                    )

                else:

                    payment_date = (
                        first_payment_date
                        + pd.Timedelta(
                            days=(
                                frequency
                                * index
                            )
                        )
                    )

                payments.append(
                    PlannedPayment(
                        date=payment_date,
                        amount=payment_amount,
                    )
                )

            # ------------------------------------------------
            # If total payable amount is supplied, preserve
            # it as the authoritative total cost.
            #
            # The schedule itself must remain exactly the
            # supplied payment schedule.
            # ------------------------------------------------

            if total_payable <= 0:

                total_payable = (
                    payment_amount
                    * number_of_payments
                    + financing_fee
                )

            # ------------------------------------------------
            # Completion deadline.
            # ------------------------------------------------

            completes = all(
                payment.date
                <= deadline
                for payment
                in payments
            )

            reason = ""

            if not completes:

                reason = (
                    "Payment schedule extends "
                    "past the requested completion date."
                )

            candidates.append(
                PaymentPlan(
                    payment_method=(
                        payment_method
                    ),
                    payment_option_id=(
                        payment_option_id
                    ),
                    payments=payments,
                    total_paid=(
                        total_payable
                    ),
                    financing_fee=(
                        financing_fee
                    ),
                    safe=False,
                    completes_by_deadline=(
                        completes
                    ),
                    starts_on=(
                        payments[0].date
                    ),
                    number_of_payments=(
                        int(
                            number_of_payments
                        )
                    ),
                    reason=reason,
                )
            )

        return candidates

    # ========================================================
    # PLAN SAFETY
    # ========================================================

    @staticmethod
    def _plan_is_safe(
        plan: PaymentPlan,
        forecast: Any,
        minimum_balance: float,
        request_date: pd.Timestamp,
    ) -> bool:

        """
        Verify the payment plan against every forecast day.

        If the baseline forecast closing balance is B and a
        payment P happens on that date, the adjusted balance is:

            B - cumulative payments so far

        The balance must remain >= minimum_balance after
        every payment and throughout the forecast horizon.
        """

        daily_forecast = getattr(
            forecast,
            "daily_forecast",
            [],
        )

        if not daily_forecast:

            return False

        payments_by_date = {}

        for payment in plan.payments:

            date = (
                pd.Timestamp(
                    payment.date
                ).normalize()
            )

            payments_by_date[date] = (
                payments_by_date.get(
                    date,
                    0.0,
                )
                + float(
                    payment.amount
                )
            )

        cumulative_payment = 0.0

        for day in daily_forecast:

            current_date = (
                pd.Timestamp(
                    day.date
                ).normalize()
            )

            # ------------------------------------------------
            # Payments only begin on/after their scheduled
            # date.
            # ------------------------------------------------

            if (
                current_date
                in payments_by_date
            ):

                cumulative_payment += (
                    payments_by_date[
                        current_date
                    ]
                )

            baseline_balance = float(
                day.closing_balance
            )

            adjusted_balance = (
                baseline_balance
                - cumulative_payment
            )

            # ------------------------------------------------
            # Hard safety rule.
            # ------------------------------------------------

            if (
                adjusted_balance
                < minimum_balance
            ):

                return False

        return True

    # ========================================================
    # RANKING
    # ========================================================

    @staticmethod
    def _ranking_key(
        plan: PaymentPlan,
    ):

        """
        Smaller tuple wins.

        Challenge ranking:

        1. Complete by deadline
        2. No spending changes
        3. Minimize total payment cost
        4. Start earlier
        5. Fewer payments
        6. Lowest payment_option_id
        """

        try:

            option_number = int(
                str(
                    plan.payment_option_id
                ).split("_")[-1]
            )

        except Exception:

            option_number = 999999

        return (
            0
            if plan.completes_by_deadline
            else 1,

            float(
                plan.total_paid
            ),

            plan.starts_on,

            int(
                plan.number_of_payments
            ),

            option_number,

            str(
                plan.payment_option_id
            ),
        )

    # ========================================================
    # HELPERS
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

            value = getattr(
                obj,
                field,
                default,
            )

            # pandas Series
            if value is default:

                try:

                    if (
                        field in obj.index
                    ):

                        return obj[field]

                except Exception:

                    pass

            return value

        except Exception:

            return default

    @staticmethod
    def _number(
        value,
    ) -> float:

        if value is None:

            return 0.0

        try:

            if pd.isna(value):

                return 0.0

        except Exception:

            pass

        try:

            return float(value)

        except (
            TypeError,
            ValueError,
        ):

            return 0.0

    @staticmethod
    def _optional_int(
        value,
    ) -> Optional[int]:

        if value is None:

            return None

        try:

            if pd.isna(value):

                return None

        except Exception:

            pass

        try:

            return int(
                float(value)
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

    @staticmethod
    def _parse_date(
        value,
    ) -> Optional[pd.Timestamp]:

        if value is None:

            return None

        try:

            parsed = pd.to_datetime(
                value,
                errors="coerce",
            )

            if pd.isna(parsed):

                return None

            return pd.Timestamp(
                parsed
            ).normalize()

        except Exception:

            return None

    @staticmethod
    def _parse_list(
        value,
    ) -> List[str]:

        if value is None:

            return []

        if isinstance(
            value,
            list,
        ):

            return [
                str(item)
                .strip()
                .lower()
                for item in value
                if str(item).strip()
            ]

        text = str(
            value
        ).strip()

        if not text:

            return []

        # Dataset uses "|" separators.
        return [
            item.strip().lower()
            for item in text.split("|")
            if item.strip()
        ]


# ============================================================
# FORMAT PAYMENT PLAN
# ============================================================

def format_payment_plan(
    plan: Optional[PaymentPlan],
) -> str:

    if plan is None:

        return "none"

    return "|".join(
        (
            f"{payment.date.strftime('%Y-%m-%d')}:"
            f"{payment.amount:g}"
        )
        for payment in plan.payments
    )


# ============================================================
# PRINT REPORT
# ============================================================

def print_optimizer_report(
    result: PaymentOptimizationResult,
) -> None:

    print()
    print("=" * 70)
    print(
        "MODEL 6: PAYMENT PLAN OPTIMIZER"
    )
    print("=" * 70)

    print(
        f"\nRequest: "
        f"{result.request_id}"
    )

    print(
        f"Requested amount: "
        f"{result.requested_amount:,.2f} "
        f"{result.currency}"
    )

    print(
        "\nUser accepted methods:"
    )

    print(
        "  "
        + (
            ", ".join(
                result.accepted_payment_methods
            )
            if result.accepted_payment_methods
            else "none"
        )
    )

    print(
        f"\nMaximum installment months: "
        f"{result.max_installment_months}"
    )

    print(
        f"\nEligible supplied options: "
        f"{len(result.candidates)}"
    )

    print(
        f"Safe options: "
        f"{len(result.safe_candidates)}"
    )

    print()

    if result.safe_candidates:

        print(
            "SAFE PAYMENT OPTIONS:"
        )

        for index, plan in enumerate(
            sorted(
                result.safe_candidates,
                key=lambda item:
                PaymentPlanOptimizer
                ._ranking_key(item),
            ),
            start=1,
        ):

            print(
                f"\n  {index}. "
                f"{plan.payment_method}"
            )

            print(
                f"     Option ID: "
                f"{plan.payment_option_id}"
            )

            print(
                f"     Total paid: "
                f"{plan.total_paid:,.2f}"
            )

            print(
                f"     Financing fee: "
                f"{plan.financing_fee:,.2f}"
            )

            print(
                f"     Payments: "
                f"{plan.number_of_payments}"
            )

            print(
                f"     Plan: "
                f"{format_payment_plan(plan)}"
            )

    if result.best_plan:

        print(
            "\n" + "-" * 70
        )

        print(
            "BEST PAYMENT PLAN:"
        )

        print(
            f"  Method: "
            f"{result.best_plan.payment_method}"
        )

        print(
            f"  Option: "
            f"{result.best_plan.payment_option_id}"
        )

        print(
            f"  Total paid: "
            f"{result.best_plan.total_paid:,.2f}"
        )

        print(
            f"  Plan: "
            f"{format_payment_plan(result.best_plan)}"
        )

    else:

        print(
            "\nNo safe supplied payment plan found."
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
        "\n" + "=" * 70
    )

    print(
        "MODEL 6 PAYMENT OPTIMIZER: SUCCESS"
    )

    print(
        "=" * 70
    )

def _get_payment_options(loader):
    """
    Retrieve request_payment_options.csv from the
    DatasetLoader using the actual Dataset structure.

    This avoids assuming that the Dataset object exposes
    a `payment_options` attribute.
    """

    data = loader.data

    # Most likely names used by the loader
    possible_names = [
        "request_payment_options",
        "payment_option",
        "payment_options_df",
        "request_payment_option",
    ]

    for name in possible_names:

        if hasattr(data, name):

            value = getattr(
                data,
                name,
            )

            if isinstance(
                value,
                pd.DataFrame,
            ):

                return value

    # --------------------------------------------------------
    # If the loader exposes its files dictionary
    # --------------------------------------------------------

    if hasattr(data, "tables"):

        tables = data.tables

        if isinstance(
            tables,
            dict,
        ):

            for name in [
                "request_payment_options.csv",
                "request_payment_options",
            ]:

                if name in tables:

                    return tables[name]

    # --------------------------------------------------------
    # Last safe fallback:
    # read the actual dataset CSV directly.
    # --------------------------------------------------------

    path = "dataset/request_payment_options.csv"

    try:

        return pd.read_csv(path)

    except FileNotFoundError:

        raise RuntimeError(
            "Could not locate request_payment_options.csv. "
            "Expected it at: "
            "dataset/request_payment_options.csv"
        )
# ============================================================
# MAIN TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        "BUY OR WAIT? - "
        "MODEL 6: PAYMENT PLAN OPTIMIZER"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Model 1: Dataset
    # --------------------------------------------------------

    loader = DatasetLoader(
        "dataset"
    )

    loader.load()

    # --------------------------------------------------------
    # First evaluation request
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
        f"Test user:    "
        f"{user_id}"
    )

    print(
        f"Request date: "
        f"{request_date.date()}"
    )

    # --------------------------------------------------------
    # Model 2: Financial State
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
    # Model 3: Evidence
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
    # Model 4: Forecast
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
    # Payment options
    # --------------------------------------------------------

    payment_options = _get_payment_options(loader)

    # --------------------------------------------------------
    # Model 6
    # --------------------------------------------------------

    optimizer = (
        PaymentPlanOptimizer()
    )

    result = optimizer.optimize(
        request=request,
        state=state,
        forecast=forecast,
        payment_options=payment_options,
    )

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    print_optimizer_report(
        result
    )