"""
Model 8 — Financial Agent Orchestrator
=======================================

Buy or Wait? - HackerRank Orchestrate

Pipeline:

    Model 1  Dataset Loader
        ↓
    Model 2  Financial State
        ↓
    Model 3  Evidence Resolver
        ↓
    Model 4  Cash-Flow Forecast
        ↓
    Model 5  Affordability
        ↓
    Model 6  Payment Optimizer
        ↓
    Model 7  Decision Engine
        ↓
    Model 10 Explanation Engine
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


class FinancialAgent:

    def __init__(
        self,
        dataset_path: str = "dataset",
    ) -> None:

        self.dataset_path = Path(dataset_path)

        # ====================================================
        # MODEL 1
        # ====================================================

        self.loader = DatasetLoader(
            self.dataset_path
        )

        self.loader.load()

        # ====================================================
        # MODEL 2
        # ====================================================

        self.state_builder = FinancialStateBuilder(
            self.loader
        )

        # ====================================================
        # MODEL 3
        # ====================================================

        self.evidence_resolver = EvidenceResolver(
            self.loader
        )

        # ====================================================
        # MODEL 4
        # ====================================================

        self.forecaster = CashFlowForecaster(
            horizon_days=90
        )

        # ====================================================
        # MODEL 5
        # ====================================================

        self.affordability_engine = AffordabilityEngine()

        # ====================================================
        # MODEL 6
        # ====================================================

        self.payment_optimizer = PaymentPlanOptimizer()

        # ====================================================
        # MODEL 7
        # ====================================================

        self.decision_engine = DecisionEngine()

        # ====================================================
        # MODEL 10
        # ====================================================

        self.explanation_engine = ExplanationEngine()

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

        if isinstance(obj, dict):
            return obj.get(field, default)

        try:
            if hasattr(obj, "get"):
                value = obj.get(field, default)

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
    # DATE FORMAT
    # ========================================================

    @staticmethod
    def _format_date(
        value: Any,
    ) -> Optional[str]:

        if value is None:
            return None

        try:

            ts = pd.to_datetime(
                value,
                errors="coerce",
            )

            if pd.isna(ts):
                return None

            return pd.Timestamp(ts).strftime(
                "%Y-%m-%d"
            )

        except Exception:

            return None

    # ========================================================
    # REQUEST
    # ========================================================

    def get_request(
        self,
        request_id: str,
    ) -> pd.Series:

        if self.loader.data is None:
            raise RuntimeError(
                "Dataset has not been loaded."
            )

        request_id = str(
            request_id
        ).strip()

        requests = self.loader.data.requests

        matches = requests[
            requests["request_id"]
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
    # RUN
    # ========================================================

    def run(
        self,
        request_id: str,
    ) -> Dict[str, Any]:

        # ====================================================
        # 1. REQUEST
        # ====================================================

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
        )

        if pd.isna(request_date):
            raise ValueError(
                f"Invalid request_date "
                f"for {request_id}"
            )

        request_date = pd.Timestamp(
            request_date
        ).normalize()

        desired_completion_date = pd.to_datetime(
            self._get(
                request,
                "desired_completion_date",
            ),
            errors="coerce",
        )

        if pd.isna(
            desired_completion_date
        ):
            desired_completion_date = None

        else:
            desired_completion_date = pd.Timestamp(
                desired_completion_date
            ).normalize()

        requested_amount = float(
            self._get(
                request,
                "requested_amount",
                0.0,
            )
            or 0.0
        )

        # ====================================================
        # 2. FINANCIAL STATE
        # ====================================================

        state = self.state_builder.build(
            user_id=user_id,
            as_of_date=request_date,
        )

        # ====================================================
        # 3. EVIDENCE
        # ====================================================

        resolved_events = (
            self.evidence_resolver.resolve_state(
                state
            )
        )

        # ====================================================
        # 4. CASH-FLOW FORECAST
        # ====================================================

        forecast = self.forecaster.forecast(
            state=state,
            resolved_events=resolved_events,
            as_of_date=request_date,
        )

        # ====================================================
        # 5. AFFORDABILITY
        # ====================================================

        affordability = (
            self.affordability_engine.assess(
                state=state,
                forecast=forecast,
                purchase_price=requested_amount,
                currency=getattr(
                    state,
                    "home_currency",
                    None,
                ),
                request_id=request_id,
            )
        )

        # ====================================================
        # 6. PAYMENT OPTIONS
        #
        # IMPORTANT:
        #
        # This MUST be request-specific.
        # ====================================================

        payment_options = (
            self.get_payment_options(
                request_id
            )
        )

        # ====================================================
        # USER PAYMENT PREFERENCES
        #
        # FinancialState calls this:
        #
        #     accepted_payment_methods
        #
        # not payment_methods_user_will_consider.
        # ====================================================

        accepted_methods = list(
            getattr(
                state,
                "accepted_payment_methods",
                [],
            )
            or []
        )

        max_installment_months = getattr(
            state,
            "max_installment_months",
            None,
        )

        allows_partial_payment = bool(
            self._get(
                request,
                "allows_partial_payment",
                False,
            )
        )

        amount_safe_to_pay = float(
            getattr(
                affordability,
                "amount_safe_to_pay",
                0.0,
            )
            or 0.0
        )

        earliest_safe_date = getattr(
            affordability,
            "earliest_safe_date",
            None,
        )

        # ====================================================
        # 7. PAYMENT OPTIMIZATION
        #
        # Use the current optimizer API.
        # ====================================================

        payment_result = (
            self.payment_optimizer.optimize(
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
                    earliest_safe_date
                ),
                allows_partial_payment=(
                    allows_partial_payment
                ),
                payment_options=(
                    payment_options
                ),
            )
        )

        # ====================================================
        # 8. FINAL DECISION
        # ====================================================

        decision = self.decision_engine.decide(
            request=request,
            state=state,
            forecast=forecast,
            affordability=affordability,
            payment_result=payment_result,
        )

        # ====================================================
        # 9. EXPLANATION
        # ====================================================

        decision_payload = {

            "request_id":
                decision.request_id,

            "user_id":
                decision.user_id,

            "decision":
                decision.decision,

            "safe_amount":
                decision.safe_amount,

            "requested_amount":
                decision.requested_amount,

            "currency":
                decision.currency,

            "payment_method":
                decision.payment_method,

            "payment_option_id":
                decision.payment_option_id,

            "payment_plan":
                decision.payment_plan,

            "earliest_safe_date":
                self._format_date(
                    decision.earliest_safe_date
                ),

            "spending_changes":
                decision.spending_changes,

            "reasons":
                decision.reasons,

            "warnings":
                decision.warnings,

            "confidence":
                decision.confidence,
        }

        explanation = (
            self.explanation_engine.explain(
                decision_payload
            )
        )

        # ====================================================
        # 10. FINAL RESULT
        # ====================================================

        return {

            "request_id":
                decision.request_id,

            "user_id":
                decision.user_id,

            "decision":
                decision.decision,

            "headline":
                explanation.headline,

            "summary":
                explanation.summary,

            "requested_amount":
                decision.requested_amount,

            "safe_amount":
                decision.safe_amount,

            "currency":
                decision.currency,

            "payment_method":
                decision.payment_method,

            "payment_option_id":
                decision.payment_option_id,

            "payment_plan":
                decision.payment_plan,

            "earliest_safe_date":
                self._format_date(
                    decision.earliest_safe_date
                ),

            "financial_impact":
                explanation.financial_impact,

            "spending_changes":
                decision.spending_changes,

            "reasons":
                decision.reasons,

            "warnings":
                decision.warnings,

            "recommendation":
                explanation.recommendation,

            "confidence":
                decision.confidence,
        }


# ============================================================
# DIRECT TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        "BUY OR WAIT? - FINANCIAL AGENT TEST"
    )
    print("=" * 70)

    agent = FinancialAgent(
        dataset_path="dataset"
    )

    result = agent.run(
        "request_26"
    )

    print()
    print("=" * 70)
    print("FINAL RESULT")
    print("=" * 70)

    for key, value in result.items():

        print(
            f"{key}: {value}"
        )

    print()
    print("=" * 70)
    print(
        "FINANCIAL AGENT: SUCCESS"
    )
    print("=" * 70)