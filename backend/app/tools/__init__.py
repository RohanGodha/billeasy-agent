"""Eager imports register every tool with the registry."""
from __future__ import annotations


def bootstrap_tools() -> None:
    # Importing the modules triggers the @tool decorator side-effect.
    from . import (  # noqa: F401
        analyze_telemetry,
        compute_value,
        create_outreach_batch,
        diagnose_reconciliation,
        generate_erp_mapping,
        generate_whatsapp,
        get_counter_transactions,
        predict_propensity,
        query_counters,
        recommend_modules,
        search_field_notes,
        validate_invoice_layout,
    )
