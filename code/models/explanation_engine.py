"""
Model 10: Grounded Explanation Engine
=====================================

Converts the structured output of Model 7 into a clear,
user-facing financial explanation.

IMPORTANT:
    This model does NOT make or change the financial decision.

    Model 7 remains the source of truth.

The explanation is grounded only in:
    - final decision
    - requested amount
    - safe amount
    - payment method
    - payment plan
    - earliest safe date
    - spending changes
    - reasons
    - warnings
    - confidence
"""


from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ============================================================
# EXPLANATION RESULT
# ============================================================

@dataclass
class ExplanationResult:

    request_id: str

    user_id: str

    decision: str

    headline: str

    summary: str

    financial_impact: List[str]

    recommendation: str

    reasons: List[str]

    warnings: List[str]

    confidence: float

    currency: str

    requested_amount: float

    safe_amount: float


# ============================================================
# EXPLANATION ENGINE
# ============================================================

class ExplanationEngine:
    """
    Produces a grounded explanation from Model 7 output.

    No new financial calculation is performed here.
    """

    # --------------------------------------------------------
    # PUBLIC METHOD
    # --------------------------------------------------------

    def explain(
        self,
        decision_result: Any,
    ) -> ExplanationResult:

        request_id = self._get(
            decision_result,
            "request_id",
            "unknown",
        )

        user_id = self._get(
            decision_result,
            "user_id",
            "unknown",
        )

        decision = self._get(
            decision_result,
            "decision",
            "not_affordable",
        )

        currency = self._get(
            decision_result,
            "currency",
            "",
        )

        requested_amount = float(
            self._get(
                decision_result,
                "requested_amount",
                0,
            )
        )

        safe_amount = float(
            self._get(
                decision_result,
                "safe_amount",
                0,
            )
        )

        payment_method = self._get(
            decision_result,
            "payment_method",
            None,
        )

        payment_option_id = self._get(
            decision_result,
            "payment_option_id",
            None,
        )

        payment_plan = self._get(
            decision_result,
            "payment_plan",
            None,
        )

        earliest_safe_date = self._get(
            decision_result,
            "earliest_safe_date",
            None,
        )

        spending_changes = self._get(
            decision_result,
            "spending_changes",
            [],
        )

        reasons = self._get(
            decision_result,
            "reasons",
            [],
        )

        warnings = self._get(
            decision_result,
            "warnings",
            [],
        )

        confidence = float(
            self._get(
                decision_result,
                "confidence",
                0,
            )
        )

        # ----------------------------------------------------
        # Headline
        # ----------------------------------------------------

        headline = (
            self._build_headline(
                decision
            )
        )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        summary = (
            self._build_summary(
                decision=decision,
                requested_amount=requested_amount,
                safe_amount=safe_amount,
                currency=currency,
                earliest_safe_date=(
                    earliest_safe_date
                ),
            )
        )

        # ----------------------------------------------------
        # Financial impact
        # ----------------------------------------------------

        financial_impact = (
            self._build_financial_impact(
                decision_result
            )
        )

        # ----------------------------------------------------
        # Recommendation
        # ----------------------------------------------------

        recommendation = (
            self._build_recommendation(
                decision=decision,
                payment_method=(
                    payment_method
                ),
                payment_option_id=(
                    payment_option_id
                ),
                payment_plan=(
                    payment_plan
                ),
                earliest_safe_date=(
                    earliest_safe_date
                ),
                spending_changes=(
                    spending_changes
                ),
            )
        )

        return ExplanationResult(
            request_id=str(
                request_id
            ),

            user_id=str(
                user_id
            ),

            decision=str(
                decision
            ),

            headline=headline,

            summary=summary,

            financial_impact=(
                financial_impact
            ),

            recommendation=(
                recommendation
            ),

            reasons=list(
                reasons
                if isinstance(
                    reasons,
                    list,
                )
                else [str(reasons)]
            ),

            warnings=list(
                warnings
                if isinstance(
                    warnings,
                    list,
                )
                else [str(warnings)]
            ),

            confidence=confidence,

            currency=str(
                currency
            ),

            requested_amount=(
                requested_amount
            ),

            safe_amount=(
                safe_amount
            ),
        )

    # ========================================================
    # HEADLINE
    # ========================================================

    @staticmethod
    def _build_headline(
        decision: str,
    ) -> str:

        headlines = {

            "affordable_now":
                "This purchase is affordable now.",

            "affordable_with_plan":
                "This purchase is affordable with a payment plan.",

            "affordable_later":
                "It is safer to wait before making this purchase.",

            "not_affordable":
                "This purchase is not safely affordable right now.",
        }

        return headlines.get(
            decision,
            "Purchase decision completed.",
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    @staticmethod
    def _build_summary(
        decision: str,
        requested_amount: float,
        safe_amount: float,
        currency: str,
        earliest_safe_date: Optional[str],
    ) -> str:

        amount = (
            f"{requested_amount:,.2f} "
            f"{currency}"
        )

        safe = (
            f"{safe_amount:,.2f} "
            f"{currency}"
        )

        if decision == "affordable_now":

            return (
                f"The requested purchase of {amount} "
                f"fits within the calculated safe spending "
                f"amount of {safe}."
            )

        if decision == "affordable_with_plan":

            return (
                f"The purchase of {amount} is not best "
                f"handled as an unrestricted immediate payment, "
                f"but a supported payment plan can keep the "
                f"purchase within the calculated financial limits."
            )

        if decision == "affordable_later":

            if earliest_safe_date:

                return (
                    f"The requested purchase of {amount} "
                    f"is safer after the financial position "
                    f"improves. The calculated earliest safe "
                    f"date is {earliest_safe_date}."
                )

            return (
                f"The requested purchase of {amount} "
                f"is not safely affordable at the moment."
            )

        return (
            f"The requested purchase of {amount} "
            f"exceeds the currently calculated safe "
            f"spending capacity of {safe}."
        )

    # ========================================================
    # FINANCIAL IMPACT
    # ========================================================

    @staticmethod
    def _build_financial_impact(
        result: Any,
    ) -> List[str]:

        requested_amount = float(
            ExplanationEngine._get(
                result,
                "requested_amount",
                0,
            )
        )

        safe_amount = float(
            ExplanationEngine._get(
                result,
                "safe_amount",
                0,
            )
        )

        currency = ExplanationEngine._get(
            result,
            "currency",
            "",
        )

        decision = ExplanationEngine._get(
            result,
            "decision",
            "",
        )

        impact = []

        impact.append(
            "Requested amount: "
            f"{requested_amount:,.2f} "
            f"{currency}"
        )

        impact.append(
            "Calculated safe amount: "
            f"{safe_amount:,.2f} "
            f"{currency}"
        )

        if decision == "affordable_now":

            remaining = (
                safe_amount
                - requested_amount
            )

            impact.append(
                "Amount remaining within the "
                "calculated safe capacity: "
                f"{max(0, remaining):,.2f} "
                f"{currency}"
            )

        elif decision == "not_affordable":

            shortfall = (
                requested_amount
                - safe_amount
            )

            impact.append(
                "Amount above the calculated "
                "safe capacity: "
                f"{max(0, shortfall):,.2f} "
                f"{currency}"
            )

        return impact

    # ========================================================
    # RECOMMENDATION
    # ========================================================

    @staticmethod
    def _build_recommendation(
        decision: str,
        payment_method: Optional[str],
        payment_option_id: Optional[str],
        payment_plan: Optional[str],
        earliest_safe_date: Optional[str],
        spending_changes: List[str],
    ) -> str:

        if decision == "affordable_now":

            if payment_method:

                return (
                    f"Proceed using {payment_method}. "
                    f"The selected payment option is compatible "
                    f"with the financial decision."
                )

            return (
                "Proceed with the purchase while maintaining "
                "the required financial reserve."
            )

        if decision == "affordable_with_plan":

            recommendation = (
                "Use the recommended payment plan "
                "instead of making the full payment immediately."
            )

            if payment_method:

                recommendation += (
                    f" Payment method: "
                    f"{payment_method}."
                )

            if payment_option_id:

                recommendation += (
                    f" Option: "
                    f"{payment_option_id}."
                )

            if payment_plan:

                recommendation += (
                    f" Schedule: "
                    f"{payment_plan}."
                )

            return recommendation

        if decision == "affordable_later":

            if earliest_safe_date:

                return (
                    "Wait until "
                    f"{earliest_safe_date} "
                    "before making the purchase."
                )

            return (
                "Wait until the financial position "
                "improves before making the purchase."
            )

        if spending_changes:

            return (
                "Do not make the purchase yet. "
                "Consider reducing or stopping "
                "non-essential spending before "
                "reconsidering the purchase."
            )

        return (
            "Do not make the purchase yet. "
            "The current financial position does "
            "not safely support it."
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

        return getattr(
            obj,
            field,
            default,
        )


# ============================================================
# USER-FACING REPORT
# ============================================================

def print_explanation(
    explanation: ExplanationResult,
) -> None:

    print()
    print("=" * 70)
    print(
        "MODEL 10: GROUNDED EXPLANATION"
    )
    print("=" * 70)

    print(
        f"\n{explanation.headline}"
    )

    print(
        f"\nRequest ID: "
        f"{explanation.request_id}"
    )

    print(
        f"User ID: "
        f"{explanation.user_id}"
    )

    print(
        "\nSUMMARY"
    )

    print(
        f"  {explanation.summary}"
    )

    print(
        "\nFINANCIAL IMPACT"
    )

    for item in (
        explanation.financial_impact
    ):

        print(
            f"  - {item}"
        )

    print(
        "\nRECOMMENDATION"
    )

    print(
        f"  {explanation.recommendation}"
    )

    if explanation.reasons:

        print(
            "\nWHY"
        )

        for reason in (
            explanation.reasons
        ):

            print(
                f"  - {reason}"
            )

    if explanation.warnings:

        print(
            "\nWARNINGS"
        )

        for warning in (
            explanation.warnings
        ):

            print(
                f"  - {warning}"
            )

    if explanation.confidence:

        print(
            f"\nConfidence: "
            f"{explanation.confidence:.2f}"
        )

    print()
    print("=" * 70)

    print(
        "MODEL 10: SUCCESS"
    )

    print(
        "=" * 70
    )


# ============================================================
# TEST WITH MODEL 7
# ============================================================

if __name__ == "__main__":

    from ..agent.financial_agent import (
        FinancialAgent,
    )

    print("=" * 70)
    print(
        "BUY OR WAIT? - MODEL 10"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Run complete agent
    # --------------------------------------------------------

    agent = FinancialAgent(
        dataset_path="dataset"
    )

    result = agent.run(
        "request_26"
    )

    # --------------------------------------------------------
    # Explain Model 7 result
    # --------------------------------------------------------

    engine = ExplanationEngine()

    explanation = engine.explain(
        result
    )

    # --------------------------------------------------------
    # Print
    # --------------------------------------------------------

    print_explanation(
        explanation
    )