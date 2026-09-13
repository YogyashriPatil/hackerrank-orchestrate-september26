# loader loads reads all
# financial_profiles.csv
# financial_events.csv
# exchange_rates.csv
# requests.csv
# sample_requests.csv
# request_payment_options.csv
# messages.csv
# images.csv

"""
Model 1: Dataset Loader
=======================

Loads and validates all participant-facing datasets for the
HackerRank Orchestrate - Buy or Wait? challenge.

This module intentionally DOES NOT make financial decisions.

Responsibilities:
    1. Load CSV files from dataset/
    2. Normalize basic CSV values
    3. Parse dates and numeric values
    4. Build indexes for fast lookups
    5. Provide request/user-specific retrieval helpers
    6. Validate dataset relationships
    7. Resolve image file paths

Later models will consume DatasetLoader rather than reading CSV
files directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


# ============================================================
# DATASET CONFIGURATION
# ============================================================

REQUIRED_FILES = [
    "requests.csv",
    "sample_requests.csv",
    "financial_profiles.csv",
    "financial_events.csv",
    "exchange_rates.csv",
    "request_payment_options.csv",
    "messages.csv",
    "images.csv",
    "output.csv",
]


# ============================================================
# DATASET CONTAINER
# ============================================================

@dataclass
class Dataset:
    """
    Container holding all loaded datasets.

    Each attribute is a pandas DataFrame.
    """

    requests: pd.DataFrame
    sample_requests: pd.DataFrame
    financial_profiles: pd.DataFrame
    financial_events: pd.DataFrame
    exchange_rates: pd.DataFrame
    request_payment_options: pd.DataFrame
    messages: pd.DataFrame
    images: pd.DataFrame
    output_template: pd.DataFrame


# ============================================================
# DATASET LOADER
# ============================================================

class DatasetLoader:
    """
    Model 1: central dataset loading and retrieval layer.

    Example:

        loader = DatasetLoader("dataset")
        loader.load()

        request = loader.request("request_26")

        profile = loader.profile_for_user("user_26")

        events = loader.events_for_user("user_26")

        options = loader.options_for_request("request_26")
    """

    def __init__(self, dataset_dir: str | Path = "dataset") -> None:
        self.dataset_dir = Path(dataset_dir)

        self.data: Optional[Dataset] = None

        # Fast lookup indexes.
        self._profiles_by_user: Dict[str, pd.Series] = {}
        self._events_by_user: Dict[str, pd.DataFrame] = {}
        self._requests_by_id: Dict[str, pd.Series] = {}
        self._sample_requests_by_id: Dict[str, pd.Series] = {}
        self._options_by_request: Dict[str, pd.DataFrame] = {}
        self._messages_by_request: Dict[str, pd.DataFrame] = {}
        self._messages_by_user: Dict[str, pd.DataFrame] = {}
        self._messages_by_event: Dict[str, pd.DataFrame] = {}
        self._images_by_request: Dict[str, pd.DataFrame] = {}
        self._images_by_user: Dict[str, pd.DataFrame] = {}
        self._images_by_event: Dict[str, pd.DataFrame] = {}

    # ========================================================
    # LOAD
    # ========================================================

    def load(self) -> Dataset:
        """
        Load every required CSV file.

        Returns:
            Dataset containing all loaded DataFrames.

        Raises:
            FileNotFoundError:
                If a required dataset file is missing.
            ValueError:
                If required columns are missing.
        """

        self._check_dataset_directory()
        self._check_required_files()

        requests = self._read_csv("requests.csv")
        sample_requests = self._read_csv("sample_requests.csv")
        financial_profiles = self._read_csv("financial_profiles.csv")
        financial_events = self._read_csv("financial_events.csv")
        exchange_rates = self._read_csv("exchange_rates.csv")
        payment_options = self._read_csv("request_payment_options.csv")
        messages = self._read_csv("messages.csv")
        images = self._read_csv("images.csv")
        output_template = self._read_csv("output.csv")

        # Basic normalization.
        requests = self._normalize_dataframe(requests)
        sample_requests = self._normalize_dataframe(sample_requests)
        financial_profiles = self._normalize_dataframe(financial_profiles)
        financial_events = self._normalize_dataframe(financial_events)
        exchange_rates = self._normalize_dataframe(exchange_rates)
        payment_options = self._normalize_dataframe(payment_options)
        messages = self._normalize_dataframe(messages)
        images = self._normalize_dataframe(images)
        output_template = self._normalize_dataframe(output_template)

        # Parse common dates.
        requests = self._parse_dates(
            requests,
            [
                "request_date",
                "desired_completion_date",
            ],
        )

        sample_requests = self._parse_dates(
            sample_requests,
            [
                "request_date",
                "desired_completion_date",
            ],
        )

        financial_profiles = self._parse_dates(
            financial_profiles,
            [
                "profile_date",
            ],
        )

        financial_events = self._parse_dates(
            financial_events,
            [
                "event_date",
                "settlement_date",
                "start_date",
                "end_date",
            ],
        )

        exchange_rates = self._parse_dates(
            exchange_rates,
            [
                "rate_date",
                "date",
            ],
        )

        payment_options = self._parse_dates(
            payment_options,
            [
                "start_date",
                "payment_start_date",
            ],
        )

        messages = self._parse_dates(
            messages,
            [
                "message_date",
                "created_at",
                "timestamp",
            ],
        )

        images = self._parse_dates(
            images,
            [
                "image_date",
                "created_at",
                "timestamp",
            ],
        )

        # Parse numeric columns without assuming every possible
        # optional column exists.
        requests = self._parse_numeric(
            requests,
            [
                "requested_amount",
            ],
        )

        sample_requests = self._parse_numeric(
            sample_requests,
            [
                "requested_amount",
                "amount_safe_to_pay",
            ],
        )

        financial_profiles = self._parse_numeric(
            financial_profiles,
            [
                "available_balance",
                "current_balance",
                "minimum_balance_to_keep",
                "max_installment_months",
            ],
        )

        financial_events = self._parse_numeric(
            financial_events,
            [
                "amount",
            ],
        )

        exchange_rates = self._parse_numeric(
            exchange_rates,
            [
                "rate",
                "exchange_rate",
            ],
        )

        payment_options = self._parse_numeric(
            payment_options,
            [
                "total_payable",
                "financing_fee",
                "installment_amount",
                "number_of_payments",
                "days_between_payments",
            ],
        )

        # Build container.
        self.data = Dataset(
            requests=requests,
            sample_requests=sample_requests,
            financial_profiles=financial_profiles,
            financial_events=financial_events,
            exchange_rates=exchange_rates,
            request_payment_options=payment_options,
            messages=messages,
            images=images,
            output_template=output_template,
        )

        # Validate schemas.
        self.validate_schema()

        # Build indexes.
        self._build_indexes()

        return self.data

    # ========================================================
    # FILE HANDLING
    # ========================================================

    def _check_dataset_directory(self) -> None:
        """Check that dataset/ exists."""

        if not self.dataset_dir.exists():
            raise FileNotFoundError(
                f"Dataset directory does not exist: "
                f"{self.dataset_dir.resolve()}"
            )

        if not self.dataset_dir.is_dir():
            raise NotADirectoryError(
                f"Dataset path is not a directory: "
                f"{self.dataset_dir.resolve()}"
            )

    def _check_required_files(self) -> None:
        """Check that every required CSV exists."""

        missing = []

        for filename in REQUIRED_FILES:
            path = self.dataset_dir / filename

            if not path.exists():
                missing.append(str(path))

        if missing:
            raise FileNotFoundError(
                "Missing required dataset files:\n"
                + "\n".join(f"  - {path}" for path in missing)
            )

    def _read_csv(self, filename: str) -> pd.DataFrame:
        """
        Read a CSV using UTF-8.

        dtype=object is intentionally used first so that blank
        amounts are preserved as missing rather than automatically
        converted into zero or otherwise guessed.
        """

        path = self.dataset_dir / filename

        try:
            return pd.read_csv(
                path,
                dtype=object,
                keep_default_na=True,
            )

        except UnicodeDecodeError:
            # Fallback for datasets containing a BOM.
            return pd.read_csv(
                path,
                dtype=object,
                encoding="utf-8-sig",
                keep_default_na=True,
            )

    # ========================================================
    # NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
        """
        Perform safe basic normalization.

        Important:
            This does NOT replace missing amounts with zero.
        """

        result = df.copy()

        # Normalize column names.
        result.columns = [
            str(column).strip()
            for column in result.columns
        ]

        # Strip surrounding whitespace from string cells.
        for column in result.columns:
            if result[column].dtype == object:
                result[column] = result[column].apply(
                    lambda value:
                    value.strip()
                    if isinstance(value, str)
                    else value
                )

        return result

    @staticmethod
    def _parse_dates(
        df: pd.DataFrame,
        columns: List[str],
    ) -> pd.DataFrame:
        """Parse date columns when present."""

        result = df.copy()

        for column in columns:
            if column in result.columns:
                result[column] = pd.to_datetime(
                    result[column],
                    errors="coerce",
                )

        return result

    @staticmethod
    def _parse_numeric(
        df: pd.DataFrame,
        columns: List[str],
    ) -> pd.DataFrame:
        """Parse numeric columns when present."""

        result = df.copy()

        for column in columns:
            if column in result.columns:
                result[column] = pd.to_numeric(
                    result[column],
                    errors="coerce",
                )

        return result

    # ========================================================
    # SCHEMA VALIDATION
    # ========================================================

    def validate_schema(self) -> None:
        """
        Validate that the important challenge columns exist.

        The challenge contains some fields whose exact names can
        vary across optional/supporting data, so validation is
        intentionally focused on the core contract.
        """

        if self.data is None:
            raise RuntimeError(
                "Dataset has not been loaded. Call load() first."
            )

        required_columns = {
            "requests": [
                "request_id",
                "user_id",
                "request_date",
                "request_type",
                "requested_amount",
                "desired_completion_date",
                "allows_partial_payment",
            ],

            "sample_requests": [
                "request_id",
            ],

            "financial_profiles": [
                "user_id",
            ],

            "financial_events": [
                "event_id",
                "user_id",
            ],

            "exchange_rates": [],

            "request_payment_options": [
                "request_id",
            ],

            "messages": [
                "message_id",
                "user_id",
            ],

            "images": [
                "image_id",
                "user_id",
            ],

            "output_template": [
                "request_id",
                "amount_safe_to_pay",
                "affordability_status",
                "recommended_payment_method",
                "payment_plan",
                "earliest_date_for_full_payment",
                "spending_changes_needed",
                "decision_explanation",
            ],
        }

        for dataset_name, columns in required_columns.items():

            dataframe = getattr(
                self.data,
                dataset_name,
            )

            missing = [
                column
                for column in columns
                if column not in dataframe.columns
            ]

            if missing:
                raise ValueError(
                    f"{dataset_name} is missing required "
                    f"columns: {missing}"
                )

    # ========================================================
    # INDEXING
    # ========================================================

    def _build_indexes(self) -> None:
        """Build lookup indexes for later models."""

        if self.data is None:
            raise RuntimeError(
                "Dataset has not been loaded."
            )

        # ----------------------------------------------------
        # Requests
        # ----------------------------------------------------

        self._requests_by_id = {}

        for _, row in self.data.requests.iterrows():
            request_id = self._string_value(
                row.get("request_id")
            )

            if request_id:
                self._requests_by_id[request_id] = row

        # ----------------------------------------------------
        # Sample requests
        # ----------------------------------------------------

        self._sample_requests_by_id = {}

        for _, row in self.data.sample_requests.iterrows():
            request_id = self._string_value(
                row.get("request_id")
            )

            if request_id:
                self._sample_requests_by_id[request_id] = row

        # ----------------------------------------------------
        # Profiles
        # ----------------------------------------------------

        self._profiles_by_user = {}

        for _, row in self.data.financial_profiles.iterrows():
            user_id = self._string_value(
                row.get("user_id")
            )

            if user_id:
                self._profiles_by_user[user_id] = row

        # ----------------------------------------------------
        # Financial events
        # ----------------------------------------------------

        self._events_by_user = self._group_by_column(
            self.data.financial_events,
            "user_id",
        )

        # ----------------------------------------------------
        # Payment options
        # ----------------------------------------------------

        self._options_by_request = self._group_by_column(
            self.data.request_payment_options,
            "request_id",
        )

        # ----------------------------------------------------
        # Messages
        # ----------------------------------------------------

        self._messages_by_request = self._group_by_column(
            self.data.messages,
            "request_id",
        )

        self._messages_by_user = self._group_by_column(
            self.data.messages,
            "user_id",
        )

        self._messages_by_event = self._group_by_column(
            self.data.messages,
            "related_event_id",
        )

        # ----------------------------------------------------
        # Images
        # ----------------------------------------------------

        self._images_by_request = self._group_by_column(
            self.data.images,
            "request_id",
        )

        self._images_by_user = self._group_by_column(
            self.data.images,
            "user_id",
        )

        self._images_by_event = self._group_by_column(
            self.data.images,
            "related_event_id",
        )

    @staticmethod
    def _group_by_column(
        dataframe: pd.DataFrame,
        column: str,
    ) -> Dict[str, pd.DataFrame]:
        """
        Group a DataFrame by a column.

        Rows with blank values are ignored.
        """

        result: Dict[str, pd.DataFrame] = {}

        if column not in dataframe.columns:
            return result

        for key, group in dataframe.groupby(
            column,
            dropna=True,
        ):
            key_string = DatasetLoader._string_value(key)

            if key_string:
                result[key_string] = group.copy()

        return result

    # ========================================================
    # REQUEST LOOKUPS
    # ========================================================

    def request(
        self,
        request_id: str,
    ) -> Optional[pd.Series]:
        """
        Return an evaluation request by request_id.
        """

        return self._requests_by_id.get(
            str(request_id)
        )

    def sample_request(
        self,
        request_id: str,
    ) -> Optional[pd.Series]:
        """
        Return a public sample request.
        """

        return self._sample_requests_by_id.get(
            str(request_id)
        )

    # ========================================================
    # USER LOOKUPS
    # ========================================================

    def profile_for_user(
        self,
        user_id: str,
    ) -> Optional[pd.Series]:
        """
        Return a user's financial profile.
        """

        return self._profiles_by_user.get(
            str(user_id)
        )

    def events_for_user(
        self,
        user_id: str,
    ) -> pd.DataFrame:
        """
        Return all financial events for a user.
        """

        return self._events_by_user.get(
            str(user_id),
            self._empty_dataframe(
                self.data.financial_events
                if self.data is not None
                else None
            ),
        ).copy()
        # ========================================================
    # DIRECT DATAFRAME ACCESS
    # ========================================================

    @property
    def request_payment_options(self) -> pd.DataFrame:
        """
        Return the complete request payment-options dataset.

        This provides backward-compatible access for models
        that expect loader.request_payment_options.
        """
        if self.data is None:
            raise RuntimeError(
                "Dataset has not been loaded. Call load() first."
            )

        return self.data.request_payment_options

    # ========================================================
    # PAYMENT OPTION LOOKUPS
    # ========================================================

    def options_for_request(
        self,
        request_id: str,
    ) -> pd.DataFrame:
        """
        Return all payment options for a request.
        """

        return self._options_by_request.get(
            str(request_id),
            self._empty_dataframe(
                self.data.request_payment_options
                if self.data is not None
                else None
            ),
        ).copy()

    # ========================================================
    # MESSAGE LOOKUPS
    # ========================================================

    def messages_for_request(
        self,
        request_id: str,
        user_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Return messages directly associated with a request.

        If user_id is provided, user-level messages are also
        included.
        """

        frames = []

        request_messages = self._messages_by_request.get(
            str(request_id)
        )

        if request_messages is not None:
            frames.append(request_messages)

        if user_id is not None:
            user_messages = self._messages_by_user.get(
                str(user_id)
            )

            if user_messages is not None:
                frames.append(user_messages)

        return self._combine_unique_rows(
            frames,
            self.data.messages
            if self.data is not None
            else None,
        )

    def messages_for_event(
        self,
        event_id: str,
    ) -> pd.DataFrame:
        """
        Return messages directly associated with an event.
        """

        return self._messages_by_event.get(
            str(event_id),
            self._empty_dataframe(
                self.data.messages
                if self.data is not None
                else None
            ),
        ).copy()

    # ========================================================
    # IMAGE LOOKUPS
    # ========================================================

    def images_for_request(
        self,
        request_id: str,
        user_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Return images associated with a request and optionally
        the user.
        """

        frames = []

        request_images = self._images_by_request.get(
            str(request_id)
        )

        if request_images is not None:
            frames.append(request_images)

        if user_id is not None:
            user_images = self._images_by_user.get(
                str(user_id)
            )

            if user_images is not None:
                frames.append(user_images)

        return self._combine_unique_rows(
            frames,
            self.data.images
            if self.data is not None
            else None,
        )

    def images_for_event(
        self,
        event_id: str,
    ) -> pd.DataFrame:
        """
        Return images associated with an event.
        """

        return self._images_by_event.get(
            str(event_id),
            self._empty_dataframe(
                self.data.images
                if self.data is not None
                else None
            ),
        ).copy()

    # ========================================================
    # IMAGE FILE RESOLUTION
    # ========================================================

    def image_path(
        self,
        image_id: str,
    ) -> Path:
        """
        Resolve an image_id to:

            dataset/media/images/<image_id>.png

        The challenge specification defines this mapping.
        """

        image_id = str(image_id).strip()

        return (
            self.dataset_dir
            / "media"
            / "images"
            / f"{image_id}.png"
        )

    def image_exists(
        self,
        image_id: str,
    ) -> bool:
        """Return whether the physical image exists."""

        return self.image_path(image_id).is_file()

    # ========================================================
    # COMBINED REQUEST CONTEXT
    # ========================================================

    def request_context(
        self,
        request_id: str,
    ) -> Dict[str, Any]:
        """
        Collect the basic records needed by later models.

        This does not perform financial reasoning.
        """

        request = self.request(request_id)

        if request is None:
            raise KeyError(
                f"Unknown request_id: {request_id}"
            )

        user_id = self._string_value(
            request.get("user_id")
        )

        return {
            "request": request,
            "profile": self.profile_for_user(user_id),
            "events": self.events_for_user(user_id),
            "payment_options": self.options_for_request(
                request_id
            ),
            "messages": self.messages_for_request(
                request_id,
                user_id,
            ),
            "images": self.images_for_request(
                request_id,
                user_id,
            ),
        }

    # ========================================================
    # DATASET STATISTICS
    # ========================================================

    def statistics(self) -> Dict[str, int]:
        """
        Return basic dataset sizes.
        """

        if self.data is None:
            raise RuntimeError(
                "Dataset has not been loaded."
            )

        return {
            "requests": len(self.data.requests),
            "sample_requests": len(
                self.data.sample_requests
            ),
            "profiles": len(
                self.data.financial_profiles
            ),
            "financial_events": len(
                self.data.financial_events
            ),
            "exchange_rates": len(
                self.data.exchange_rates
            ),
            "payment_options": len(
                self.data.request_payment_options
            ),
            "messages": len(
                self.data.messages
            ),
            "images": len(
                self.data.images
            ),
            "output_template": len(
                self.data.output_template
            ),
        }

    # ========================================================
    # RELATIONSHIP VALIDATION
    # ========================================================

    def validate_relationships(self) -> Dict[str, Any]:
        """
        Validate important dataset relationships.

        Returns a report instead of immediately raising for
        every relationship issue.

        This is useful during development.
        """

        if self.data is None:
            raise RuntimeError(
                "Dataset has not been loaded."
            )

        report: Dict[str, Any] = {
            "valid": True,
            "errors": [],
            "warnings": [],
        }

        # ----------------------------------------------------
        # Request IDs
        # ----------------------------------------------------

        request_ids = set(
            self.data.requests["request_id"]
            .dropna()
            .astype(str)
        )

        # ----------------------------------------------------
        # Profile user IDs
        # ----------------------------------------------------

        profile_users = set(
            self.data.financial_profiles["user_id"]
            .dropna()
            .astype(str)
        )

        request_users = set(
            self.data.requests["user_id"]
            .dropna()
            .astype(str)
        )

        missing_profiles = sorted(
            request_users - profile_users
        )

        if missing_profiles:
            report["errors"].append(
                "Requests with no financial profile: "
                + ", ".join(missing_profiles)
            )

        # ----------------------------------------------------
        # Payment options
        # ----------------------------------------------------

        if "request_id" in self.data.request_payment_options.columns:

            option_request_ids = set(
                self.data.request_payment_options[
                    "request_id"
                ]
                .dropna()
                .astype(str)
            )

            unknown_option_requests = sorted(
                option_request_ids - request_ids
            )

            # Some payment options may correspond to the
            # public sample requests, so check those too.
            sample_ids = set(
                self.data.sample_requests[
                    "request_id"
                ]
                .dropna()
                .astype(str)
            )

            unknown_option_requests = sorted(
                option_request_ids
                - request_ids
                - sample_ids
            )

            if unknown_option_requests:
                report["warnings"].append(
                    "Payment options referencing unknown "
                    "evaluation/sample requests: "
                    + ", ".join(
                        unknown_option_requests
                    )
                )

        # ----------------------------------------------------
        # Financial events
        # ----------------------------------------------------

        if "user_id" in self.data.financial_events.columns:

            event_users = set(
                self.data.financial_events["user_id"]
                .dropna()
                .astype(str)
            )

            unknown_event_users = sorted(
                event_users - profile_users
            )

            if unknown_event_users:
                report["warnings"].append(
                    "Financial events with unknown users: "
                    + ", ".join(
                        unknown_event_users
                    )
                )

        # ----------------------------------------------------
        # Image files
        # ----------------------------------------------------

        missing_images = []

        if "image_id" in self.data.images.columns:

            for image_id in (
                self.data.images["image_id"]
                .dropna()
                .astype(str)
                .unique()
            ):

                if not self.image_exists(image_id):
                    missing_images.append(image_id)

        if missing_images:
            report["errors"].append(
                "Referenced image files are missing: "
                + ", ".join(
                    sorted(missing_images)
                )
            )

        # ----------------------------------------------------
        # Final validity
        # ----------------------------------------------------

        report["valid"] = (
            len(report["errors"]) == 0
        )

        return report

    # ========================================================
    # DUPLICATE CHECKING
    # ========================================================

    def duplicate_ids(
        self,
        dataframe_name: str,
        id_column: str,
    ) -> pd.DataFrame:
        """
        Find duplicate identifiers in a dataset.

        This only reports duplicates.

        It does NOT delete or merge them.

        Duplicate resolution belongs to a later financial
        state reconstruction model.
        """

        if self.data is None:
            raise RuntimeError(
                "Dataset has not been loaded."
            )

        dataframe = getattr(
            self.data,
            dataframe_name,
            None,
        )

        if dataframe is None:
            raise ValueError(
                f"Unknown dataset: {dataframe_name}"
            )

        if id_column not in dataframe.columns:
            raise ValueError(
                f"Column '{id_column}' does not exist in "
                f"{dataframe_name}"
            )

        duplicated = dataframe[
            dataframe[id_column]
            .duplicated(keep=False)
        ].copy()

        return duplicated.sort_values(
            by=id_column
        )

    # ========================================================
    # UTILITY
    # ========================================================

    @staticmethod
    def _string_value(
        value: Any,
    ) -> Optional[str]:
        """Convert a value to a clean string or None."""

        if value is None:
            return None

        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        value = str(value).strip()

        return value if value else None

    @staticmethod
    def _empty_dataframe(
        dataframe: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        """Create an empty DataFrame preserving columns."""

        if dataframe is None:
            return pd.DataFrame()

        return dataframe.iloc[0:0].copy()

    @staticmethod
    def _combine_unique_rows(
        frames: List[pd.DataFrame],
        template: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Combine DataFrames and remove exact duplicate rows.
        """

        if not frames:
            return DatasetLoader._empty_dataframe(
                template
            )

        combined = pd.concat(
            frames,
            ignore_index=True,
        )

        if not combined.empty:
            combined = combined.drop_duplicates()

        return combined.reset_index(drop=True)


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================

def load_dataset(
    dataset_dir: str | Path = "dataset",
) -> DatasetLoader:
    """
    Convenience function.

    Example:

        loader = load_dataset("dataset")
        print(loader.statistics())
    """

    loader = DatasetLoader(dataset_dir)
    loader.load()

    return loader


# ============================================================
# COMMAND-LINE TEST
# ============================================================

if __name__ == "__main__":

    print("=" * 60)
    print("BUY OR WAIT? - MODEL 1: DATASET LOADER")
    print("=" * 60)

    loader = DatasetLoader("dataset")

    try:
        loader.load()

        stats = loader.statistics()

        print("\nDataset statistics:")

        for name, count in stats.items():
            print(f"  {name}: {count}")

        relationship_report = (
            loader.validate_relationships()
        )

        print("\nRelationship validation:")
        print(
            f"  valid: "
            f"{relationship_report['valid']}"
        )

        if relationship_report["errors"]:
            print("\nErrors:")

            for error in relationship_report["errors"]:
                print(f"  - {error}")

        if relationship_report["warnings"]:
            print("\nWarnings:")

            for warning in relationship_report["warnings"]:
                print(f"  - {warning}")

        # ----------------------------------------------------
        # Small smoke test
        # ----------------------------------------------------

        if not loader.data.requests.empty:

            first_request_id = str(
                loader.data.requests.iloc[0][
                    "request_id"
                ]
            )

            context = loader.request_context(
                first_request_id
            )

            request = context["request"]

            user_id = str(
                request["user_id"]
            )

            print("\nSmoke test:")
            print(
                f"  request_id: "
                f"{first_request_id}"
            )
            print(
                f"  user_id: "
                f"{user_id}"
            )
            print(
                f"  events: "
                f"{len(context['events'])}"
            )
            print(
                f"  payment_options: "
                f"{len(context['payment_options'])}"
            )
            print(
                f"  messages: "
                f"{len(context['messages'])}"
            )
            print(
                f"  images: "
                f"{len(context['images'])}"
            )

        print("\n" + "=" * 60)
        print("MODEL 1 DATASET LOADER: SUCCESS")
        print("=" * 60)

    except Exception as exc:

        print("\n" + "=" * 60)
        print("MODEL 1 DATASET LOADER: FAILED")
        print("=" * 60)

        print(f"\nError: {exc}")

        raise