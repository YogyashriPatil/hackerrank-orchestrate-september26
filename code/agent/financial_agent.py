"""
Model 8: Financial Agent Orchestrator

Connects Models 1-7 into one end-to-end financial agent.

Input:
    request_id

Output:
    final structured financial decision
"""

from __future__ import annotations

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
    ):

        self.dataset_path = dataset_path

        # Model 1
        self.loader = DatasetLoader(
            dataset_path
        )

        self.loader.load()

        # Models
        self.state_builder = (
            FinancialStateBuilder(
                self.loader
            )
        )

        self.evidence_resolver = (
            EvidenceResolver(
                self.loader
            )
        )

        self.forecaster = (
            CashFlowForecaster(
                horizon_days=90
            )
        )

        self.affordability_engine = (
            AffordabilityEngine()
        )

        # self.payment_optimizer = (
        #     PaymentPlanOptimizer()
        # )
        self.payment_optimizer = PaymentPlanOptimizer(
            payment_options=self.loader.request_payment_options
        )

        self.decision_engine = (
            DecisionEngine()
        )

        self.explanation_engine = (
            ExplanationEngine()
        )

    # ========================================================
    # FIND REQUEST
    # ========================================================

    def get_request(
        self,
        request_id: str,
    ):

        requests = (
            self.loader.data.requests
        )

        matches = requests[
            requests[
                "request_id"
            ].astype(str)
            == str(request_id)
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

    def get_payment_options(self):

        data = self.loader.data

        # Try names exposed by Dataset.
        possible_names = [
            "request_payment_options",
            "payment_option",
            "payment_options_df",
            "request_payment_option",
        ]

        for name in possible_names:

            if hasattr(
                data,
                name,
            ):

                value = getattr(
                    data,
                    name,
                )

                if isinstance(
                    value,
                    pd.DataFrame,
                ):

                    return value

        # Fallback to the real CSV.
        path = (
            f"{self.dataset_path}/"
            "request_payment_options.csv"
        )

        return pd.read_csv(path)

    # ========================================================
    # RUN AGENT
    # ========================================================

    def run(
        self,
        request_id: str,
    ):

        # ----------------------------------------------------
        # STEP 1 — Request
        # ----------------------------------------------------

        request = self.get_request(
            request_id
        )

        user_id = str(
            request["user_id"]
        )

        request_date = pd.to_datetime(
            request["request_date"]
        ).normalize()

        # ----------------------------------------------------
        # STEP 2 — Financial State
        # ----------------------------------------------------

        state = (
            self.state_builder.build(
                user_id=user_id,
                as_of_date=request_date,
            )
        )

        # ----------------------------------------------------
        # STEP 3 — Evidence Resolution
        # ----------------------------------------------------

        resolved_events = (
            self.evidence_resolver
            .resolve_state(
                state
            )
        )

        # ----------------------------------------------------
        # STEP 4 — 90-Day Forecast
        # ----------------------------------------------------

        forecast = (
            self.forecaster.forecast(
                state=state,
                resolved_events=resolved_events,
                as_of_date=request_date,
            )
        )

        # ----------------------------------------------------
        # STEP 5 — Affordability
        # ----------------------------------------------------

        requested_amount = float(
            request.get(
                "requested_amount",
                0,
            )
        )

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
        # STEP 6 — Payment Optimization
        # ----------------------------------------------------

        payment_options = (
            self.get_payment_options()
        )

        payment_result = (
            self.payment_optimizer
            .optimize(
                request=request,
                state=state,
                forecast=forecast,
                payment_options=payment_options,
            )
        )

        # ----------------------------------------------------
        # STEP 7 — Final Decision
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
        # STEP 8 — Structured output
        # ----------------------------------------------------

        # return {
        #     "request_id": decision.request_id,
        #     "user_id": decision.user_id,

        #     "decision": decision.decision,

        #     "safe_amount": decision.safe_amount,

        #     "requested_amount": (
        #         decision.requested_amount
        #     ),

        #     "currency": decision.currency,

        #     "payment_method": (
        #         decision.payment_method
        #     ),

        #     "payment_option_id": (
        #         decision.payment_option_id
        #     ),

        #     "payment_plan": (
        #         decision.payment_plan
        #     ),

        #     "earliest_safe_date": (
        #         decision.earliest_safe_date
        #         .strftime("%Y-%m-%d")
        #         if decision.earliest_safe_date
        #         else None
        #     ),

        #     "spending_changes": (
        #         decision.spending_changes
        #     ),

        #     "reasons": (
        #         decision.reasons
        #     ),

        #     "warnings": (
        #         decision.warnings
        #     ),

        #     "confidence": (
        #         decision.confidence
        #     ),
        # }
        # --------------------------------------------------------
        # MODEL 10 — GROUNDED EXPLANATION
        # --------------------------------------------------------

        explanation = (
            self.explanation_engine.explain(
                {
                    "request_id": decision.request_id,
                    "user_id": decision.user_id,
                    "decision": decision.decision,
                    "safe_amount": decision.safe_amount,
                    "requested_amount": decision.requested_amount,
                    "currency": decision.currency,
                    "payment_method": decision.payment_method,
                    "payment_option_id": decision.payment_option_id,
                    "payment_plan": decision.payment_plan,
                    "earliest_safe_date": (
                        decision.earliest_safe_date
                        .strftime("%Y-%m-%d")
                        if decision.earliest_safe_date
                        else None
                    ),
                    "spending_changes": (
                        decision.spending_changes
                    ),
                    "reasons": decision.reasons,
                    "warnings": decision.warnings,
                    "confidence": decision.confidence,
                }
            )
        )

        # --------------------------------------------------------
        # FINAL AGENT RESPONSE
        # --------------------------------------------------------

        return {
            "request_id": decision.request_id,
            "user_id": decision.user_id,

            "decision": decision.decision,

            "headline": explanation.headline,

            "summary": explanation.summary,

            "requested_amount": (
                decision.requested_amount
            ),

            "safe_amount": (
                decision.safe_amount
            ),

            "currency": decision.currency,

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
                decision.earliest_safe_date
                .strftime("%Y-%m-%d")
                if decision.earliest_safe_date
                else None
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
    result,
):

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
        f"  {result['decision'].upper()}"
    )

    print(
        f"\nRequested amount:"
        f" {result['requested_amount']:,.2f} "
        f"{result['currency']}"
    )

    print(
        f"Safe amount:"
        f" {result['safe_amount']:,.2f} "
        f"{result['currency']}"
    )

    if result[
        "payment_method"
    ]:

        print(
            f"\nPayment method:"
            f" {result['payment_method']}"
        )

    if result[
        "payment_option_id"
    ]:

        print(
            f"Payment option:"
            f" {result['payment_option_id']}"
        )

    if result[
        "payment_plan"
    ]:

        print(
            f"Payment plan:"
        )

        print(
            f"  {result['payment_plan']}"
        )

    if result[
        "earliest_safe_date"
    ]:

        print(
            f"\nEarliest safe date:"
            f" {result['earliest_safe_date']}"
        )

    if result[
        "spending_changes"
    ]:

        print(
            "\nSpending changes:"
        )

        for item in result[
            "spending_changes"
        ]:

            print(
                f"  - {item}"
            )

    print(
        "\nReasons:"
    )

    for reason in result[
        "reasons"
    ]:

        print(
            f"  - {reason}"
        )

    if result[
        "warnings"
    ]:

        print(
            "\nWarnings:"
        )

        for warning in result[
            "warnings"
        ]:

            print(
                f"  - {warning}"
            )

    print(
        f"\nConfidence:"
        f" {result['confidence']:.2f}"
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
# MAIN
# ============================================================

if __name__ == "__main__":

    agent = FinancialAgent(
        dataset_path="dataset"
    )

    # Test request
    result = agent.run(
        "request_26"
    )

    print_result(
        result
    )