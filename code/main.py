"""
BUY OR WAIT?
Challenge-facing application.

Runs the complete Financial Agent and returns
a clean JSON-compatible response.
"""

from __future__ import annotations

import json
import sys

from .agent.financial_agent import FinancialAgent


# ============================================================
# AGENT
# ============================================================

agent = FinancialAgent(
    dataset_path="dataset"
)


# ============================================================
# PROCESS REQUEST
# ============================================================

def process_request(
    request_id: str,
):

    result = agent.run(
        request_id
    )

    return result


# ============================================================
# PRINT JSON
# ============================================================

def print_json(
    result,
):

    print(
        json.dumps(
            result,
            indent=2,
            default=str,
        )
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Command-line request
    # --------------------------------------------------------

    if len(sys.argv) > 1:

        request_id = sys.argv[1]

    else:

        request_id = "request_26"

    try:

        result = process_request(
            request_id
        )

        print_json(
            result
        )

    except Exception as exc:

        error = {
            "success": False,
            "error": type(
                exc
            ).__name__,
            "message": str(
                exc
            ),
        }

        print_json(
            error
        )

        raise


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()