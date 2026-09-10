from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from app.agent.prompts import WHATSAPP_PROMPT as _SYSTEM_PROMPT
from app.application.tool_registry import tool
from app.domain import ScoreBreakdown
from app.infrastructure.datasource import get_datasource
from app.infrastructure.llm import LLMMessage, get_llm_router
from app.scoring.compliance import compliance_check


class GenerateWhatsAppIn(BaseModel):
    counter_id: str
    module_id: str
    tone: str = Field(default="professional", description="warm | formal | professional | concise")
    language: str = Field(default="English", description="Target language, e.g. English, Hindi, Marathi, Tamil")
    top_features: list[ScoreBreakdown] = Field(default_factory=list)
    manager_name: str = "Rohan"


class GenerateWhatsAppOut(BaseModel):
    counter_id: str
    module_id: str
    message: str
    compliance: dict[str, Any]
    llm_route: str
    latency_ms: int
    fallback_reason: str = ""


def _user_prompt(counter: dict[str, Any], module: dict[str, Any], top_features: list[ScoreBreakdown], tone: str, manager_name: str, language: str = "English") -> str:
    feat_lines = "\n".join(
        f"- {f.feature}: contribution={f.contribution:+.2f}  ({f.rationale})"
        for f in top_features[:3]
    )
    lang_line = (
        "Language: English\n" if language.lower() == "english"
        else f"Language: {language} — write the ENTIRE message in {language} "
             f"(use the {language} script; keep the counter's name as-is).\n"
    )
    return (
        f"Counter:\n"
        f"  name: {counter.get('name')}\n"
        f"  city: {counter.get('city')}\n"
        f"  counter_type: {counter.get('counter_type')}\n"
        f"  tier: {counter.get('tier')}\n"
        f"  operator: {counter.get('operator')}\n"
        f"  monthly_tpv: ₹{float(counter.get('monthly_tpv') or 0):,.0f}\n"
        f"  digital_share: {counter.get('digital_share')}\n"
        f"  pending_settlement: {counter.get('pending_settlement')}\n"
        f"Billeasy module:\n"
        f"  name: {module.get('name')}\n"
        f"  category: {module.get('category')}\n"
        f"  description: {module.get('description')}\n"
        f"Top signals:\n{feat_lines or '  (none)'}\n"
        f"Tone: {tone}\n"
        f"{lang_line}"
        f"Area Partner Manager: {manager_name}\n"
        f"\nWrite the WhatsApp message to the counter supervisor / outlet owner now."
    )


@tool(
    name="generate_whatsapp_message",
    description=(
        "Generate a compliance-validated WhatsApp draft addressed to one counter's supervisor or "
        "outlet owner about one Billeasy module, grounded in the supplied top feature "
        "contributions. Numeric grounding validator strips any ungrounded ₹ figure, share or "
        "count from the final draft."
    ),
    input_model=GenerateWhatsAppIn,
    output_model=GenerateWhatsAppOut,
)
async def generate_whatsapp_message(args: GenerateWhatsAppIn) -> GenerateWhatsAppOut:
    started = time.perf_counter()
    ds = get_datasource()
    profile_res = await ds.get_counter(args.counter_id)
    mods_res = await ds.get_modules()
    modules: list[dict[str, Any]] = mods_res.data or []
    module = next((m for m in modules if m["id"] == args.module_id), None)
    if not profile_res.data or not module:
        return GenerateWhatsAppOut(
            counter_id=args.counter_id,
            module_id=args.module_id,
            message="",
            compliance={"ok": False, "error": "counter_or_module_not_found"},
            llm_route="-",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    counter = profile_res.data
    # DPDP consent gate, defense-in-depth: a merchant without outreach consent must not
    # be messaged — even if a caller invokes this tool directly, bypassing the agent.
    if not counter.get("consent_ok"):
        return GenerateWhatsAppOut(
            counter_id=args.counter_id,
            module_id=args.module_id,
            message="",
            compliance={
                "ok": False,
                "error": "dpdp_consent_required",
                "reason": "merchant has no DPDP consent for outreach — no message generated",
            },
            llm_route="-",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    router = get_llm_router()
    resp = await router.complete(
        kind="generation",
        messages=[
            LLMMessage(role="system", content=_SYSTEM_PROMPT),
            LLMMessage(role="user", content=_user_prompt(counter, module, args.top_features, args.tone, args.manager_name, args.language)),
        ],
        temperature=0.6,
        max_tokens=220,
    )
    draft = resp.text.strip().strip('"').strip("'")

    # Compliance grounding
    source_context = {
        "counter": counter,
        "module": module,
        "features": [f.model_dump() for f in args.top_features],
    }
    report = compliance_check(draft, source_context)
    final_msg = report["redacted_draft"] if not report["ok"] else draft
    if report["ok"]:
        report["dpdp_consent_ok"] = True

    return GenerateWhatsAppOut(
        counter_id=args.counter_id,
        module_id=args.module_id,
        message=final_msg,
        compliance=report,
        llm_route=resp.meta.get("route_used", resp.provider),
        latency_ms=int((time.perf_counter() - started) * 1000),
        fallback_reason=resp.meta.get("fallback_reason", ""),
    )
