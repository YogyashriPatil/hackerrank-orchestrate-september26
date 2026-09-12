# Current available balance
# Minimum balance
# Recurring income
# Recurring expenses
# Essential expenses
# Flexible expenses
# Pending debits
# Pending credits
# Scheduled payments
# Settled transactions
# Failed transactions
# Cancelled transactions
# Unrealized investments
"""
Model 2: Financial State Reconstruction
=======================================

HackerRank Orchestrate - Buy or Wait?

This model transforms raw dataset records into a structured
financial state for one user.

Responsibilities
----------------
1. Read the user's financial profile.
2. Classify financial events by cash-flow status.
3. Separate income and expenses.
4. Identify recurring events.
5. Identify flexible/protected expenses.
6. Reserve pending debits.
7. Ignore pending credits.
8. Ignore failed/cancelled transactions.
9. Ignore unrealized investment value as available cash.
10. Detect confirmed future income/payments.
11. Provide a structured state to the forecasting model.

This model DOES NOT:
    - calculate the final purchase decision
    - generate payment plans
    - calculate amount_safe_to_pay
    - rank payment options
    - modify expenses

Those responsibilities belong to later models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

# from .data_loader import DatasetLoader
from code.models.data_loader import DatasetLoader
# from models.data_loader import DatasetLoader
# ============================================================
# CONSTANTS
# ============================================================

SETTLED_STATUSES = {
    "settled",
}

PENDING_STATUSES = {
    "pending",
}

SCHEDULED_STATUSES = {
    "scheduled",
}

FAILED_STATUSES = {
    "failed",
}

CANCELLED_STATUSES = {
    "cancelled",
    "canceled",
}

UNREALIZED_STATUSES = {
    "unrealized",
}


# ============================================================
# EVENT REPRESENTATION
# ============================================================

@dataclass
class FinancialEvent:
    """
    Clean representation of one financial event.
    """

    event_id: str
    user_id: str

    event_type: Optional[str]
    description: Optional[str]
    category: Optional[str]

    direction: Optional[str]

    amount: Optional[float]
    currency: Optional[str]

    event_date: Optional[pd.Timestamp]
    settlement_date: Optional[pd.Timestamp]

    status: Optional[str]
    linked_event_id: Optional[str]

    flexibility: Optional[str]
    minimum_allowed_amount: Optional[float]

    # Derived attributes.
    is_income: bool = False
    is_expense: bool = False
    is_recurring_candidate: bool = False
    counts_as_cash: bool = False
    reserves_cash: bool = False
    is_future: bool = False
    is_flexible: bool = False
    is_protected: bool = False
    is_reducible: bool = False
    is_stoppable: bool = False


# ============================================================
# FINANCIAL STATE
# ============================================================

@dataclass
class FinancialState:
    """
    Structured financial state for one user.
    """

    user_id: str

    home_currency: Optional[str]

    current_available_balance: float

    minimum_balance_to_keep: float

    financial_priorities: List[str]

    protected_categories: List[str]

    reducible_categories: List[str]

    stoppable_categories: List[str]

    accepted_payment_methods: List[str]

    max_installment_months: Optional[int]

    # All processed events.
    events: List[FinancialEvent] = field(
        default_factory=list
    )

    # Categorized events.
    settled_income: List[FinancialEvent] = field(
        default_factory=list
    )

    settled_expenses: List[FinancialEvent] = field(
        default_factory=list
    )

    pending_debits: List[FinancialEvent] = field(
        default_factory=list
    )

    pending_credits: List[FinancialEvent] = field(
        default_factory=list
    )

    scheduled_income: List[FinancialEvent] = field(
        default_factory=list
    )

    scheduled_expenses: List[FinancialEvent] = field(
        default_factory=list
    )

    failed_events: List[FinancialEvent] = field(
        default_factory=list
    )

    cancelled_events: List[FinancialEvent] = field(
        default_factory=list
    )

    unrealized_events: List[FinancialEvent] = field(
        default_factory=list
    )

    recurring_income: List[FinancialEvent] = field(
        default_factory=list
    )

    recurring_expenses: List[FinancialEvent] = field(
        default_factory=list
    )

    flexible_expenses: List[FinancialEvent] = field(
        default_factory=list
    )

    protected_expenses: List[FinancialEvent] = field(
        default_factory=list
    )

    reducible_expenses: List[FinancialEvent] = field(
        default_factory=list
    )

    stoppable_expenses: List[FinancialEvent] = field(
        default_factory=list
    )

    future_confirmed_income: List[FinancialEvent] = field(
        default_factory=list
    )

    future_confirmed_expenses: List[FinancialEvent] = field(
        default_factory=list
    )

    # Diagnostic information.
    duplicate_event_ids: List[str] = field(
        default_factory=list
    )

    warnings: List[str] = field(
        default_factory=list
    )

    def summary(self) -> Dict[str, Any]:
        """
        Return a compact summary useful for debugging and
        later models.
        """

        return {
            "user_id": self.user_id,
            "home_currency": self.home_currency,
            "current_available_balance": (
                self.current_available_balance
            ),
            "minimum_balance_to_keep": (
                self.minimum_balance_to_keep
            ),
            "financial_priorities": (
                self.financial_priorities
            ),
            "protected_categories": (
                self.protected_categories
            ),
            "reducible_categories": (
                self.reducible_categories
            ),
            "stoppable_categories": (
                self.stoppable_categories
            ),
            "accepted_payment_methods": (
                self.accepted_payment_methods
            ),
            "max_installment_months": (
                self.max_installment_months
            ),
            "total_events": len(self.events),
            "settled_income": len(
                self.settled_income
            ),
            "settled_expenses": len(
                self.settled_expenses
            ),
            "pending_debits": len(
                self.pending_debits
            ),
            "pending_credits": len(
                self.pending_credits
            ),
            "scheduled_income": len(
                self.scheduled_income
            ),
            "scheduled_expenses": len(
                self.scheduled_expenses
            ),
            "failed_events": len(
                self.failed_events
            ),
            "cancelled_events": len(
                self.cancelled_events
            ),
            "unrealized_events": len(
                self.unrealized_events
            ),
            "recurring_income": len(
                self.recurring_income
            ),
            "recurring_expenses": len(
                self.recurring_expenses
            ),
            "flexible_expenses": len(
                self.flexible_expenses
            ),
            "protected_expenses": len(
                self.protected_expenses
            ),
            "reducible_expenses": len(
                self.reducible_expenses
            ),
            "stoppable_expenses": len(
                self.stoppable_expenses
            ),
            "future_confirmed_income": len(
                self.future_confirmed_income
            ),
            "future_confirmed_expenses": len(
                self.future_confirmed_expenses
            ),
            "duplicate_event_ids": (
                self.duplicate_event_ids
            ),
            "warnings": self.warnings,
        }


# ============================================================
# FINANCIAL STATE BUILDER
# ============================================================

class FinancialStateBuilder:
    """
    Builds a FinancialState from DatasetLoader.

    Example
    -------
        loader = DatasetLoader("dataset")
        loader.load()

        builder = FinancialStateBuilder(loader)

        state = builder.build(
            "user_26",
            pd.Timestamp("2025-08-03")
        )
    """

    def __init__(
        self,
        loader: DatasetLoader,
    ) -> None:

        self.loader = loader

        if self.loader.data is None:
            raise RuntimeError(
                "DatasetLoader must be loaded before "
                "FinancialStateBuilder can be used."
            )

    # ========================================================
    # PUBLIC API
    # ========================================================

    def build(
        self,
        user_id: str,
        as_of_date: Optional[pd.Timestamp] = None,
    ) -> FinancialState:
        """
        Build a structured financial state for one user.

        Parameters
        ----------
        user_id:
            User whose state should be reconstructed.

        as_of_date:
            Date at which the financial state is evaluated.

        Returns
        -------
        FinancialState
        """

        user_id = str(user_id)

        profile = self.loader.profile_for_user(
            user_id
        )

        if profile is None:
            raise KeyError(
                f"No financial profile found for "
                f"user_id={user_id}"
            )

        events_df = self.loader.events_for_user(
            user_id
        )

        # ----------------------------------------------------
        # Profile
        # ----------------------------------------------------

        home_currency = self._string(
            profile.get("home_currency")
        )

        current_balance = self._number(
            profile.get(
                "current_available_balance"
            )
        )

        minimum_balance = self._number(
            profile.get(
                "minimum_balance_to_keep"
            )
        )

        priorities = self._split_list(
            profile.get("financial_priorities")
        )

        protected_categories = self._split_list(
            profile.get(
                "expense_categories_to_protect"
            )
        )

        reducible_categories = self._split_list(
            profile.get(
                "expense_categories_user_is_willing_to_reduce"
            )
        )

        stoppable_categories = self._split_list(
            profile.get(
                "expense_categories_user_is_willing_to_stop"
            )
        )

        accepted_payment_methods = self._split_list(
            profile.get(
                "payment_methods_user_will_consider"
            )
        )

        max_installment_months = self._integer(
            profile.get(
                "max_installment_months"
            )
        )

        state = FinancialState(
            user_id=user_id,
            home_currency=home_currency,
            current_available_balance=(
                current_balance or 0.0
            ),
            minimum_balance_to_keep=(
                minimum_balance or 0.0
            ),
            financial_priorities=priorities,
            protected_categories=(
                protected_categories
            ),
            reducible_categories=(
                reducible_categories
            ),
            stoppable_categories=(
                stoppable_categories
            ),
            accepted_payment_methods=(
                accepted_payment_methods
            ),
            max_installment_months=(
                max_installment_months
            ),
        )

        # ----------------------------------------------------
        # Convert raw rows
        # ----------------------------------------------------

        raw_events = []

        for _, row in events_df.iterrows():

            event = self._convert_event(
                row=row,
                state=state,
                as_of_date=as_of_date,
            )

            if event is not None:
                raw_events.append(event)

        state.events = raw_events

        # ----------------------------------------------------
        # Detect duplicates
        # ----------------------------------------------------

        self._detect_duplicates(state)

        # ----------------------------------------------------
        # Categorize events
        # ----------------------------------------------------

        for event in state.events:
            self._classify_event(
                state=state,
                event=event,
                as_of_date=as_of_date,
            )

        # ----------------------------------------------------
        # Detect recurrence
        # ----------------------------------------------------

        self._detect_recurring_events(
            state=state
        )

        # ----------------------------------------------------
        # Sort all lists chronologically
        # ----------------------------------------------------

        self._sort_state_lists(state)

        return state

    # ========================================================
    # EVENT CONVERSION
    # ========================================================

    def _convert_event(
        self,
        row: pd.Series,
        state: FinancialState,
        as_of_date: Optional[pd.Timestamp],
    ) -> Optional[FinancialEvent]:
        """
        Convert one DataFrame row into FinancialEvent.
        """

        event_id = self._string(
            row.get("event_id")
        )

        if not event_id:
            state.warnings.append(
                "Financial event without event_id "
                "was ignored."
            )

            return None

        user_id = self._string(
            row.get("user_id")
        )

        if not user_id:
            user_id = state.user_id

        amount = self._number(
            row.get("amount")
        )

        event_date = self._date(
            row.get("event_date")
        )

        settlement_date = self._date(
            row.get("settlement_date")
        )

        event = FinancialEvent(
            event_id=event_id,
            user_id=user_id,
            event_type=self._string(
                row.get("event_type")
            ),
            description=self._string(
                row.get("description")
            ),
            category=self._string(
                row.get("category")
            ),
            direction=self._string(
                row.get("direction")
            ),
            amount=amount,
            currency=self._string(
                row.get("currency")
            ),
            event_date=event_date,
            settlement_date=settlement_date,
            status=self._normalize_status(
                row.get("status")
            ),
            linked_event_id=self._string(
                row.get("linked_event_id")
            ),
            flexibility=self._string(
                row.get("flexibility")
            ),
            minimum_allowed_amount=self._number(
                row.get(
                    "minimum_allowed_amount"
                )
            ),
        )

        # ----------------------------------------------------
        # Basic derived properties
        # ----------------------------------------------------

        direction = (
            event.direction.lower()
            if event.direction
            else ""
        )

        event.is_income = (
            direction == "credit"
            or self._looks_like_income(event)
        )

        event.is_expense = (
            direction == "debit"
            or self._looks_like_expense(event)
        )

        event.is_flexible = (
            self._normalize_text(
                event.flexibility
            ) == "flexible"
        )

        event.is_protected = (
            self._normalize_text(
                event.category
            )
            in {
                self._normalize_text(x)
                for x in state.protected_categories
            }
        )

        event.is_reducible = (
            self._normalize_text(
                event.category
            )
            in {
                self._normalize_text(x)
                for x in state.reducible_categories
            }
        )

        event.is_stoppable = (
            self._normalize_text(
                event.category
            )
            in {
                self._normalize_text(x)
                for x in state.stoppable_categories
            }
        )

        if (
            as_of_date is not None
            and event.event_date is not None
        ):
            event.is_future = (
                event.event_date
                > as_of_date
            )

        return event

    # ========================================================
    # EVENT CLASSIFICATION
    # ========================================================

    def _classify_event(
        self,
        state: FinancialState,
        event: FinancialEvent,
        as_of_date: Optional[pd.Timestamp],
    ) -> None:
        """
        Apply challenge cash-state rules.
        """

        status = (
            event.status or ""
        ).lower()

        # ----------------------------------------------------
        # Cancelled
        # ----------------------------------------------------

        if status in CANCELLED_STATUSES:

            state.cancelled_events.append(
                event
            )

            return

        # ----------------------------------------------------
        # Failed
        # ----------------------------------------------------

        if status in FAILED_STATUSES:

            state.failed_events.append(
                event
            )

            return

        # ----------------------------------------------------
        # Unrealized
        # ----------------------------------------------------

        if status in UNREALIZED_STATUSES:

            state.unrealized_events.append(
                event
            )

            # Unrealized investment value is not cash.
            event.counts_as_cash = False
            event.reserves_cash = False

            return

        # ----------------------------------------------------
        # Pending
        # ----------------------------------------------------

        if status in PENDING_STATUSES:

            if event.is_expense:

                # Pending debit must be reserved.
                state.pending_debits.append(
                    event
                )

                event.counts_as_cash = False
                event.reserves_cash = True

            elif event.is_income:

                # Pending credits are NOT available cash.
                state.pending_credits.append(
                    event
                )

                event.counts_as_cash = False
                event.reserves_cash = False

            return

        # ----------------------------------------------------
        # Scheduled
        # ----------------------------------------------------

        if status in SCHEDULED_STATUSES:

            if event.is_expense:

                state.scheduled_expenses.append(
                    event
                )

                # Future scheduled debit must be
                # considered by forecasting.
                event.counts_as_cash = False
                event.reserves_cash = True

            elif event.is_income:

                state.scheduled_income.append(
                    event
                )

                # Confirmed scheduled income can be
                # used by the future forecast when
                # its settlement is confirmed.
                event.counts_as_cash = False
                event.reserves_cash = False

            return

        # ----------------------------------------------------
        # Settled
        # ----------------------------------------------------

        if status in SETTLED_STATUSES:

            if event.is_income:

                state.settled_income.append(
                    event
                )

                event.counts_as_cash = True

            elif event.is_expense:

                state.settled_expenses.append(
                    event
                )

                event.counts_as_cash = True

            return

        # ----------------------------------------------------
        # Unknown status
        # ----------------------------------------------------

        state.warnings.append(
            f"Event {event.event_id} has "
            f"unrecognized status "
            f"'{event.status}'."
        )

    # ========================================================
    # RECURRING DETECTION
    # ========================================================

    def _detect_recurring_events(
        self,
        state: FinancialState,
    ) -> None:
        """
        Detect recurring income and expense patterns.

        This is intentionally conservative.

        We only mark an event as a recurring candidate when
        enough historical evidence exists.

        We do NOT assume that every repeated category is
        recurring.
        """

        income_groups = self._group_candidate_events(
            state.settled_income
        )

        expense_groups = self._group_candidate_events(
            state.settled_expenses
        )

        # ----------------------------------------------------
        # Income
        # ----------------------------------------------------

        for group in income_groups.values():

            if self._is_recurring_group(group):

                for event in group:
                    event.is_recurring_candidate = True

                    if event not in state.recurring_income:
                        state.recurring_income.append(
                            event
                        )

        # ----------------------------------------------------
        # Expenses
        # ----------------------------------------------------

        for group in expense_groups.values():

            if self._is_recurring_group(group):

                for event in group:
                    event.is_recurring_candidate = True

                    if event not in state.recurring_expenses:
                        state.recurring_expenses.append(
                            event
                        )

                    if event.is_flexible:
                        if (
                            event
                            not in state.flexible_expenses
                        ):
                            state.flexible_expenses.append(
                                event
                            )

                    if event.is_protected:
                        if (
                            event
                            not in state.protected_expenses
                        ):
                            state.protected_expenses.append(
                                event
                            )

                    if event.is_reducible:
                        if (
                            event
                            not in state.reducible_expenses
                        ):
                            state.reducible_expenses.append(
                                event
                            )

                    if event.is_stoppable:
                        if (
                            event
                            not in state.stoppable_expenses
                        ):
                            state.stoppable_expenses.append(
                                event
                            )

    def _group_candidate_events(
        self,
        events: List[FinancialEvent],
    ) -> Dict[str, List[FinancialEvent]]:
        """
        Group events using conservative recurrence keys.

        The key uses:
            category
            direction
            approximate amount
            description

        This prevents unrelated expenses from being
        incorrectly merged.
        """

        groups: Dict[
            str,
            List[FinancialEvent]
        ] = {}

        for event in events:

            if event.event_date is None:
                continue

            if event.amount is None:
                continue

            category = (
                self._normalize_text(
                    event.category
                )
                or "unknown"
            )

            direction = (
                self._normalize_text(
                    event.direction
                )
                or "unknown"
            )

            description = (
                self._normalize_text(
                    event.description
                )
                or ""
            )

            # Use rounded amount bucket.
            amount_bucket = round(
                float(event.amount),
                2,
            )

            key = (
                f"{category}|"
                f"{direction}|"
                f"{amount_bucket}|"
                f"{description}"
            )

            groups.setdefault(
                key,
                []
            ).append(event)

        return groups

    def _is_recurring_group(
        self,
        events: List[FinancialEvent],
    ) -> bool:
        """
        Determine whether a group has sufficient evidence
        of recurrence.

        Minimum:
            3 observations

        And at least two intervals should be reasonably
        similar.

        Typical monthly/weekly recurrence is accepted.

        This is deliberately conservative.
        """

        if len(events) < 3:
            return False

        dates = sorted(
            [
                event.event_date
                for event in events
                if event.event_date is not None
            ]
        )

        if len(dates) < 3:
            return False

        intervals = []

        for first, second in zip(
            dates,
            dates[1:],
        ):
            days = (
                second - first
            ).days

            if days > 0:
                intervals.append(days)

        if len(intervals) < 2:
            return False

        # Common recurrence windows.
        recurrence_windows = [
            (5, 9),       # weekly-ish
            (12, 17),     # biweekly-ish
            (25, 35),     # monthly-ish
            (50, 70),     # ~2 monthly
            (80, 100),    # ~quarterly
            (170, 200),   # ~half-year
            (340, 390),   # annual
        ]

        matching = 0

        for interval in intervals:

            for low, high in recurrence_windows:

                if low <= interval <= high:
                    matching += 1
                    break

        # Require at least two recurrence-like intervals.
        return matching >= 2

    # ========================================================
    # DUPLICATE DETECTION
    # ========================================================

    def _detect_duplicates(
        self,
        state: FinancialState,
    ) -> None:
        """
        Detect repeated event IDs.

        We do not delete duplicates here because resolving
        transaction lifecycle duplicates requires more context.

        Later transaction resolution can use this information.
        """

        seen = set()

        duplicates = set()

        for event in state.events:

            if event.event_id in seen:
                duplicates.add(
                    event.event_id
                )

            seen.add(
                event.event_id
            )

        state.duplicate_event_ids = sorted(
            duplicates
        )

        if duplicates:
            state.warnings.append(
                "Duplicate event IDs detected: "
                + ", ".join(
                    sorted(duplicates)
                )
            )

    # ========================================================
    # FUTURE EVENTS
    # ========================================================

    def get_future_confirmed_events(
        self,
        state: FinancialState,
        as_of_date: pd.Timestamp,
    ) -> None:
        """
        Populate future confirmed income/expense lists.

        This method is separate from build() so later models can
        explicitly call it after determining the relevant request
        date.
        """

        state.future_confirmed_income.clear()
        state.future_confirmed_expenses.clear()

        for event in state.events:

            event_date = (
                event.settlement_date
                or event.event_date
            )

            if event_date is None:
                continue

            if event_date <= as_of_date:
                continue

            # Confirmed future income.
            if (
                event.is_income
                and event.status
                in {
                    "scheduled",
                    "settled",
                }
            ):
                state.future_confirmed_income.append(
                    event
                )

            # Confirmed future expense.
            elif (
                event.is_expense
                and event.status
                == "scheduled"
            ):
                state.future_confirmed_expenses.append(
                    event
                )

    # ========================================================
    # EXPENSE CHANGE ELIGIBILITY
    # ========================================================

    def can_change_expense(
        self,
        state: FinancialState,
        event: FinancialEvent,
        action: str,
    ) -> bool:
        """
        Determine whether a recurring expense can be stopped
        or reduced.

        Challenge rule:
            only non-protected flexible expenses may be changed.
        """

        if not event.is_expense:
            return False

        if not event.is_recurring_candidate:
            return False

        if not event.is_flexible:
            return False

        if event.is_protected:
            return False

        action = self._normalize_text(
            action
        )

        if action == "stop":
            return event.is_stoppable

        if action == "reduce":
            return event.is_reducible

        return False

    # ========================================================
    # SORTING
    # ========================================================

    def _sort_state_lists(
        self,
        state: FinancialState,
    ) -> None:
        """
        Sort events by date.
        """

        def event_key(
            event: FinancialEvent,
        ):
            return (
                event.event_date
                if event.event_date is not None
                else pd.Timestamp.max
            )

        list_names = [
            "events",
            "settled_income",
            "settled_expenses",
            "pending_debits",
            "pending_credits",
            "scheduled_income",
            "scheduled_expenses",
            "failed_events",
            "cancelled_events",
            "unrealized_events",
            "recurring_income",
            "recurring_expenses",
            "flexible_expenses",
            "protected_expenses",
            "reducible_expenses",
            "stoppable_expenses",
            "future_confirmed_income",
            "future_confirmed_expenses",
        ]

        for name in list_names:

            values = getattr(
                state,
                name,
            )

            values.sort(
                key=event_key
            )

    # ========================================================
    # INCOME / EXPENSE HEURISTICS
    # ========================================================

    @staticmethod
    def _looks_like_income(
        event: FinancialEvent,
    ) -> bool:
        """
        Conservative fallback for identifying income when
        direction is missing.

        Direction is normally authoritative.
        """

        event_type = (
            FinancialStateBuilder._normalize_text(
                event.event_type
            )
            or ""
        )

        description = (
            FinancialStateBuilder._normalize_text(
                event.description
            )
            or ""
        )

        keywords = [
            "salary",
            "payroll",
            "income",
            "wage",
            "commission",
            "bonus",
            "refund",
            "reimbursement",
            "dividend",
        ]

        text = (
            f"{event_type} "
            f"{description}"
        )

        return any(
            keyword in text
            for keyword in keywords
        )

    @staticmethod
    def _looks_like_expense(
        event: FinancialEvent,
    ) -> bool:
        """
        Conservative fallback for identifying expenses when
        direction is missing.
        """

        event_type = (
            FinancialStateBuilder._normalize_text(
                event.event_type
            )
            or ""
        )

        description = (
            FinancialStateBuilder._normalize_text(
                event.description
            )
            or ""
        )

        keywords = [
            "expense",
            "purchase",
            "payment",
            "rent",
            "utility",
            "grocery",
            "debt",
            "transfer",
            "subscription",
            "fee",
        ]

        text = (
            f"{event_type} "
            f"{description}"
        )

        return any(
            keyword in text
            for keyword in keywords
        )

    # ========================================================
    # TYPE HELPERS
    # ========================================================

    @staticmethod
    def _number(
        value: Any,
    ) -> Optional[float]:

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
            return float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _integer(
        value: Any,
    ) -> Optional[int]:

        number = FinancialStateBuilder._number(
            value
        )

        if number is None:
            return None

        return int(number)

    @staticmethod
    def _date(
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

        timestamp = pd.to_datetime(
            value,
            errors="coerce",
        )

        if pd.isna(timestamp):
            return None

        return timestamp

    @staticmethod
    def _string(
        value: Any,
    ) -> Optional[str]:

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

        value = str(value).strip()

        return value if value else None

    @staticmethod
    def _split_list(
        value: Any,
    ) -> List[str]:

        if value is None:
            return []

        try:

            if pd.isna(value):
                return []

        except (
            TypeError,
            ValueError,
        ):
            pass

        text = str(value).strip()

        if not text:
            return []

        return [
            item.strip()
            for item in text.split("|")
            if item.strip()
        ]

    @staticmethod
    def _normalize_status(
        value: Any,
    ) -> Optional[str]:

        text = FinancialStateBuilder._string(
            value
        )

        if text is None:
            return None

        return text.lower()

    @staticmethod
    def _normalize_text(
        value: Any,
    ) -> Optional[str]:

        text = FinancialStateBuilder._string(
            value
        )

        if text is None:
            return None

        return (
            text
            .lower()
            .strip()
        )


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================

def build_financial_state(
    loader: DatasetLoader,
    user_id: str,
    as_of_date: Optional[pd.Timestamp] = None,
) -> FinancialState:
    """
    Convenience function.

    Example
    -------

        loader = DatasetLoader("dataset")
        loader.load()

        state = build_financial_state(
            loader,
            "user_26",
            pd.Timestamp("2025-08-03")
        )
    """

    builder = FinancialStateBuilder(
        loader
    )

    return builder.build(
        user_id=user_id,
        as_of_date=as_of_date,
    )


# ============================================================
# COMMAND-LINE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print("BUY OR WAIT? - MODEL 2: FINANCIAL STATE")
    print("=" * 70)

    loader = DatasetLoader(
        "dataset"
    )

    loader.load()

    # --------------------------------------------------------
    # Use the first evaluation request as the test request.
    # --------------------------------------------------------

    first_request = (
        loader.data.requests.iloc[0]
    )

    request_id = str(
        first_request["request_id"]
    )

    user_id = str(
        first_request["user_id"]
    )

    request_date = pd.to_datetime(
        first_request["request_date"]
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
    # Build state.
    # --------------------------------------------------------

    builder = FinancialStateBuilder(
        loader
    )

    state = builder.build(
        user_id=user_id,
        as_of_date=request_date,
    )

    # --------------------------------------------------------
    # Populate future events.
    # --------------------------------------------------------

    builder.get_future_confirmed_events(
        state,
        request_date,
    )

    # --------------------------------------------------------
    # Print summary.
    # --------------------------------------------------------

    summary = state.summary()

    print("\nFinancial state summary:")

    for key, value in summary.items():
        print(
            f"  {key}: {value}"
        )

    # --------------------------------------------------------
    # Show important events.
    # --------------------------------------------------------

    print("\nImportant cash-flow events:")

    print(
        f"  Pending debits: "
        f"{len(state.pending_debits)}"
    )

    print(
        f"  Pending credits: "
        f"{len(state.pending_credits)}"
    )

    print(
        f"  Scheduled expenses: "
        f"{len(state.scheduled_expenses)}"
    )

    print(
        f"  Scheduled income: "
        f"{len(state.scheduled_income)}"
    )

    print(
        f"  Recurring expenses: "
        f"{len(state.recurring_expenses)}"
    )

    print(
        f"  Flexible expenses: "
        f"{len(state.flexible_expenses)}"
    )

    # --------------------------------------------------------
    # Print first few flexible expenses.
    # --------------------------------------------------------

    if state.flexible_expenses:

        print(
            "\nFlexible recurring expenses:"
        )

        for event in state.flexible_expenses[:10]:

            print(
                "  "
                f"{event.event_id} | "
                f"{event.category} | "
                f"{event.amount} | "
                f"{event.flexibility}"
            )

    # --------------------------------------------------------
    # Final status.
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("MODEL 2 FINANCIAL STATE: SUCCESS")
    print("=" * 70)