"""
Model 4: 90-Day Cash-Flow Forecast
===================================

Buy or Wait? - HackerRank Orchestrate

This model projects the user's financial position over the
next 90 days.

Important:
    Historical recurring events are NOT simply discarded.
    Their future occurrences are reconstructed from the
    historical recurrence pattern.

The model:
    - includes future confirmed events
    - includes historical recurring income/expenses by projecting
      their next occurrences
    - ignores cancelled/failed/unrealized cash flows
    - does not count pending credits
    - keeps pending debits reserved through the financial state
    - normalizes all dates to pandas Timestamp
    - produces deterministic daily balances
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from statistics import median
from typing import List, Optional, Dict, Any

import pandas as pd

from .data_loader import DatasetLoader
from .financial_state import FinancialStateBuilder
from .evidence_resolver import EvidenceResolver, ResolvedEvent


# ============================================================
# DATA CLASSES
# ============================================================


@dataclass
class ForecastTransaction:
    """One transaction included in the forecast."""

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
    """Cash position for one day."""

    date: pd.Timestamp

    opening_balance: float

    income: float

    expenses: float

    closing_balance: float

    reserve_requirement: float

    reserve_breached: bool


@dataclass
class CashFlowForecast:
    """Complete 90-day forecast."""

    user_id: str

    start_date: pd.Timestamp
    end_date: pd.Timestamp

    starting_balance: float

    minimum_balance_required: float

    daily_forecast: List[DailyForecast] = field(
        default_factory=list
    )

    transactions: List[ForecastTransaction] = field(
        default_factory=list
    )

    total_projected_income: float = 0.0

    total_projected_expenses: float = 0.0

    minimum_projected_balance: float = 0.0

    minimum_balance_date: Optional[pd.Timestamp] = None

    reserve_breached: bool = False

    reserve_breach_date: Optional[pd.Timestamp] = None

    warnings: List[str] = field(default_factory=list)


# ============================================================
# FORECAST ENGINE
# ============================================================


class CashFlowForecaster:
    """
    Generate a deterministic 90-day cash-flow forecast.

    The key rule here is:

        A historical recurring event is evidence of a future
        recurring event.

    Therefore:

        historical rent
              ↓
        detect recurrence
              ↓
        project next rent
              ↓
        project subsequent rent
              ↓
        include in daily balance
    """

    def __init__(self, horizon_days: int = 90) -> None:

        if horizon_days <= 0:
            raise ValueError(
                "horizon_days must be greater than zero."
            )

        self.horizon_days = int(horizon_days)

    # ========================================================
    # PUBLIC API
    # ========================================================

    def forecast(
        self,
        state,
        resolved_events: List[ResolvedEvent],
        as_of_date,
    ) -> CashFlowForecast:

        start_date = self._normalize_date(as_of_date)

        end_date = (
            start_date
            + timedelta(days=self.horizon_days)
        )

        starting_balance = float(
            state.current_available_balance
        )

        reserve = float(
            state.minimum_balance_to_keep
        )

        transactions = self._build_transactions(
            state=state,
            resolved_events=resolved_events,
            start_date=start_date,
            end_date=end_date,
        )

        daily = self._build_daily_forecast(
            start_date=start_date,
            end_date=end_date,
            starting_balance=starting_balance,
            reserve=reserve,
            transactions=transactions,
        )

        total_income = sum(
            float(t.amount)
            for t in transactions
            if t.direction == "income"
        )

        total_expenses = sum(
            float(t.amount)
            for t in transactions
            if t.direction == "expense"
        )

        if daily:
            minimum_day = min(
                daily,
                key=lambda item: item.closing_balance,
            )
        else:
            minimum_day = DailyForecast(
                date=start_date,
                opening_balance=starting_balance,
                income=0.0,
                expenses=0.0,
                closing_balance=starting_balance,
                reserve_requirement=reserve,
                reserve_breached=(
                    starting_balance < reserve
                ),
            )

        breached_days = [
            day
            for day in daily
            if day.reserve_breached
        ]

        warnings: List[str] = []

        if breached_days:
            warnings.append(
                "Projected balance falls below "
                "the user's required minimum reserve."
            )

        unresolved = [
            event
            for event in resolved_events
            if not getattr(
                event,
                "amount_resolved",
                True,
            )
        ]

        if unresolved:
            warnings.append(
                f"{len(unresolved)} event(s) have "
                "unresolved amounts and were excluded "
                "from the deterministic forecast."
            )

        forecast = CashFlowForecast(
            user_id=str(state.user_id),

            start_date=start_date,
            end_date=end_date,

            starting_balance=starting_balance,
            minimum_balance_required=reserve,

            daily_forecast=daily,
            transactions=transactions,

            total_projected_income=total_income,
            total_projected_expenses=total_expenses,

            minimum_projected_balance=(
                float(minimum_day.closing_balance)
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
    ) -> List[ForecastTransaction]:
        """
        Build all cash-flow transactions inside the forecast.

        This is the important bug fix.

        Non-recurring:
            only future events are included.

        Recurring:
            historical events are used as recurrence evidence,
            then their next occurrences are projected.
        """

        transactions: List[ForecastTransaction] = []

        # ----------------------------------------------------
        # Keep track of transaction dates to avoid duplicates.
        # ----------------------------------------------------

        seen_keys = set()

        # ----------------------------------------------------
        # Events that have already been resolved.
        # ----------------------------------------------------

        resolved_by_id: Dict[str, ResolvedEvent] = {}

        for resolved in resolved_events:

            event = getattr(
                resolved,
                "event",
                None,
            )

            if event is None:
                continue

            event_id = str(
                getattr(
                    event,
                    "event_id",
                    "",
                )
            )

            if event_id:
                resolved_by_id[event_id] = resolved

        # ----------------------------------------------------
        # Helper: get amount.
        # ----------------------------------------------------

        def get_amount(resolved, event):

            value = getattr(
                resolved,
                "resolved_amount",
                None,
            )

            if value is None:
                value = getattr(
                    event,
                    "amount",
                    None,
                )

            if value is None:
                return None

            try:
                value = float(value)
            except (
                TypeError,
                ValueError,
            ):
                return None

            if value <= 0:
                return None

            return value

        # ----------------------------------------------------
        # Helper: event status.
        # ----------------------------------------------------

        def valid_status(resolved, event):

            status = getattr(
                resolved,
                "resolved_status",
                None,
            )

            if not status:
                status = getattr(
                    event,
                    "status",
                    None,
                )

            status = str(
                status or ""
            ).lower().strip()

            if status in {
                "cancelled",
                "canceled",
                "failed",
                "declined",
            }:
                return False

            # Unrealized is never cash.
            if status == "unrealized":
                return False

            return True

        # ----------------------------------------------------
        # Helper: add transaction.
        # ----------------------------------------------------

        def add_transaction(
            event,
            amount,
            event_date,
            resolved,
            recurring=False,
            event_id_override=None,
        ):

            if amount is None:
                return

            if event_date is None:
                return

            try:
                amount = float(amount)
            except (
                TypeError,
                ValueError,
            ):
                return

            if amount <= 0:
                return

            event_date = self._normalize_date(
                event_date
            )

            if (
                event_date < start_date
                or event_date > end_date
            ):
                return

            if not valid_status(
                resolved,
                event,
            ):
                return

            direction = self._determine_direction(
                event
            )

            if direction is None:
                return

            original_id = str(
                getattr(
                    event,
                    "event_id",
                    "event",
                )
            )

            event_id = (
                str(event_id_override)
                if event_id_override
                else original_id
            )

            duplicate_key = (
                event_id,
                event_date,
                round(amount, 8),
                direction,
            )

            if duplicate_key in seen_keys:
                return

            seen_keys.add(
                duplicate_key
            )

            transactions.append(
                ForecastTransaction(

                    event_id=event_id,

                    date=event_date,

                    amount=amount,

                    direction=direction,

                    category=getattr(
                        event,
                        "category",
                        None,
                    ),

                    description=getattr(
                        event,
                        "description",
                        None,
                    ),

                    source=(
                        getattr(
                            resolved,
                            "amount_source",
                            None,
                        )
                        or "financial_event"
                    ),

                    confidence=float(
                        getattr(
                            resolved,
                            "amount_confidence",
                            1.0,
                        )
                        or 1.0
                    ),

                    recurring=bool(
                        recurring
                        or getattr(
                            event,
                            "is_recurring_candidate",
                            False,
                        )
                    ),

                    protected=bool(
                        getattr(
                            event,
                            "is_protected",
                            False,
                        )
                    ),

                    reducible=bool(
                        getattr(
                            event,
                            "is_reducible",
                            False,
                        )
                    ),

                    stoppable=bool(
                        getattr(
                            event,
                            "is_stoppable",
                            False,
                        )
                    ),
                )
            )

        # ====================================================
        # 1. NORMAL FUTURE EVENTS
        # ====================================================

        for resolved in resolved_events:

            event = getattr(
                resolved,
                "event",
                None,
            )

            if event is None:
                continue

            amount = get_amount(
                resolved,
                event,
            )

            if amount is None:
                continue

            event_date = self._event_date(
                event
            )

            if event_date is None:
                continue

            is_recurring = self._is_recurring(
                event,
                state,
            )

            # ------------------------------------------------
            # Normal event.
            # ------------------------------------------------

            if not is_recurring:

                add_transaction(
                    event=event,
                    amount=amount,
                    event_date=event_date,
                    resolved=resolved,
                    recurring=False,
                )

        # ====================================================
        # 2. HISTORICAL RECURRING EVENTS
        # ====================================================

        recurring_events = []

        # Prefer explicitly detected recurring events.
        for collection_name in [
            "recurring_income",
            "recurring_expenses",
        ]:

            collection = getattr(
                state,
                collection_name,
                [],
            )

            if collection:
                recurring_events.extend(
                    collection
                )

        # Fallback to candidate events.
        if not recurring_events:

            recurring_events = [
                event
                for event in getattr(
                    state,
                    "events",
                    [],
                )
                if getattr(
                    event,
                    "is_recurring_candidate",
                    False,
                )
            ]

        # Remove duplicate object references.
        unique_recurring = {}

        for event in recurring_events:

            event_id = str(
                getattr(
                    event,
                    "event_id",
                    "",
                )
            )

            if event_id:
                unique_recurring[
                    event_id
                ] = event

        # ----------------------------------------------------
        # Project each recurrence group.
        # ----------------------------------------------------

        groups = self._group_recurring_events(
            state=state,
            recurring_events=list(
                unique_recurring.values()
            ),
            resolved_by_id=resolved_by_id,
        )

        for group in groups:

            self._project_recurring_group(
                group=group,
                start_date=start_date,
                end_date=end_date,
                add_transaction=add_transaction,
            )

        # ====================================================
        # 3. FUTURE CONFIRMED EVENTS
        # ====================================================

        # These are deliberately handled separately.
        # This catches scheduled salary/payment records even
        # when recurrence detection did not classify them.

        confirmed_collections = [
            "future_confirmed_income",
            "future_confirmed_expenses",
        ]

        for collection_name in confirmed_collections:

            collection = getattr(
                state,
                collection_name,
                [],
            )

            for event in collection:

                event_id = str(
                    getattr(
                        event,
                        "event_id",
                        "",
                    )
                )

                if not event_id:
                    continue

                resolved = resolved_by_id.get(
                    event_id
                )

                if resolved is None:
                    # Create a minimal compatible resolver
                    # only if the event itself has a known amount.
                    amount = getattr(
                        event,
                        "amount",
                        None,
                    )

                    if amount is None:
                        continue

                    class _Resolved:
                        resolved_amount = amount
                        resolved_status = getattr(
                            event,
                            "status",
                            None,
                        )
                        amount_source = (
                            "financial_event"
                        )
                        amount_confidence = 1.0

                    resolved = _Resolved()

                amount = get_amount(
                    resolved,
                    event,
                )

                event_date = self._event_date(
                    event
                )

                if (
                    amount is None
                    or event_date is None
                ):
                    continue

                add_transaction(
                    event=event,
                    amount=amount,
                    event_date=event_date,
                    resolved=resolved,
                    recurring=False,
                )

        # ====================================================
        # SORT
        # ====================================================

        transactions.sort(
            key=lambda transaction: (
                transaction.date,
                transaction.event_id,
            )
        )

        return transactions

    # ========================================================
    # RECURRING GROUPING
    # ========================================================

    def _group_recurring_events(
        self,
        state,
        recurring_events,
        resolved_by_id,
    ):
        """
        Group recurrence evidence by:

            direction
            category
            description

        This prevents unrelated recurring transactions from
        being combined.
        """

        groups: Dict[Any, List[Any]] = {}

        all_events = getattr(
            state,
            "events",
            [],
        )

        recurring_ids = {
            str(
                getattr(
                    event,
                    "event_id",
                    "",
                )
            )
            for event in recurring_events
        }

        # ----------------------------------------------------
        # Include all historical events belonging to a
        # recurrence group.
        # ----------------------------------------------------

        for recurring_event in recurring_events:

            direction = self._determine_direction(
                recurring_event
            )

            if direction is None:
                continue

            category = self._normalize_text(
                getattr(
                    recurring_event,
                    "category",
                    None,
                )
            )

            description = self._normalize_description(
                getattr(
                    recurring_event,
                    "description",
                    None,
                )
            )

            key = (
                direction,
                category,
                description,
            )

            groups.setdefault(
                key,
                [],
            ).append(
                recurring_event
            )

        # ----------------------------------------------------
        # Add other events matching a detected recurring
        # signature. This is important because recurrence
        # detection marks individual events, while forecasting
        # needs the complete historical series.
        # ----------------------------------------------------

        signatures = set(
            groups.keys()
        )

        for event in all_events:

            direction = self._determine_direction(
                event
            )

            if direction is None:
                continue

            category = self._normalize_text(
                getattr(
                    event,
                    "category",
                    None,
                )
            )

            description = self._normalize_description(
                getattr(
                    event,
                    "description",
                    None,
                )
            )

            key = (
                direction,
                category,
                description,
            )

            if key not in signatures:
                continue

            event_id = str(
                getattr(
                    event,
                    "event_id",
                    "",
                )
            )

            if not event_id:
                continue

            # Don't include cancelled/failed/unrealized
            # historical evidence.
            status = str(
                getattr(
                    event,
                    "status",
                    "",
                )
                or ""
            ).lower().strip()

            if status in {
                "cancelled",
                "canceled",
                "failed",
                "declined",
                "unrealized",
            }:
                continue

            if event_id not in {
                str(
                    getattr(
                        item,
                        "event_id",
                        "",
                    )
                )
                for item in groups[key]
            }:
                groups[key].append(
                    event
                )

        return list(
            groups.values()
        )

    # ========================================================
    # PROJECT RECURRING GROUP
    # ========================================================

    def _project_recurring_group(
        self,
        group,
        start_date,
        end_date,
        add_transaction,
    ):
        """
        Project future occurrences from historical recurrence.

        At least two matching intervals are required.

        Supported recurrence periods include:

            weekly
            biweekly
            monthly
            every ~2 months
            quarterly
            half-yearly
            yearly
        """

        if not group:
            return

        # ----------------------------------------------------
        # Sort historical evidence.
        # ----------------------------------------------------

        valid_events = []

        for event in group:

            event_date = self._event_date(
                event
            )

            if event_date is None:
                continue

            amount = getattr(
                event,
                "amount",
                None,
            )

            if amount is None:
                continue

            try:
                amount = float(amount)
            except (
                TypeError,
                ValueError,
            ):
                continue

            if amount <= 0:
                continue

            status = str(
                getattr(
                    event,
                    "status",
                    "",
                )
                or ""
            ).lower().strip()

            if status in {
                "cancelled",
                "canceled",
                "failed",
                "declined",
                "unrealized",
            }:
                continue

            valid_events.append(
                (
                    self._normalize_date(
                        event_date
                    ),
                    event,
                    amount,
                )
            )

        if not valid_events:
            return

        valid_events.sort(
            key=lambda item: item[0]
        )

        # ----------------------------------------------------
        # Remove duplicate dates.
        # ----------------------------------------------------

        by_date = {}

        for event_date, event, amount in valid_events:

            by_date[event_date] = (
                event,
                amount,
            )

        points = sorted(
            [
                (
                    date,
                    event,
                    amount,
                )
                for date, (
                    event,
                    amount,
                ) in by_date.items()
            ],
            key=lambda item: item[0],
        )

        # ----------------------------------------------------
        # Need at least 3 observations to establish recurrence
        # safely.
        # ----------------------------------------------------

        if len(points) < 3:
            return

        dates = [
            item[0]
            for item in points
        ]

        intervals = []

        for first, second in zip(
            dates,
            dates[1:],
        ):

            days = (
                second - first
            ).days

            if days > 0:
                intervals.append(
                    days
                )

        if len(intervals) < 2:
            return

        # ----------------------------------------------------
        # Detect supported recurrence window.
        # ----------------------------------------------------

        recurrence_windows = [
            (5, 9),       # weekly
            (12, 17),     # biweekly
            (25, 35),     # monthly
            (50, 70),     # ~2 monthly
            (80, 100),    # quarterly
            (170, 200),   # half-yearly
            (340, 390),   # yearly
        ]

        supported_intervals = []

        for interval in intervals:

            for low, high in recurrence_windows:

                if low <= interval <= high:

                    supported_intervals.append(
                        interval
                    )

                    break

        # ----------------------------------------------------
        # Need at least two recurrence-like intervals.
        # ----------------------------------------------------

        if len(supported_intervals) < 2:
            return

        interval_days = int(
            round(
                median(
                    supported_intervals
                )
            )
        )

        if interval_days <= 0:
            return

        # ----------------------------------------------------
        # Most recent historical occurrence.
        # ----------------------------------------------------

        last_date, last_event, last_amount = points[-1]

        # ----------------------------------------------------
        # Determine whether the last event itself is already
        # in the forecast. If yes, it will be included by
        # normal future-event handling.
        # ----------------------------------------------------

        next_date = (
            last_date
            + timedelta(
                days=interval_days
            )
        )

        # ----------------------------------------------------
        # Amount strategy:
        #
        # Use the most recent recurring amount because this
        # reflects the latest known recurring obligation.
        # ----------------------------------------------------

        amount = float(
            last_amount
        )

        # ----------------------------------------------------
        # Resolve object for metadata.
        # ----------------------------------------------------

        class _ProjectedResolved:
            resolved_amount = amount
            resolved_status = getattr(
                last_event,
                "status",
                None,
            )
            amount_source = (
                "recurring_history"
            )
            amount_confidence = 0.90

        resolved = _ProjectedResolved()

        # ----------------------------------------------------
        # Project all future occurrences.
        # ----------------------------------------------------

        occurrence_number = 1

        while next_date <= end_date:

            if next_date >= start_date:

                generated_id = (
                    f"{getattr(last_event, 'event_id', 'recurring')}"
                    f"_recurrence_{occurrence_number}"
                )

                add_transaction(
                    event=last_event,
                    amount=amount,
                    event_date=next_date,
                    resolved=resolved,
                    recurring=True,
                    event_id_override=generated_id,
                )

            next_date = (
                next_date
                + timedelta(
                    days=interval_days
                )
            )

            occurrence_number += 1

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
    ) -> List[DailyForecast]:

        dates = pd.date_range(
            start=start_date,
            end=end_date,
            freq="D",
        )

        daily: List[DailyForecast] = []

        balance = float(
            starting_balance
        )

        # Faster lookup than repeatedly scanning the
        # entire transaction list.
        income_by_date: Dict[pd.Timestamp, float] = {}
        expense_by_date: Dict[pd.Timestamp, float] = {}

        for transaction in transactions:

            date = self._normalize_date(
                transaction.date
            )

            if transaction.direction == "income":

                income_by_date[date] = (
                    income_by_date.get(
                        date,
                        0.0,
                    )
                    + float(
                        transaction.amount
                    )
                )

            elif transaction.direction == "expense":

                expense_by_date[date] = (
                    expense_by_date.get(
                        date,
                        0.0,
                    )
                    + float(
                        transaction.amount
                    )
                )

        for current_date in dates:

            current_date = self._normalize_date(
                current_date
            )

            day_income = float(
                income_by_date.get(
                    current_date,
                    0.0,
                )
            )

            day_expenses = float(
                expense_by_date.get(
                    current_date,
                    0.0,
                )
            )

            opening_balance = float(
                balance
            )

            balance = (
                opening_balance
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

                    closing_balance=float(
                        balance
                    ),

                    reserve_requirement=(
                        float(reserve)
                    ),

                    reserve_breached=(
                        breached
                    ),
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
        Determine income/expense from the normalized
        FinancialEvent object.
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
        # Derived FinancialEvent flags.
        # ----------------------------------------------------

        if getattr(
            event,
            "is_income",
            False,
        ):
            return "income"

        if getattr(
            event,
            "is_expense",
            False,
        ):
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
        # Category / description fallback.
        # ----------------------------------------------------

        text_parts = [
            getattr(
                event,
                "category",
                None,
            ),
            getattr(
                event,
                "description",
                None,
            ),
        ]

        text = " ".join(
            str(value)
            for value in text_parts
            if value is not None
        ).lower()

        if text:

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
                "transport",
                "dining",
                "insurance",
                "loan",
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
    # RECURRING DETECTION HELPERS
    # ========================================================

    @staticmethod
    def _is_recurring(
        event,
        state,
    ) -> bool:

        if getattr(
            event,
            "is_recurring_candidate",
            False,
        ):
            return True

        event_id = str(
            getattr(
                event,
                "event_id",
                "",
            )
        )

        for collection_name in [
            "recurring_income",
            "recurring_expenses",
        ]:

            collection = getattr(
                state,
                collection_name,
                [],
            )

            for recurring_event in collection:

                if str(
                    getattr(
                        recurring_event,
                        "event_id",
                        "",
                    )
                ) == event_id:
                    return True

        return False

    # ========================================================
    # EVENT DATE
    # ========================================================

    @staticmethod
    def _event_date(
        event,
    ) -> Optional[pd.Timestamp]:

        # Prefer settlement date for actual cash movement.
        for field_name in [
            "settlement_date",
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

                    return pd.Timestamp(
                        parsed
                    ).normalize()

            except Exception:
                continue

        return None

    # ========================================================
    # DATE NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_date(
        value,
    ) -> pd.Timestamp:

        timestamp = pd.Timestamp(
            value
        )

        return timestamp.normalize()

    # ========================================================
    # TEXT NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_text(
        value,
    ) -> str:

        if value is None:
            return ""

        text = str(value).lower().strip()

        if text in {
            "nan",
            "none",
            "nat",
        }:
            return ""

        return text

    @classmethod
    def _normalize_description(
        cls,
        value,
    ) -> str:

        text = cls._normalize_text(
            value
        )

        # Collapse whitespace.
        text = " ".join(
            text.split()
        )

        return text

    # ========================================================
    # REPORT
    # ========================================================

def print_forecast_report(
    forecast: CashFlowForecast,
) -> None:

    print("\n")
    print("=" * 70)
    print("90-DAY CASH-FLOW FORECAST")
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
        f"Minimum reserve: "
        f"{forecast.minimum_balance_required:,.2f}"
    )

    print(
        f"\nProjected income: "
        f"{forecast.total_projected_income:,.2f}"
    )

    print(
        f"Projected expenses: "
        f"{forecast.total_projected_expenses:,.2f}"
    )

    print(
        f"\nMinimum projected balance: "
        f"{forecast.minimum_projected_balance:,.2f}"
    )

    if forecast.minimum_balance_date:
        print(
            f"Minimum balance date: "
            f"{forecast.minimum_balance_date.date()}"
        )

    print(
        f"\nReserve breached: "
        f"{forecast.reserve_breached}"
    )

    if forecast.reserve_breach_date:
        print(
            f"First breach date: "
            f"{forecast.reserve_breach_date.date()}"
        )

    print(
        f"\nForecast transactions: "
        f"{len(forecast.transactions)}"
    )

    # --------------------------------------------------------
    # Transaction breakdown
    # --------------------------------------------------------

    recurring_income = sum(
        1
        for transaction in forecast.transactions
        if (
            transaction.recurring
            and transaction.direction == "income"
        )
    )

    recurring_expenses = sum(
        1
        for transaction in forecast.transactions
        if (
            transaction.recurring
            and transaction.direction == "expense"
        )
    )

    print(
        f"Recurring income transactions: "
        f"{recurring_income}"
    )

    print(
        f"Recurring expense transactions: "
        f"{recurring_expenses}"
    )

    if forecast.warnings:

        print("\nWarnings:")

        for warning in forecast.warnings:

            print(
                f"  - {warning}"
            )

    print(
        "\nCash-flow checkpoints:"
    )

    # Approximately every 15 days.
    checkpoint_indexes = set(
        [
            0,
            15,
            30,
            45,
            60,
            75,
            len(forecast.daily_forecast) - 1,
        ]
    )

    for index in sorted(
        checkpoint_indexes
    ):

        if (
            index < 0
            or index >= len(
                forecast.daily_forecast
            )
        ):
            continue

        day = forecast.daily_forecast[
            index
        ]

        print(
            f"  {day.date.date()} | "
            f"opening={day.opening_balance:,.2f} | "
            f"income={day.income:,.2f} | "
            f"expenses={day.expenses:,.2f} | "
            f"closing={day.closing_balance:,.2f} | "
            f"breach={day.reserve_breached}"
        )


# ============================================================
# STANDALONE TEST
# ============================================================


def main():

    print("=" * 70)
    print(
        "BUY OR WAIT? - MODEL 4: "
        "90-DAY CASH-FLOW FORECAST"
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
    # Model 2
    # --------------------------------------------------------

    state_builder = FinancialStateBuilder(
        loader
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

    print("\n")
    print("=" * 70)
    print(
        "MODEL 4 CASH-FLOW FORECAST: SUCCESS"
    )
    print("=" * 70)


if __name__ == "__main__":
    main()