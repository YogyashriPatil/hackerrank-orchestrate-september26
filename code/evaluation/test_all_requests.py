"""
Model 9: Batch Evaluation / Test Harness

Runs the complete Financial Agent against every request
in the dataset.

This is a validation layer, not a decision model.
"""

from __future__ import annotations

import traceback
from collections import Counter

import pandas as pd

from ..agent.financial_agent import FinancialAgent


# ============================================================
# REQUIRED OUTPUT FIELDS
# ============================================================

REQUIRED_FIELDS = [
    "request_id",
    "user_id",
    "decision",
    "safe_amount",
    "requested_amount",
    "currency",
    "payment_method",
    "payment_option_id",
    "payment_plan",
    "earliest_safe_date",
    "spending_changes",
    "reasons",
    "warnings",
    "confidence",
]


# ============================================================
# VALIDATE ONE RESULT
# ============================================================

def validate_result(result):

    errors = []

    # Required fields
    for field in REQUIRED_FIELDS:

        if field not in result:

            errors.append(
                f"missing field: {field}"
            )

    # Decision
    valid_decisions = {
        "affordable_now",
        "affordable_with_plan",
        "affordable_later",
        "not_affordable",
    }

    if (
        "decision" in result
        and result["decision"]
        not in valid_decisions
    ):

        errors.append(
            "invalid decision: "
            f"{result['decision']}"
        )

    # Numeric checks
    if "safe_amount" in result:

        if result["safe_amount"] < 0:

            errors.append(
                "safe_amount is negative"
            )

    if "requested_amount" in result:

        if result["requested_amount"] < 0:

            errors.append(
                "requested_amount is negative"
            )

    # Confidence
    if "confidence" in result:

        confidence = result["confidence"]

        if not (
            0 <= confidence <= 1
        ):

            errors.append(
                "confidence must be between 0 and 1"
            )

    # Reasons
    if "reasons" in result:

        if not isinstance(
            result["reasons"],
            list,
        ):

            errors.append(
                "reasons must be a list"
            )

    return errors


# ============================================================
# RUN ALL REQUESTS
# ============================================================

def run_all():

    print("=" * 70)
    print(
        "MODEL 9: BATCH EVALUATION"
    )
    print("=" * 70)

    agent = FinancialAgent(
        dataset_path="dataset"
    )

    requests = (
        agent.loader.data.requests
    )

    total = len(requests)

    print(
        f"\nTotal requests: {total}"
    )

    successful = 0
    failed = 0
    invalid = 0

    results = []

    decision_counter = Counter()

    # --------------------------------------------------------
    # Process every request
    # --------------------------------------------------------

    for index, row in requests.iterrows():

        request_id = str(
            row["request_id"]
        )

        print(
            f"\n[{index + 1}/{total}] "
            f"{request_id}",
            end=" "
        )

        try:

            result = agent.run(
                request_id
            )

            errors = validate_result(
                result
            )

            if errors:

                invalid += 1

                print(
                    "INVALID"
                )

                for error in errors:

                    print(
                        f"    - {error}"
                    )

            else:

                successful += 1

                decision = result[
                    "decision"
                ]

                decision_counter[
                    decision
                ] += 1

                print(
                    f"OK -> {decision}"
                )

            results.append(
                result
            )

        except Exception as exc:

            failed += 1

            print(
                "FAILED"
            )

            print(
                f"    {type(exc).__name__}: "
                f"{exc}"
            )

            traceback.print_exc()

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 70)
    print(
        "EVALUATION SUMMARY"
    )
    print("=" * 70)

    print(
        f"\nTotal requests: "
        f"{total}"
    )

    print(
        f"Successful: "
        f"{successful}"
    )

    print(
        f"Invalid outputs: "
        f"{invalid}"
    )

    print(
        f"Failed: "
        f"{failed}"
    )

    if total:

        success_rate = (
            successful / total
        ) * 100

        print(
            f"Success rate: "
            f"{success_rate:.2f}%"
        )

    # --------------------------------------------------------
    # Decision distribution
    # --------------------------------------------------------

    print(
        "\nDecision distribution:"
    )

    if decision_counter:

        for decision, count in (
            decision_counter.most_common()
        ):

            percentage = (
                count / successful * 100
                if successful
                else 0
            )

            print(
                f"  {decision}: "
                f"{count} "
                f"({percentage:.2f}%)"
            )

    else:

        print(
            "  No valid decisions."
        )

    # --------------------------------------------------------
    # Average confidence
    # --------------------------------------------------------

    if results:

        confidence_values = [
            r["confidence"]
            for r in results
            if (
                isinstance(r, dict)
                and "confidence" in r
            )
        ]

        if confidence_values:

            average_confidence = (
                sum(confidence_values)
                / len(confidence_values)
            )

            print(
                f"\nAverage confidence: "
                f"{average_confidence:.2f}"
            )

    # ========================================================
    # SAVE RESULTS
    # ========================================================

    if results:

        output = pd.DataFrame(
            results
        )

        output_path = (
            "evaluation_results.csv"
        )

        output.to_csv(
            output_path,
            index=False,
        )

        print(
            f"\nResults saved to: "
            f"{output_path}"
        )

    print()
    print("=" * 70)

    if (
        failed == 0
        and invalid == 0
    ):

        print(
            "MODEL 9: ALL REQUESTS PASSED"
        )

    else:

        print(
            "MODEL 9: ISSUES FOUND"
        )

    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    run_all()