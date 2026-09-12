"""
Model 3: Evidence Resolution Agent
==================================

Purpose
-------
Resolve incomplete or uncertain financial events using:

1. financial_events.csv
2. messages.csv
3. images.csv
4. image files referenced by images.csv

This model sits between:

    Model 2: Financial State Reconstruction
                    |
                    v
    Model 3: Evidence Resolution
                    |
                    v
    Model 4: 90-Day Forecast

Important principles
--------------------
- Never convert a missing amount into zero.
- Prefer structured financial_events.csv values.
- Use linked messages as supporting evidence.
- Use image evidence when an event amount is missing.
- Keep unresolved evidence explicit.
- Preserve the original event.
- Record the source of every resolved value.
- Do not make the final Buy/Wait decision here.

The model is intentionally conservative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .data_loader import DatasetLoader
from .financial_state import (
    FinancialEvent,
    FinancialState,
    FinancialStateBuilder,
)


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class EvidenceItem:
    """
    One piece of evidence associated with a financial event.
    """

    evidence_id: str

    event_id: Optional[str]

    evidence_type: str
    # "message", "image", "structured_event"

    source_file: Optional[str]

    source_reference: Optional[str]

    text: Optional[str]

    image_path: Optional[str]

    confidence: float

    extracted_amount: Optional[float]

    currency: Optional[str]

    extracted_status: Optional[str]

    notes: List[str] = field(
        default_factory=list
    )


@dataclass
class ResolvedEvent:
    """
    Financial event after evidence resolution.
    """

    event: FinancialEvent

    resolved_amount: Optional[float]

    resolved_currency: Optional[str]

    resolved_status: Optional[str]

    amount_source: Optional[str]

    status_source: Optional[str]

    amount_confidence: float

    status_confidence: float

    messages: List[EvidenceItem] = field(
        default_factory=list
    )

    images: List[EvidenceItem] = field(
        default_factory=list
    )

    warnings: List[str] = field(
        default_factory=list
    )

    amount_resolved: bool = False

    status_resolved: bool = False

    has_conflicting_evidence: bool = False


# ============================================================
# EVIDENCE RESOLVER
# ============================================================

class EvidenceResolver:
    """
    Resolve incomplete financial events.

    The resolver uses the DatasetLoader created in Model 1
    and the FinancialState created in Model 2.

    Example
    -------
        loader = DatasetLoader("dataset")
        loader.load()

        state_builder = FinancialStateBuilder(loader)

        state = state_builder.build(
            user_id="user_26",
            as_of_date=pd.Timestamp("2025-08-03")
        )

        resolver = EvidenceResolver(loader)

        resolved = resolver.resolve_state(state)

        for item in resolved:
            print(item.resolved_amount)
    """

    def __init__(
        self,
        loader: DatasetLoader,
        image_root: Optional[str] = None,
    ) -> None:

        self.loader = loader

        if self.loader.data is None:
            raise RuntimeError(
                "DatasetLoader must be loaded before "
                "EvidenceResolver can be used."
            )

        self.data = self.loader.data

        self.image_root = (
            Path(image_root)
            if image_root
            else Path("dataset/media/images")
        )

        self._messages = self._get_dataframe(
            "messages"
        )

        self._images = self._get_dataframe(
            "images"
        )

        self._events = self._get_dataframe(
            "financial_events"
        )

    # ========================================================
    # PUBLIC API
    # ========================================================

    def resolve_state(
        self,
        state: FinancialState,
    ) -> List[ResolvedEvent]:
        """
        Resolve all events belonging to the state user.
        """

        resolved_events = []

        for event in state.events:

            resolved = self.resolve_event(
                event
            )

            resolved_events.append(
                resolved
            )

        return resolved_events

    def resolve_event(
        self,
        event: FinancialEvent,
    ) -> ResolvedEvent:
        """
        Resolve one financial event using all available evidence.
        """

        result = ResolvedEvent(
            event=event,
            resolved_amount=event.amount,
            resolved_currency=event.currency,
            resolved_status=event.status,
            amount_source=(
                "financial_events.csv"
                if event.amount is not None
                else None
            ),
            status_source=(
                "financial_events.csv"
                if event.status
                else None
            ),
            amount_confidence=(
                1.0
                if event.amount is not None
                else 0.0
            ),
            status_confidence=(
                1.0
                if event.status
                else 0.0
            ),
        )

        # ----------------------------------------------------
        # Structured event evidence
        # ----------------------------------------------------

        structured_evidence = self._structured_evidence(
            event
        )

        if structured_evidence:
            result.amount_confidence = max(
                result.amount_confidence,
                1.0,
            )

        # ----------------------------------------------------
        # Messages
        # ----------------------------------------------------

        messages = self._find_messages(
            event.event_id
        )

        result.messages = messages

        # ----------------------------------------------------
        # Resolve amount from messages if necessary
        # ----------------------------------------------------

        if result.resolved_amount is None:

            amount_candidates = []

            for message in messages:

                if (
                    message.extracted_amount
                    is not None
                ):
                    amount_candidates.append(
                        message
                    )

            if amount_candidates:

                best = self._choose_best_evidence(
                    amount_candidates
                )

                result.resolved_amount = (
                    best.extracted_amount
                )

                result.resolved_currency = (
                    result.resolved_currency
                    or best.currency
                )

                result.amount_source = (
                    "messages.csv"
                )

                result.amount_confidence = (
                    best.confidence
                )

        # ----------------------------------------------------
        # Resolve status from messages
        # ----------------------------------------------------

        if (
            result.resolved_status is None
            or result.resolved_status
            in {
                "",
                "unknown",
            }
        ):

            status_candidates = []

            for message in messages:

                if message.extracted_status:

                    status_candidates.append(
                        message
                    )

            if status_candidates:

                best = self._choose_best_evidence(
                    status_candidates
                )

                result.resolved_status = (
                    best.extracted_status
                )

                result.status_source = (
                    "messages.csv"
                )

                result.status_confidence = (
                    best.confidence
                )

        # ----------------------------------------------------
        # Images
        # ----------------------------------------------------

        images = self._find_images(
            event.event_id
        )

        result.images = images

        # ----------------------------------------------------
        # Resolve amount from image metadata / OCR text
        # ----------------------------------------------------

        if result.resolved_amount is None:

            image_candidates = []

            for image in images:

                if (
                    image.extracted_amount
                    is not None
                ):
                    image_candidates.append(
                        image
                    )

            if image_candidates:

                best = self._choose_best_evidence(
                    image_candidates
                )

                result.resolved_amount = (
                    best.extracted_amount
                )

                result.resolved_currency = (
                    result.resolved_currency
                    or best.currency
                )

                result.amount_source = (
                    "images.csv"
                )

                result.amount_confidence = (
                    best.confidence
                )

        # ----------------------------------------------------
        # Detect conflicts
        # ----------------------------------------------------

        self._detect_conflicts(
            result
        )

        # ----------------------------------------------------
        # Final resolution status
        # ----------------------------------------------------

        result.amount_resolved = (
            result.resolved_amount is not None
        )

        result.status_resolved = (
            result.resolved_status is not None
        )

        # ----------------------------------------------------
        # Warnings
        # ----------------------------------------------------

        if not result.amount_resolved:

            result.warnings.append(
                "Amount could not be resolved "
                "from structured, message, or "
                "image evidence."
            )

        if result.has_conflicting_evidence:

            result.warnings.append(
                "Conflicting evidence detected. "
                "The strongest source was retained, "
                "but the conflict should be reviewed "
                "by downstream reasoning."
            )

        return result

    # ========================================================
    # MESSAGE HANDLING
    # ========================================================

    def _find_messages(
        self,
        event_id: str,
    ) -> List[EvidenceItem]:
        """
        Find messages linked to an event.

        Primary relationship:
            messages.linked_event_id
                ->
            financial_events.event_id
        """

        if self._messages.empty:
            return []

        messages = self._messages.copy()

        # ----------------------------------------------------
        # Exact linked event ID.
        # ----------------------------------------------------

        if "linked_event_id" in messages.columns:

            matched = messages[
                messages[
                    "linked_event_id"
                ].astype(str)
                == str(event_id)
            ]

        else:
            matched = pd.DataFrame()

        evidence = []

        for index, row in matched.iterrows():

            text = self._extract_message_text(
                row
            )

            amount = self._extract_amount_from_text(
                text
            )

            currency = self._extract_currency(
                text
            )

            status = self._extract_status(
                text
            )

            evidence.append(
                EvidenceItem(
                    evidence_id=f"message_{index}",
                    event_id=event_id,
                    evidence_type="message",
                    source_file="messages.csv",
                    source_reference=str(index),
                    text=text,
                    image_path=None,
                    confidence=0.75,
                    extracted_amount=amount,
                    currency=currency,
                    extracted_status=status,
                )
            )

        return evidence

    # ========================================================
    # IMAGE HANDLING
    # ========================================================

    def _find_images(
        self,
        event_id: str,
    ) -> List[EvidenceItem]:
        """
        Find image evidence connected to an event.

        The exact mapping depends on images.csv.

        We support common mappings such as:

            event_id
            linked_event_id
            image_id
        """

        if self._images.empty:
            return []

        images = self._images.copy()

        matched = pd.DataFrame()

        # ----------------------------------------------------
        # Direct event mapping.
        # ----------------------------------------------------

        if "event_id" in images.columns:

            matched = images[
                images[
                    "event_id"
                ].astype(str)
                == str(event_id)
            ]

        # ----------------------------------------------------
        # Linked event mapping.
        # ----------------------------------------------------

        elif "linked_event_id" in images.columns:

            matched = images[
                images[
                    "linked_event_id"
                ].astype(str)
                == str(event_id)
            ]

        evidence = []

        for index, row in matched.iterrows():

            image_id = self._string(
                row.get("image_id")
            )

            image_path = (
                self._resolve_image_path(
                    image_id
                )
                if image_id
                else None
            )

            text = self._extract_image_text(
                row
            )

            amount = self._extract_amount_from_text(
                text
            )

            currency = self._extract_currency(
                text
            )

            status = self._extract_status(
                text
            )

            notes = []

            if image_path is None:

                notes.append(
                    "Image file path could not "
                    "be resolved."
                )

            evidence.append(
                EvidenceItem(
                    evidence_id=(
                        f"image_{index}"
                    ),
                    event_id=event_id,
                    evidence_type="image",
                    source_file="images.csv",
                    source_reference=str(index),
                    text=text,
                    image_path=image_path,
                    confidence=0.70,
                    extracted_amount=amount,
                    currency=currency,
                    extracted_status=status,
                    notes=notes,
                )
            )

        return evidence

    # ========================================================
    # IMAGE PATH
    # ========================================================

    def _resolve_image_path(
        self,
        image_id: str,
    ) -> Optional[str]:
        """
        Resolve image ID to a local image path.

        Supports common image extensions.
        """

        if not image_id:
            return None

        extensions = [
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        ]

        for extension in extensions:

            candidate = (
                self.image_root
                / f"{image_id}{extension}"
            )

            if candidate.exists():

                return str(
                    candidate
                )

        # ----------------------------------------------------
        # Search recursively if direct path isn't found.
        # ----------------------------------------------------

        if self.image_root.exists():

            for extension in extensions:

                matches = list(
                    self.image_root.rglob(
                        f"{image_id}{extension}"
                    )
                )

                if matches:

                    return str(
                        matches[0]
                    )

        return None

    # ========================================================
    # IMAGE TEXT
    # ========================================================

    def _extract_image_text(
        self,
        row: pd.Series,
    ) -> Optional[str]:
        """
        Extract any textual evidence already stored in
        images.csv.

        We intentionally DO NOT perform OCR here unless
        the dataset explicitly provides OCR text.

        A later multimodal model can process the actual
        image file.
        """

        possible_columns = [
            "text",
            "ocr_text",
            "extracted_text",
            "description",
            "caption",
        ]

        values = []

        for column in possible_columns:

            if column not in row.index:
                continue

            value = self._string(
                row.get(column)
            )

            if value:
                values.append(
                    value
                )

        if not values:
            return None

        return " ".join(
            values
        )

    # ========================================================
    # STRUCTURED EVIDENCE
    # ========================================================

    def _structured_evidence(
        self,
        event: FinancialEvent,
    ) -> List[EvidenceItem]:
        """
        Represent the CSV event itself as evidence.
        """

        return [
            EvidenceItem(
                evidence_id=event.event_id,
                event_id=event.event_id,
                evidence_type="structured_event",
                source_file="financial_events.csv",
                source_reference=event.event_id,
                text=event.description,
                image_path=None,
                confidence=1.0,
                extracted_amount=event.amount,
                currency=event.currency,
                extracted_status=event.status,
            )
        ]

    # ========================================================
    # AMOUNT EXTRACTION
    # ========================================================

    @classmethod
    def _extract_amount_from_text(
        cls,
        text: Optional[str],
    ) -> Optional[float]:
        """
        Extract an amount from message/OCR text.

        This is intentionally conservative.

        Supported examples:

            $1,250
            USD 1250
            1,250 USD
            IDR 2,500,000
            ₹50,000
            50,000 INR
            R50,000
            50000

        Bare numbers are only accepted when they appear
        financially meaningful in the surrounding text.
        """

        if not text:
            return None

        # ----------------------------------------------------
        # Currency-prefixed amount.
        # ----------------------------------------------------

        currency_pattern = re.compile(
            r"""
            (?:
                [$₹€£¥]
                |
                \b(?:USD|EUR|GBP|INR|IDR|ZAR|SGD|AUD|CAD|JPY)\b
            )
            \s*
            ([0-9][0-9,]*(?:\.[0-9]+)?)
            """,
            re.IGNORECASE | re.VERBOSE,
        )

        match = currency_pattern.search(
            text
        )

        if match:

            return cls._parse_number(
                match.group(1)
            )

        # ----------------------------------------------------
        # Amount followed by currency.
        # ----------------------------------------------------

        suffix_pattern = re.compile(
            r"""
            ([0-9][0-9,]*(?:\.[0-9]+)?)
            \s*
            \b(?:USD|EUR|GBP|INR|IDR|ZAR|SGD|AUD|CAD|JPY)\b
            """,
            re.IGNORECASE | re.VERBOSE,
        )

        match = suffix_pattern.search(
            text
        )

        if match:

            return cls._parse_number(
                match.group(1)
            )

        # ----------------------------------------------------
        # Financial keywords + number.
        # ----------------------------------------------------

        keyword_pattern = re.compile(
            r"""
            (?:
                amount
                |
                salary
                |
                payment
                |
                paid
                |
                price
                |
                cost
                |
                refund
                |
                rent
                |
                installment
                |
                deposit
                |
                transfer
            )
            [^\d]{0,30}
            ([0-9][0-9,]*(?:\.[0-9]+)?)
            """,
            re.IGNORECASE | re.VERBOSE,
        )

        match = keyword_pattern.search(
            text
        )

        if match:

            return cls._parse_number(
                match.group(1)
            )

        return None

    # ========================================================
    # CURRENCY EXTRACTION
    # ========================================================

    @staticmethod
    def _extract_currency(
        text: Optional[str],
    ) -> Optional[str]:

        if not text:
            return None

        pattern = re.compile(
            r"\b(USD|EUR|GBP|INR|IDR|ZAR|SGD|AUD|CAD|JPY)\b",
            re.IGNORECASE,
        )

        match = pattern.search(
            text
        )

        if match:

            return match.group(1).upper()

        symbol_map = {
            "$": "USD",
            "₹": "INR",
            "€": "EUR",
            "£": "GBP",
            "¥": "JPY",
        }

        for symbol, currency in symbol_map.items():

            if symbol in text:

                return currency

        return None

    # ========================================================
    # STATUS EXTRACTION
    # ========================================================

    @staticmethod
    def _extract_status(
        text: Optional[str],
    ) -> Optional[str]:

        if not text:
            return None

        text_normalized = (
            text.lower()
        )

        status_keywords = [
            (
                "cancelled",
                "cancelled",
            ),
            (
                "canceled",
                "cancelled",
            ),
            (
                "failed",
                "failed",
            ),
            (
                "pending",
                "pending",
            ),
            (
                "scheduled",
                "scheduled",
            ),
            (
                "settled",
                "settled",
            ),
            (
                "completed",
                "settled",
            ),
            (
                "paid",
                "settled",
            ),
            (
                "declined",
                "failed",
            ),
        ]

        for keyword, status in status_keywords:

            if keyword in text_normalized:

                return status

        return None

    # ========================================================
    # CONFLICT DETECTION
    # ========================================================

    def _detect_conflicts(
        self,
        result: ResolvedEvent,
    ) -> None:
        """
        Detect disagreements between message/image evidence.

        We don't silently overwrite structured data.
        """

        amounts = []

        if result.event.amount is not None:

            amounts.append(
                (
                    "financial_events.csv",
                    float(
                        result.event.amount
                    ),
                )
            )

        for item in result.messages:

            if item.extracted_amount is not None:

                amounts.append(
                    (
                        "messages.csv",
                        float(
                            item.extracted_amount
                        ),
                    )
                )

        for item in result.images:

            if item.extracted_amount is not None:

                amounts.append(
                    (
                        "images.csv",
                        float(
                            item.extracted_amount
                        ),
                    )
                )

        if len(amounts) < 2:
            return

        unique_amounts = {
            round(
                amount,
                2,
            )
            for _, amount in amounts
        }

        if len(unique_amounts) > 1:

            result.has_conflicting_evidence = True

            result.warnings.append(
                "Different amounts were found "
                "across evidence sources: "
                + str(amounts)
            )

        statuses = []

        if result.event.status:

            statuses.append(
                (
                    "financial_events.csv",
                    result.event.status,
                )
            )

        for item in result.messages:

            if item.extracted_status:

                statuses.append(
                    (
                        "messages.csv",
                        item.extracted_status,
                    )
                )

        for item in result.images:

            if item.extracted_status:

                statuses.append(
                    (
                        "images.csv",
                        item.extracted_status,
                    )
                )

        if len(statuses) >= 2:

            unique_statuses = {
                status
                for _, status in statuses
            }

            if len(unique_statuses) > 1:

                result.has_conflicting_evidence = True

                result.warnings.append(
                    "Different statuses were found "
                    "across evidence sources: "
                    + str(statuses)
                )

    # ========================================================
    # EVIDENCE RANKING
    # ========================================================

    @staticmethod
    def _choose_best_evidence(
        evidence: List[EvidenceItem],
    ) -> EvidenceItem:
        """
        Select strongest evidence.

        Ranking:
            confidence
            ↓
            structured financial evidence
            ↓
            message
            ↓
            image
        """

        priority = {
            "structured_event": 3,
            "message": 2,
            "image": 1,
        }

        return max(
            evidence,
            key=lambda item: (
                item.confidence,
                priority.get(
                    item.evidence_type,
                    0,
                ),
            ),
        )

    # ========================================================
    # DATAFRAME HELPERS
    # ========================================================

    def _get_dataframe(
        self,
        name: str,
    ) -> pd.DataFrame:

        try:

            dataframe = getattr(
                self.data,
                name,
            )

            if dataframe is None:
                return pd.DataFrame()

            return dataframe

        except AttributeError:

            return pd.DataFrame()

    # ========================================================
    # TYPE HELPERS
    # ========================================================

    @staticmethod
    def _parse_number(
        value: Any,
    ) -> Optional[float]:

        if value is None:
            return None

        try:

            cleaned = (
                str(value)
                .replace(",", "")
                .strip()
            )

            return float(
                cleaned
            )

        except (
            ValueError,
            TypeError,
        ):

            return None

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

        text = str(
            value
        ).strip()

        return (
            text
            if text
            else None
        )


# ============================================================
# SUMMARY HELPERS
# ============================================================

def summarize_resolved_events(
    events: List[ResolvedEvent],
) -> Dict[str, Any]:
    """
    Generate a compact Model 3 diagnostic summary.
    """

    total = len(events)

    amount_resolved = sum(
        1
        for event in events
        if event.amount_resolved
    )

    status_resolved = sum(
        1
        for event in events
        if event.status_resolved
    )

    unresolved_amounts = sum(
        1
        for event in events
        if not event.amount_resolved
    )

    conflicts = sum(
        1
        for event in events
        if event.has_conflicting_evidence
    )

    messages = sum(
        len(event.messages)
        for event in events
    )

    images = sum(
        len(event.images)
        for event in events
    )

    return {
        "total_events": total,
        "amount_resolved": amount_resolved,
        "amount_unresolved": unresolved_amounts,
        "status_resolved": status_resolved,
        "events_with_conflicts": conflicts,
        "message_evidence_items": messages,
        "image_evidence_items": images,
    }


# ============================================================
# COMMAND-LINE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 70)
    print(
        "BUY OR WAIT? - "
        "MODEL 3: EVIDENCE RESOLUTION"
    )
    print("=" * 70)

    # --------------------------------------------------------
    # Load dataset
    # --------------------------------------------------------

    loader = DatasetLoader(
        "dataset"
    )

    loader.load()

    # --------------------------------------------------------
    # Get first evaluation request
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
        f"Request date: "
        f"{request_date.date()}"
    )

    # --------------------------------------------------------
    # Build Model 2 state
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
    # Summary
    # --------------------------------------------------------

    summary = summarize_resolved_events(
        resolved_events
    )

    print(
        "\nEvidence resolution summary:"
    )

    for key, value in summary.items():

        print(
            f"  {key}: {value}"
        )

    # --------------------------------------------------------
    # Show unresolved events
    # --------------------------------------------------------

    unresolved = [
        event
        for event in resolved_events
        if not event.amount_resolved
    ]

    print(
        "\nEvents with unresolved amounts:"
    )

    if not unresolved:

        print(
            "  None"
        )

    else:

        for item in unresolved[:20]:

            print(
                f"  {item.event.event_id} | "
                f"{item.event.description}"
            )

            for warning in item.warnings:

                print(
                    f"      WARNING: {warning}"
                )

    # --------------------------------------------------------
    # Show evidence
    # --------------------------------------------------------

    print(
        "\nEvents with external evidence:"
    )

    evidence_events = [
        event
        for event in resolved_events
        if event.messages
        or event.images
    ]

    if not evidence_events:

        print(
            "  No linked message/image evidence "
            "found for this user."
        )

    else:

        for item in evidence_events[:10]:

            print(
                f"  Event: "
                f"{item.event.event_id}"
            )

            print(
                f"    Amount: "
                f"{item.resolved_amount}"
            )

            print(
                f"    Source: "
                f"{item.amount_source}"
            )

            print(
                f"    Messages: "
                f"{len(item.messages)}"
            )

            print(
                f"    Images: "
                f"{len(item.images)}"
            )

    print(
        "\n" + "=" * 70
    )

    print(
        "MODEL 3 EVIDENCE RESOLUTION: SUCCESS"
    )

    print(
        "=" * 70
    )