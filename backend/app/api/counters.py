"""Counter 360 endpoint — the full picture behind one counter in the network."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.middleware import require_token
from app.infrastructure.datasource import get_datasource

router = APIRouter(prefix="/counters", tags=["counters"], dependencies=[Depends(require_token)])


@router.get(
    "/{counter_id}",
    summary="Counter 360",
    description=(
        "Profile of one retail outlet or transit ticketing counter (jetty, depot, metro station) "
        "together with its recent transactions, the Billeasy modules already live on it, and the "
        "field-visit notes logged against it. All amounts in ₹."
    ),
)
async def get_counter(counter_id: str) -> dict:
    ds = get_datasource()
    profile = await ds.get_counter(counter_id)
    if not profile.data:
        raise HTTPException(status_code=404, detail="Counter not found")
    txns = await ds.get_transactions(counter_id, 6)
    modules = await ds.get_holdings(counter_id)
    field_notes = await ds.get_field_notes(counter_id)
    return {
        "counter": profile.data,
        "source": profile.source,
        "transactions": txns.data or [],
        "modules": modules.data or [],
        "field_notes": field_notes.data or [],
    }
