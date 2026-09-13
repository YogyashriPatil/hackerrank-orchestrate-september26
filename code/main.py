"""
Buy or Wait?
Final submission entry point.

Reads every request from dataset/requests.csv,
runs the Financial Agent, validates the result,
and writes output.csv in the repository root.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .agent.financial_agent import FinancialAgent


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATASET = ROOT / "dataset"

REQUESTS_FILE = DATASET / "requests.csv"

OUTPUT_FILE = ROOT / "output.csv"


# ============================================================
# REQUIRED OUTPUT COLUMNS
# ============================================================

OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]


# ============================================================
# CONVERT AGENT RESULT TO SUBMISSION ROW
# ============================================================

def make_output_row(result):

    decision = result.get(
        "decision",
        "not_affordable",
    )

    requested_amount = float(
        result.get(
            "requested_amount",
            0,
        )
    )

    safe_amount = float(
        result.get(
            "safe_amount",
            0,
        )
    )

    # --------------------------------------------------------
    # Safety bound
    # --------------------------------------------------------

    safe_amount = max(
        0.0,
        min(
            safe_amount,
            requested_amount,
        ),
    )

    # --------------------------------------------------------
    # Payment plan
    # --------------------------------------------------------

    payment_plan = result.get(
        "payment_plan"
    )

    if not payment_plan:

        payment_plan = "none"

    # --------------------------------------------------------
    # Spending changes
    # --------------------------------------------------------

    spending_changes = result.get(
        "spending_changes",
        [],
    )

    if not spending_changes:

        spending_changes_value = "none"

    elif isinstance(
        spending_changes,
        list,
    ):

        spending_changes_value = "|".join(
            str(x)
            for x in spending_changes
        )

    else:

        spending_changes_value = str(
            spending_changes
        )

    # --------------------------------------------------------
    # Earliest date
    # --------------------------------------------------------

    earliest_date = result.get(
        "earliest_safe_date"
    )

    if earliest_date is None:

        earliest_date = ""

    # --------------------------------------------------------
    # Explanation
    # --------------------------------------------------------

    reasons = result.get(
        "reasons",
        [],
    )

    recommendation = result.get(
        "recommendation",
        "",
    )

    summary = result.get(
        "summary",
        "",
    )

    explanation_parts = []

    if summary:

        explanation_parts.append(
            str(summary)
        )

    if recommendation:

        explanation_parts.append(
            str(recommendation)
        )

    if reasons:

        if isinstance(
            reasons,
            list,
        ):

            explanation_parts.extend(
                str(x)
                for x in reasons
            )

        else:

            explanation_parts.append(
                str(reasons)
            )

    decision_explanation = " ".join(
        explanation_parts
    )

    # --------------------------------------------------------
    # Return exact submission schema
    # --------------------------------------------------------

    return {
        "request_id": result[
            "request_id"
        ],

        "amount_safe_to_pay": safe_amount,

        "affordability_status": decision,

        "recommended_payment_method": (
            result.get(
                "payment_method"
            )
            or "not_recommended"
        ),

        "payment_plan": payment_plan,

        "earliest_date_for_full_payment": (
            earliest_date
        ),

        "spending_changes_needed": (
            spending_changes_value
        ),

        "decision_explanation": (
            decision_explanation
        ),
    }


# ============================================================
# VALIDATE ROW
# ============================================================

def validate_row(row):

    errors = []

    # Required columns
    if list(row.keys()) != OUTPUT_COLUMNS:

        errors.append(
            "Output columns do not match required schema."
        )

    # Amount
    try:

        amount = float(
            row[
                "amount_safe_to_pay"
            ]
        )

        if amount < 0:

            errors.append(
                "amount_safe_to_pay < 0"
            )

    except Exception:

        errors.append(
            "Invalid amount_safe_to_pay"
        )

    # Status
    allowed_statuses = {
        "affordable_now",
        "affordable_with_plan",
        "affordable_later",
        "not_affordable",
    }

    if (
        row[
            "affordability_status"
        ]
        not in allowed_statuses
    ):

        errors.append(
            "Invalid affordability_status"
        )

    # Payment method
    allowed_methods = {
        "full_payment",
        "partial_payment",
        "installments",
        "wait",
        "not_recommended",
    }

    if (
        row[
            "recommended_payment_method"
        ]
        not in allowed_methods
    ):

        errors.append(
            "Invalid recommended_payment_method"
        )

    return errors


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("BUY OR WAIT?")
    print("FINAL FULL-DATASET GENERATION")
    print("=" * 70)

    # --------------------------------------------------------
    # Load agent
    # --------------------------------------------------------

    agent = FinancialAgent(
        dataset_path=str(
            DATASET
        )
    )

    # --------------------------------------------------------
    # Read requests
    # --------------------------------------------------------

    with open(
        REQUESTS_FILE,
        "r",
        encoding="utf-8",
        newline="",
    ) as f:

        requests = list(
            csv.DictReader(f)
        )

    print(
        f"\nRequests found: "
        f"{len(requests)}"
    )

    if not requests:

        raise RuntimeError(
            "requests.csv is empty."
        )

    # --------------------------------------------------------
    # Run every request
    # --------------------------------------------------------

    output_rows = []

    failures = []

    for index, request in enumerate(
        requests,
        start=1,
    ):

        request_id = request[
            "request_id"
        ]

        print(
            f"[{index}/{len(requests)}] "
            f"{request_id}",
            end=" "
        )

        try:

            result = agent.run(
                request_id
            )

            row = make_output_row(
                result
            )

            errors = validate_row(
                row
            )

            if errors:

                failures.append(
                    (
                        request_id,
                        errors,
                    )
                )

                print(
                    "INVALID"
                )

                continue

            output_rows.append(
                row
            )

            print(
                f"OK -> "
                f"{row['affordability_status']}"
            )

        except Exception as exc:
            failures.append(
                (
                    request_id,
                    [
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ],
                )
            )

            print(
                f"FAILED -> "
                f"{type(exc).__name__}: {exc}"
            )
    # --------------------------------------------------------
    # Check row count
    # --------------------------------------------------------

    if len(output_rows) != len(
        requests
    ):

        raise RuntimeError(
            f"Only {len(output_rows)} "
            f"of {len(requests)} requests "
            f"produced valid output."
        )

    if failures:

        raise RuntimeError(
            f"{len(failures)} requests failed."
        )

    # --------------------------------------------------------
    # Write output.csv
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
        newline="",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=OUTPUT_COLUMNS,
        )

        writer.writeheader()

        writer.writerows(
            output_rows
        )

    # --------------------------------------------------------
    # Final verification
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "r",
        encoding="utf-8",
        newline="",
    ) as f:

        generated = list(
            csv.DictReader(f)
        )

    print()
    print("=" * 70)
    print("FINAL VALIDATION")
    print("=" * 70)

    print(
        f"Expected rows: "
        f"{len(requests)}"
    )

    print(
        f"Generated rows: "
        f"{len(generated)}"
    )

    print(
        f"Columns: "
        f"{list(generated[0].keys())}"
    )

    if (
        len(generated)
        != len(requests)
    ):

        raise RuntimeError(
            "Output row count mismatch."
        )

    if (
        list(generated[0].keys())
        != OUTPUT_COLUMNS
    ):

        raise RuntimeError(
            "Output column mismatch."
        )

    print(
        "\noutput.csv successfully generated."
    )

    print(
        f"Location: {OUTPUT_FILE}"
    )

    print()
    print("=" * 70)
    print("FINAL SUBMISSION OUTPUT: SUCCESS")
    print("=" * 70)


if __name__ == "__main__":

    main()