"""
Model 8: Financial Agent Orchestrator
=====================================

Buy or Wait? - HackerRank Orchestrate

Connects:

    Model 1  -> Dataset Loader
    Model 2  -> Financial State
    Model 3  -> Evidence Resolution
    Model 4  -> 90-Day Cash-Flow Forecast
    Model 5  -> Affordability Engine
    Model 6  -> Payment Plan Optimizer
    Model 7  -> Final Decision Engine
    Model 10 -> Grounded Explanation Engine

The FinancialAgent is an orchestrator.

It does NOT independently invent financial rules.
It passes the correct information between models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from ..models.data_loader import DatasetLoader
from ..models.financial_state import FinancialStateBuilder
from ..models.evidence_resolver import EvidenceResolver
from ..models.cashflow_forecast import CashFlowForecaster
from ..models.affordability_engine import AffordabilityEngine
from ..models.payment_optimizer import PaymentPlanOptimizer
from ..models.decision_engine import DecisionEngine
from ..models.explanation_engine import ExplanationEngine


# ============================================================
# FINANCIAL AGENT
# ============================================================

class FinancialAgent:
    """
    End-to-end Buy or Wait? financial agent.

    Parameters
    ----------
    dataset_path:
        Path to the participant-facing dataset directory.
    """

    def __init__(
        self,
        dataset_path: str = "dataset",
    ) -> None:

        self.dataset_path = Path(
            dataset_path
        )

        # ----------------------------------------------------
        # MODEL 1 — DATASET LOADER
        # ----------------------------------------------------

        self.loader = DatasetLoader(
            self.dataset_path
        )

        self.loader.load()

        # ----------------------------------------------------
        # MODEL 2 — FINANCIAL STATE
        # ----------------------------------------------------

        self.state_builder = (
            FinancialStateBuilder(
                self.loader
            )
        )

        # ----------------------------------------------------
        # MODEL 3 — EVIDENCE RESOLUTION
        # ----------------------------------------------------

        self.evidence_resolver = (
            EvidenceResolver(
                self.loader
            )
        )

        # ----------------------------------------------------
        # MODEL 4 — CASH-FLOW FORECAST
        # ----------------------------------------------------

        self.forecaster = (
            CashFlowForecaster(
                horizon_days=90
            )
        )

        # ----------------------------------------------------
        # MODEL 5 — AFFORDABILITY
        # ----------------------------------------------------

        self.affordability_engine = (
            AffordabilityEngine()
        )

        # ----------------------------------------------------
        # MODEL 6 — PAYMENT PLAN OPTIMIZER
        #
        # IMPORTANT:
        #
        # Do NOT pass payment options here.
        #
        # The active optimize() implementation expects the
        # payment options indirectly through the optimizer's
        # payment_options attribute.
        # ----------------------------------------------------

        self.payment_optimizer = (
            PaymentPlanOptimizer()
        )

        # ----------------------------------------------------
        # MODEL 7 — DECISION ENGINE
        # ----------------------------------------------------

        self.decision_engine = (
            DecisionEngine()
        )

        # ----------------------------------------------------
        # MODEL 10 — EXPLANATION ENGINE
        # ----------------------------------------------------

        self.explanation_engine = (
            ExplanationEngine()
        )

    # ========================================================
    # REQUEST LOOKUP
    # ========================================================

    def get_request(
        self,
        request_id: str,
    ) -> pd.Series:
        """
        Retrieve one evaluation request.

        Parameters
        ----------
        request_id:
            Request identifier from requests.csv.
        """

        if self.loader.data is None:
            raise RuntimeError(
                "Dataset has not been loaded."
            )

        request_id = str(
            request_id
        ).strip()

        requests = (
            self.loader.data.requests
        )

        matches = requests[
            requests[
                "request_id"
            ]
            .astype(str)
            .str.strip()
            == request_id
        ]

        if matches.empty:

            raise ValueError(
                f"Request '{request_id}' "
                f"was not found in requests.csv"
            )

        return matches.iloc[0]

    # ========================================================
    # PAYMENT OPTIONS
    # ========================================================

    def get_payment_options(
        self,
        request_id: str,
    ) -> pd.DataFrame:
        """
        Return payment options belonging only to one request.
        """

        if self.loader.data is None:
            raise RuntimeError(
                "Dataset has not been loaded."
            )

        options = self.loader.options_for_request(
            request_id
        )

        if options is None:
            return pd.DataFrame()

        return options.copy()
    # ========================================================
    # GENERIC ATTRIBUTE GETTER
    # ========================================================

    @staticmethod
    def _get(
        obj: Any,
        field: str,
        default: Any = None,
    ) -> Any:
        """
        Read a field from either a dictionary, pandas Series,
        dataclass/object, or other compatible object.
        """

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

            if hasattr(
                obj,
                "get",
            ):

                value = obj.get(
                    field,
                    default,
                )

                if value is not None:
                    return value

        except Exception:
            pass

        return getattr(
            obj,
            field,
            default,
        )

    # ========================================================
    # DATE FORMATTER
    # ========================================================

    @staticmethod
    def _format_date(
        value: Any,
    ) -> Optional[str]:
        """
        Convert a date-like value to YYYY-MM-DD.
        """

        if value is None:
            return None

        try:

            timestamp = pd.to_datetime(
                value,
                errors="coerce",
            )

            if pd.isna(timestamp):
                return None

            return pd.Timestamp(
                timestamp
            ).strftime(
                "%Y-%m-%d"
            )

        except Exception:

            return None

    # ========================================================
    # RUN AGENT
    # ========================================================

    def run(
        self,
        request_id: str,
    ) -> Dict[str, Any]:
        """
        Run the complete financial decision pipeline.

        Returns
        -------
        dict
            Structured final result suitable for main.py.
        """

        # ----------------------------------------------------
        # STEP 1 — REQUEST
        # ----------------------------------------------------

        request = self.get_request(
            request_id
        )

        request_id = str(
            self._get(
                request,
                "request_id",
                request_id,
            )
        )

        user_id = str(
            self._get(
                request,
                "user_id",
                "",
            )
        )

        request_date = pd.to_datetime(
            self._get(
                request,
                "request_date",
            ),
            errors="coerce",
        ).normalize()

        if pd.isna(
            request_date
        ):
            raise ValueError(
                f"Invalid request_date "
                f"for {request_id}"
            )

        requested_amount = float(
            self._get(
                request,
                "requested_amount",
                0.0,
            )
            or 0.0
        )

        desired_completion_date = pd.to_datetime(
            self._get(
                request,
                "desired_completion_date",
            ),
            errors="coerce",
        ).normalize()

        if pd.isna(
            desired_completion_date
        ):
            raise ValueError(
                f"Invalid desired_completion_date "
                f"for {request_id}"
            )

        # ----------------------------------------------------
        # STEP 2 — FINANCIAL STATE
        # ----------------------------------------------------

        state = (
            self.state_builder.build(
                user_id=user_id,
                as_of_date=request_date,
            )
        )

        # ----------------------------------------------------
        # STEP 3 — EVIDENCE RESOLUTION
        # ----------------------------------------------------

        resolved_events = (
            self.evidence_resolver
            .resolve_state(
                state
            )
        )

        # ----------------------------------------------------
        # STEP 4 — 90-DAY CASH-FLOW FORECAST
        # ----------------------------------------------------

        forecast = (
            self.forecaster.forecast(
                state=state,
                resolved_events=resolved_events,
                as_of_date=request_date,
            )
        )

        # ----------------------------------------------------
        # STEP 5 — AFFORDABILITY
        # ----------------------------------------------------

        currency = getattr(
            state,
            "home_currency",
            None,
        )

        affordability = (
            self.affordability_engine
            .assess(
                state=state,
                forecast=forecast,
                purchase_price=requested_amount,
                currency=currency,
                request_id=request_id,
            )
        )

        # ----------------------------------------------------
        # STEP 6 — PAYMENT OPTIONS
        # ----------------------------------------------------

        payment_options = self.get_payment_options(request_id)
        # FinancialStateBuilder stores the user's payment
        # preferences in accepted_payment_methods.
        # Keep a compatibility fallback for older state objects.
        accepted_methods = getattr(
            state,
            "accepted_payment_methods",
            None,
        )

        if accepted_methods is None:
            accepted_methods = getattr(
                state,
                "payment_methods_user_will_consider",
                [],
            )

        # Be defensive if a state implementation returns a
        # pipe-separated string instead of a list.
        if isinstance(accepted_methods, str):
            accepted_methods = [
                item.strip()
                for item in accepted_methods.split("|")
                if item.strip()
            ]

        max_installment_months = getattr(
            state,
            "max_installment_months",
            None,
        )

        # ----------------------------------------------------
        # Values from Model 5
        # ----------------------------------------------------

        amount_safe_to_pay = float(
            getattr(
                affordability,
                "amount_safe_to_pay",
                getattr(
                    affordability,
                    "safe_amount",
                    0.0,
                ),
            )
            or 0.0
        )

        # Keep the value inside the challenge contract.
        amount_safe_to_pay = max(
            0.0,
            min(
                amount_safe_to_pay,
                requested_amount,
            ),
        )

        earliest_date_for_full_payment = getattr(
            affordability,
            "earliest_safe_date",
            getattr(
                affordability,
                "earliest_date_for_full_payment",
                None,
            ),
        )

        # Some affordability implementations may use a
        # different field name. Try several compatible names.
        if earliest_date_for_full_payment is None:

            earliest_date_for_full_payment = getattr(
                affordability,
                "full_payment_safe_date",
                None,
            )

        # If Model 5 says the purchase is immediately
        # affordable, the specification requires the earliest
        # safe date to be request_date.
        immediate_affordable = bool(
            getattr(
                affordability,
                "immediate_affordable",
                False,
            )
        )

        if immediate_affordable:

            earliest_date_for_full_payment = (
                request_date
            )

        # ----------------------------------------------------
        # MODEL 6 — PAYMENT PLAN OPTIMIZER
        # ----------------------------------------------------
        #
        # IMPORTANT:
        # Use the request-specific payment_options already
        # loaded above. Do NOT call get_payment_options()
        # without request_id.
        #
        # The active optimizer accepts the explicit argument
        # payment_options, so pass the DataFrame directly.
        # ----------------------------------------------------

        payment_result = (
            self.payment_optimizer
            .optimize(
                request_id=request_id,
                request_date=request_date,
                requested_amount=requested_amount,
                desired_completion_date=(
                    desired_completion_date
                ),
                user_payment_methods=(
                    accepted_methods
                ),
                max_installment_months=(
                    max_installment_months
                ),
                amount_safe_to_pay=(
                    amount_safe_to_pay
                ),
                earliest_date_for_full_payment=(
                    earliest_date_for_full_payment
                ),
                allows_partial_payment=bool(
                    self._get(
                        request,
                        "allows_partial_payment",
                        False,
                    )
                ),
                payment_options=(
                    payment_options
                ),
            )
        )

        # ----------------------------------------------------
        # STEP 7 — FINAL DECISION
        # ----------------------------------------------------

        decision = (
            self.decision_engine
            .decide(
                request=request,
                state=state,
                forecast=forecast,
                affordability=affordability,
                payment_result=payment_result,
            )
        )

        # ----------------------------------------------------
        # STEP 8 — MODEL 10 EXPLANATION
        # ----------------------------------------------------

        decision_earliest_date = getattr(
            decision,
            "earliest_safe_date",
            None,
        )

        decision_payload = {

            "request_id": (
                decision.request_id
            ),

            "user_id": (
                decision.user_id
            ),

            "decision": (
                decision.decision
            ),

            "safe_amount": (
                decision.safe_amount
            ),

            "requested_amount": (
                decision.requested_amount
            ),

            "currency": (
                decision.currency
            ),

            "payment_method": (
                decision.payment_method
            ),

            "payment_option_id": (
                decision.payment_option_id
            ),

            "payment_plan": (
                decision.payment_plan
            ),

            "earliest_safe_date": (
                self._format_date(
                    decision_earliest_date
                )
            ),

            "spending_changes": (
                decision.spending_changes
            ),

            "reasons": (
                decision.reasons
            ),

            "warnings": (
                decision.warnings
            ),

            "confidence": (
                decision.confidence
            ),
        }

        explanation = (
            self.explanation_engine
            .explain(
                decision_payload
            )
        )

        # ----------------------------------------------------
        # FINAL AGENT RESULT
        # ----------------------------------------------------

        return {

            "request_id": (
                decision.request_id
            ),

            "user_id": (
                decision.user_id
            ),

            "decision": (
                decision.decision
            ),

            "headline": (
                explanation.headline
            ),

            "summary": (
                explanation.summary
            ),

            "requested_amount": (
                decision.requested_amount
            ),

            "safe_amount": (
                decision.safe_amount
            ),

            "currency": (
                decision.currency
            ),

            "payment_method": (
                decision.payment_method
            ),

            "payment_option_id": (
                decision.payment_option_id
            ),

            "payment_plan": (
                decision.payment_plan
            ),

            "earliest_safe_date": (
                self._format_date(
                    decision.earliest_safe_date
                )
            ),

            "financial_impact": (
                explanation.financial_impact
            ),

            "recommendation": (
                explanation.recommendation
            ),

            "spending_changes": (
                decision.spending_changes
            ),

            "reasons": (
                decision.reasons
            ),

            "warnings": (
                decision.warnings
            ),

            "confidence": (
                decision.confidence
            ),
        }


# ============================================================
# PRINT RESULT
# ============================================================

def print_result(
    result: Dict[str, Any],
) -> None:

    print()
    print("=" * 70)
    print(
        "BUY OR WAIT? - FINANCIAL AGENT"
    )
    print("=" * 70)

    print(
        f"\nRequest ID: "
        f"{result['request_id']}"
    )

    print(
        f"User ID: "
        f"{result['user_id']}"
    )

    print(
        "\nFINAL DECISION"
    )

    print(
        f"  {str(result['decision']).upper()}"
    )

    print(
        f"\nRequested amount: "
        f"{result['requested_amount']:,.2f} "
        f"{result['currency']}"
    )

    print(
        f"Safe amount: "
        f"{result['safe_amount']:,.2f} "
        f"{result['currency']}"
    )

    if result.get(
        "payment_method"
    ):

        print(
            f"\nPayment method: "
            f"{result['payment_method']}"
        )

    if result.get(
        "payment_option_id"
    ):

        print(
            f"Payment option: "
            f"{result['payment_option_id']}"
        )

    if result.get(
        "payment_plan"
    ):

        print(
            f"Payment plan: "
            f"{result['payment_plan']}"
        )

    if result.get(
        "earliest_safe_date"
    ):

        print(
            f"\nEarliest safe date: "
            f"{result['earliest_safe_date']}"
        )

    if result.get(
        "financial_impact"
    ):

        print(
            "\nFINANCIAL IMPACT"
        )

        for item in result[
            "financial_impact"
        ]:

            print(
                f"  - {item}"
            )

    print(
        "\nRECOMMENDATION"
    )

    print(
        f"  {result['recommendation']}"
    )

    if result.get(
        "spending_changes"
    ):

        print(
            "\nSPENDING CHANGES"
        )

        for item in result[
            "spending_changes"
        ]:

            print(
                f"  - {item}"
            )

    if result.get(
        "reasons"
    ):

        print(
            "\nWHY"
        )

        for reason in result[
            "reasons"
        ]:

            print(
                f"  - {reason}"
            )

    if result.get(
        "warnings"
    ):

        print(
            "\nWARNINGS"
        )

        for warning in result[
            "warnings"
        ]:

            print(
                f"  - {warning}"
            )

    print(
        f"\nConfidence: "
        f"{float(result['confidence']):.2f}"
    )

    print(
        "\n" + "=" * 70
    )

    print(
        "FINANCIAL AGENT: SUCCESS"
    )

    print(
        "=" * 70
    )


# ============================================================
# COMMAND-LINE TEST
# ============================================================

if __name__ == "__main__":

    print(
        "=" * 70
    )

    print(
        "BUY OR WAIT? - FINANCIAL AGENT TEST"
    )

    print(
        "=" * 70
    )

    agent = FinancialAgent(
        dataset_path="dataset"
    )

    result = agent.run(
        "request_26"
    )

    print_result(
        result
    )