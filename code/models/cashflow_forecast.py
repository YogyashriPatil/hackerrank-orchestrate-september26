"""
Model 4: 90-Day Cash-Flow Forecast
===================================

Purpose
-------
Project the user's cash position over the next 90 days.

This model DOES NOT decide whether the user should buy.
It produces the forecast that Model 5 will use.

Input:
    Model 2 FinancialState
    Model 3 ResolvedEvent list

Output:
    Daily projected balances
    Minimum projected balance
    Reserve breach information
    Income/expense totals
    Forecast warnings

Design principles:
    - Never treat missing amounts as zero.
    - Never count cancelled/failed transactions as future cash flow.
    - Respect the user's minimum balance reserve.
    - Separate known future cash flows from uncertain ones.
    - Keep the forecast auditable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional, Dict, Any

import pandas as pd

from .data_loader import DatasetLoader
from .financial_state import (
    FinancialStateBuilder,
)
from .evidence_resolver import (
    EvidenceResolver,
    ResolvedEvent,
)


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class ForecastTransaction:
    """
    One transaction included in the forecast.
    """

    event_id: str

    date: pd.Timestamp

    amount: float

    direction: str
    # income / expense

    category: Optional[str]

    description: Optional[str]

    source: str

    confidence: float

    recurring: bool = False

    protected: bool = False

    reducible: bool = False

    stoppable: bool = False


@dataclass
class DailyForecast:
    """
    Cash position for one day.
    """

    date: pd.Timestamp

    opening_balance: float

    income: float

    expenses: float

    closing_balance: float

    reserve_requirement: float

    reserve_breached: bool


@dataclass
class CashFlowForecast:
    """
    Complete 90-day forecast.
    """

    user_id: str

    start_date: pd.Timestamp

    end_date: pd.Timestamp

    starting_balance: float

    minimum_balance_required: float

    daily_forecast: List[
        DailyForecast
    ] = field(default_factory=list)

    transactions: List[
        ForecastTransaction
    ] = field(default_factory=list)

    total_projected_income: float = 0.0

    total_projected_expenses: float = 0.0

    minimum_projected_balance: float = 0.0

    minimum_balance_date: Optional[
        pd.Timestamp
    ] = None

    reserve_breached: bool = False

    reserve_breach_date: Optional[
        pd.Timestamp
    ] = None

    warnings: List[str] = field(
        default_factory=list
    )


# ============================================================
# FORECAST ENGINE
# ============================================================

class CashFlowForecaster:
    """
    Generate a 90-day cash-flow forecast.
    """

    def __init__(
        self,
        horizon_days: int = 90,
    ) -> None:

        if horizon_days <= 0:

            raise ValueError(
                "horizon_days must be greater than zero."
            )

        self.horizon_days = horizon_days

    # ========================================================
    # PUBLIC
    # ========================================================

    def forecast(
        self,
        state,
        resolved_events: List[
            ResolvedEvent
        ],
        as_of_date,
    ) -> CashFlowForecast:

        start_date = pd.Timestamp(
            as_of_date
        ).normalize()

        end_date = (
            start_date
            + timedelta(
                days=self.horizon_days
            )
        )

        starting_balance = float(
            state.current_available_balance
        )

        reserve = float(
            state.minimum_balance_to_keep
        )

        transactions = (
            self._build_transactions(
                state=state,
                resolved_events=resolved_events,
                start_date=start_date,
                end_date=end_date,
            )
        )

        daily = (
            self._build_daily_forecast(
                start_date=start_date,
                end_date=end_date,
                starting_balance=starting_balance,
                reserve=reserve,
                transactions=transactions,
            )
        )

        total_income = sum(
            transaction.amount
            for transaction in transactions
            if transaction.direction
            == "income"
        )

        total_expenses = sum(
            transaction.amount
            for transaction in transactions
            if transaction.direction
            == "expense"
        )

        minimum_day = min(
            daily,
            key=lambda item:
            item.closing_balance,
        )

        breached_days = [
            item
            for item in daily
            if item.reserve_breached
        ]

        warnings = []

        if breached_days:

            warnings.append(
                "Projected balance falls below "
                "the user's required minimum reserve."
            )

        unresolved = [
            event
            for event in resolved_events
            if not event.amount_resolved
        ]

        if unresolved:

            warnings.append(
                f"{len(unresolved)} event(s) have "
                "unresolved amounts and were excluded "
                "from the deterministic forecast."
            )

        forecast = CashFlowForecast(
            user_id=state.user_id,
            start_date=start_date,
            end_date=end_date,
            starting_balance=starting_balance,
            minimum_balance_required=reserve,
            daily_forecast=daily,
            transactions=transactions,
            total_projected_income=total_income,
            total_projected_expenses=total_expenses,
            minimum_projected_balance=(
                minimum_day.closing_balance
            ),
            minimum_balance_date=(
                minimum_day.date
            ),
            reserve_breached=bool(
                breached_days
            ),
            reserve_breach_date=(
                breached_days[0].date
                if breached_days
                else None
            ),
            warnings=warnings,
        )

        return forecast

    # ========================================================
    # BUILD TRANSACTIONS
    # ========================================================

    def _build_transactions(
        self,
        state,
        resolved_events,
        start_date,
        end_date,
    ) -> List[
        ForecastTransaction
    ]:

        transactions = []

        for resolved in resolved_events:

            event = resolved.event

            # ------------------------------------------------
            # Amount must be known.
            # ------------------------------------------------

            if (
                resolved.resolved_amount
                is None
            ):
                continue

            amount = float(
                resolved.resolved_amount
            )

            if amount <= 0:

                continue

            # ------------------------------------------------
            # Determine date.
            # ------------------------------------------------

            event_date = self._event_date(
                event
            )

            if event_date is None:

                continue

            event_date = pd.Timestamp(
                event_date
            ).normalize()

            # ------------------------------------------------
            # Only future events enter the forecast.
            # ------------------------------------------------

            if event_date < start_date:

                continue

            if event_date > end_date:

                continue

            # ------------------------------------------------
            # Ignore transactions that definitely
            # won't happen.
            # ------------------------------------------------

            status = (
                str(
                    resolved.resolved_status
                    or event.status
                    or ""
                )
                .lower()
                .strip()
            )

            if status in {
                "cancelled",
                "canceled",
                "failed",
                "declined",
            }:

                continue

            # ------------------------------------------------
            # Determine direction.
            # ------------------------------------------------

            direction = (
                self._determine_direction(
                    event
                )
            )

            if direction is None:

                continue

            transaction = (
                ForecastTransaction(
                    event_id=str(
                        event.event_id
                    ),
                    date=event_date,
                    amount=amount,
                    direction=direction,
                    category=(
                        getattr(
                            event,
                            "category",
                            None,
                        )
                    ),
                    description=(
                        getattr(
                            event,
                            "description",
                            None,
                        )
                    ),
                    source=(
                        resolved.amount_source
                        or "financial_event"
                    ),
                    confidence=float(
                        resolved.amount_confidence
                    ),
                    recurring=bool(
                        getattr(
                            event,
                            "recurring",
                            False,
                        )
                    ),
                    protected=bool(
                        getattr(
                            event,
                            "protected",
                            False,
                        )
                    ),
                    reducible=bool(
                        getattr(
                            event,
                            "reducible",
                            False,
                        )
                    ),
                    stoppable=bool(
                        getattr(
                            event,
                            "stoppable",
                            False,
                        )
                    ),
                )
            )

            transactions.append(
                transaction
            )

        return transactions

    # ========================================================
    # DAILY FORECAST
    # ========================================================

    def _build_daily_forecast(
        self,
        start_date,
        end_date,
        starting_balance,
        reserve,
        transactions,
    ):

        dates = pd.date_range(
            start=start_date,
            end=end_date,
            freq="D",
        )

        daily = []

        balance = float(
            starting_balance
        )

        for current_date in dates:

            day_income = sum(
                transaction.amount
                for transaction in transactions
                if transaction.date
                == current_date
                and transaction.direction
                == "income"
            )

            day_expenses = sum(
                transaction.amount
                for transaction in transactions
                if transaction.date
                == current_date
                and transaction.direction
                == "expense"
            )

            opening_balance = balance

            balance = (
                balance
                + day_income
                - day_expenses
            )

            breached = (
                balance < reserve
            )

            daily.append(
                DailyForecast(
                    date=current_date,
                    opening_balance=(
                        opening_balance
                    ),
                    income=day_income,
                    expenses=day_expenses,
                    closing_balance=balance,
                    reserve_requirement=(
                        reserve
                    ),
                    reserve_breached=breached,
                )
            )

        return daily

    # ========================================================
    # DIRECTION
    # ========================================================

    @staticmethod
    def _determine_direction(
        event,
    ) -> Optional[str]:
        """
        Determine whether an event is income or expense.

        We check common fields without assuming that every
        dataset row has the same schema.
        """

        # ----------------------------------------------------
        # Explicit direction.
        # ----------------------------------------------------

        for field_name in [
            "direction",
            "flow_type",
            "transaction_type",
        ]:

            value = getattr(
                event,
                field_name,
                None,
            )

            if value:

                normalized = (
                    str(value)
                    .lower()
                    .strip()
                )

                if normalized in {
                    "income",
                    "credit",
                    "inflow",
                    "deposit",
                    "salary",
                    "revenue",
                }:

                    return "income"

                if normalized in {
                    "expense",
                    "debit",
                    "outflow",
                    "withdrawal",
                    "payment",
                    "purchase",
                }:

                    return "expense"

        # ----------------------------------------------------
        # Event type.
        # ----------------------------------------------------

        event_type = getattr(
            event,
            "event_type",
            None,
        )

        if event_type:

            normalized = (
                str(event_type)
                .lower()
                .strip()
            )

            if any(
                word in normalized
                for word in [
                    "income",
                    "salary",
                    "credit",
                    "deposit",
                    "refund",
                ]
            ):

                return "income"

            if any(
                word in normalized
                for word in [
                    "expense",
                    "payment",
                    "purchase",
                    "debit",
                    "withdrawal",
                    "bill",
                ]
            ):

                return "expense"

        # ----------------------------------------------------
        # Description fallback.
        # ----------------------------------------------------

        description = getattr(
            event,
            "description",
            None,
        )

        if description:

            text = (
                str(description)
                .lower()
            )

            income_words = [
                "salary",
                "income",
                "bonus",
                "refund",
                "cashback",
                "deposit",
                "received",
            ]

            expense_words = [
                "rent",
                "bill",
                "payment",
                "purchase",
                "subscription",
                "expense",
                "groceries",
                "utilities",
            ]

            if any(
                word in text
                for word in income_words
            ):

                return "income"

            if any(
                word in text
                for word in expense_words
            ):

                return "expense"

        return None

    # ========================================================
    # EVENT DATE
    # ========================================================

    @staticmethod
    def _event_date(
        event,
    ) -> Optional[pd.Timestamp]:

        for field_name in [
            "scheduled_date",
            "event_date",
            "transaction_date",
            "date",
            "due_date",
        ]:

            value = getattr(
                event,
                field_name,
                None,
            )

            if value is None:
                continue

            try:

                parsed = pd.to_datetime(
                    value,
                    errors="coerce",
                )

                if pd.notna(parsed):

                    return parsed

            except Exception:

                continue

        return None


# ============================================================
# REPORT
# ============================================================

def print_forecast_report(
    forecast: CashFlowForecast,
) -> None:

    print("\n")
    print("=" * 70)
    print(
        "90-DAY CASH-FLOW FORECAST"
    )
    print("=" * 70)

    print(
        f"\nUser: "
        f"{forecast.user_id}"
    )

    print(
        f"Forecast start: "
        f"{forecast.start_date.date()}"
    )

    print(
        f"Forecast end:   "
        f"{forecast.end_date.date()}"
    )

    print(
        f"\nStarting balance: "
        f"{forecast.starting_balance:,.2f}"
    )

    print(
        f"Minimum reserve:  "
        f"{forecast.minimum_balance_required:,.2f}"
    )

    print(
        f"\nProjected income:  "
        f"{forecast.total_projected_income:,.2f}"
    )

    print(
        f"Projected expenses:"
        f" {forecast.total_projected_expenses:,.2f}"
    )

    print(
        f"\nMinimum projected balance:"
        f" {forecast.minimum_projected_balance:,.2f}"
    )

    if forecast.minimum_balance_date:

        print(
            f"Minimum balance date:"
            f" {forecast.minimum_balance_date.date()}"
        )

    print(
        f"\nReserve breached: "
        f"{forecast.reserve_breached}"
    )

    if forecast.reserve_breach_date:

        print(
            f"First breach date:"
            f" {forecast.reserve_breach_date.date()}"
        )

    print(
        f"\nForecast transactions:"
        f" {len(forecast.transactions)}"
    )

    if forecast.warnings:

        print(
            "\nWarnings:"
        )

        for warning in forecast.warnings:

            print(
                f"  - {warning}"
            )

    print(
        "\nCash-flow checkpoints:"
    )

    # Show approximately every 15 days.
    checkpoints = forecast.daily_forecast[
        ::15
    ]

    for day in checkpoints:

        print(
            f"  {day.date.date()} | "
            f"Income: {day.income:,.2f} | "
            f"Expense: {day.expenses:,.2f} | "
            f"Balance: {day.closing_balance:,.2f}"
        )

    print(
        "\n" + "=" * 70
    )

    print(
        "MODEL 4 CASH-FLOW FORECAST: SUCCESS"
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
        "MODEL 4: 90-DAY CASH-FLOW FORECAST"
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
    # Select test request
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
    # Report
    # --------------------------------------------------------

    print_forecast_report(
        forecast
    )