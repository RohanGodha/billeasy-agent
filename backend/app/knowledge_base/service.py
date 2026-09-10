"""Real-time knowledge base over the new_features markdown documents.

Answers Area Partner Manager questions by retrieving the most relevant document
sections (BM25 over markdown chunks) and grounding an LLM answer in them. Falls back to
an extractive answer from the documents when no LLM is available - so answers always
come from the documents, not the model's memory or only the database.
"""
from __future__ import annotations

import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from app.domain import CounterFilters
from app.infrastructure.datasource import get_datasource
from app.infrastructure.llm import LLMMessage, get_llm_router
from app.observability import get_logger
from app.settings import get_settings

logger = get_logger(__name__)

_SETTLEMENT_CATEGORIES = {"reconciliation", "payments", "ticketing"}
_STOPWORDS = {
    "tell", "show", "give", "list", "what", "which", "past", "counter", "counters",
    "module", "modules", "taken", "by", "me", "the", "a", "an", "of", "for", "is",
    "are", "do", "does", "has", "have", "about", "history", "data", "customer",
    "client", "his", "her", "their", "and",
    # --- domain vocabulary -------------------------------------------------
    # These are words an Area Manager uses to ask a *general* question, and they
    # also happen to appear inside counter names. Without this, "how does NCMC work
    # at an AFC gate?" resolves "gate" to "Kashmere Gate ISBT" and the KB answers a
    # policy question with one Delhi bus counter's pending settlement.
    "gate", "gates", "afc", "jetty", "jetties", "depot", "depots", "station",
    "stations", "metro", "hub", "terminus", "terminal", "isbt", "stand",
    "ferry", "ferries", "bus", "buses", "retail", "outlet", "outlets", "store",
    "stores", "kiosk", "cluster", "shop",
    "settlement", "settlements", "payout", "payouts", "ticket", "tickets",
    "ticketing", "fare", "fares", "revenue", "leakage", "gst", "ncmc", "upi",
    "rupay", "mdr", "tpv", "device", "devices", "cash", "digital", "merchant",
    "reconciliation", "billing", "loyalty", "receipt", "receipts", "invoice",
}

_KB_DIR = Path(__file__).resolve().parents[2] / "new_features"
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")

# --- Retrieval stopwords ----------------------------------------------------
# NOT the same list as _STOPWORDS above. _STOPWORDS removes *domain* vocabulary so a
# policy question does not resolve to a counter *name*; those very words (ncmc, afc,
# gst, settlement) are the highest-signal terms for *document* retrieval and must
# never be stripped here.
#
# What must be stripped here is the interrogative frame an Area Manager wraps every
# question in - "what is X and how does it work at a Y". With only ~45 chunks, no
# function word appears in more than half of them, so BM25Okapi never assigns it a
# negative IDF and never applies its epsilon floor: "how", "does" and "what" each end
# up with an IDF of ~1.1-1.2, the same weight as "ncmc". A long FAQ chunk full of
# question text then out-scores the one section that actually answers the question.
# Applied symmetrically to the index and the query, so nothing stops matching.
_RETRIEVAL_STOPWORDS = {
    "a", "about", "again", "against", "all", "also", "am", "an", "and", "any", "anyone",
    "are", "as", "ask", "at", "back", "be", "because", "been", "before", "being",
    "between", "both", "but", "by", "can", "could", "did", "difference", "different",
    "do", "does", "doing", "done", "each", "explain", "few", "for", "from", "further",
    "get", "gets", "give", "gives", "go", "goes", "had", "has", "have", "having", "he",
    "her", "here", "hers", "him", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "itself", "just", "know", "let", "like", "list", "look", "make", "many",
    "may", "me", "mean", "meaning", "means", "might", "more", "most", "much", "must",
    "my", "need", "needs", "no", "nor", "not", "now", "of", "off", "on", "once", "one",
    "only", "or", "other", "others", "ought", "our", "ours", "out", "over", "own",
    "please", "put", "same", "say", "see", "shall", "she", "should", "show", "so",
    "some", "such", "take", "tell", "than", "that", "the", "their", "theirs", "them",
    "then", "there", "these", "they", "thing", "things", "this", "those", "through",
    "to", "too", "under", "until", "up", "us", "use", "used", "uses", "using", "very",
    "vs", "want", "was", "we", "well", "were", "what", "whats", "when", "where",
    "whether", "which", "while", "who", "whom", "whose", "why", "will", "with",
    "within", "would", "you", "your", "yours",
    "work", "working", "works",
}

# High-signal domain acronyms and the words they stand for. BM25 cannot know that
# "One Nation One Card" and "NCMC" are the same thing, so a question phrased either
# way is expanded to cover both. Expansion terms are added once (the acronym itself
# is not duplicated), so this widens recall without swamping the literal query.
_ACRONYM_EXPANSIONS = {
    "ncmc": "national common mobility card one nation one card rupay contactless prepaid transit",
    "afc": "automatic fare collection gate reader turnstile validator tap",
    "irn": "invoice reference number e-invoice einvoice signed qr",
    "mdr": "merchant discount rate interchange",
    "upi": "unified payments interface npci",
    "tpv": "total payment value throughput",
    "dpdp": "digital personal data protection consent",
    "pa": "payment aggregator",
    "pg": "payment gateway",
    "kyc": "know your customer merchant onboarding due diligence",
    "gst": "goods services tax e-invoicing",
    "hsn": "harmonised system nomenclature code",
    "sac": "services accounting code",
    "tvm": "ticket vending machine",
    "npci": "national payments corporation",
    "rbi": "reserve bank",
    "onoc": "one nation one card ncmc",
}

# Sections are chunked at heading boundaries first, then any section longer than this
# is sub-split on paragraph boundaries with a one-paragraph overlap. Without this a
# whole FAQ letter-section ("E. Disputes and chargebacks", six unrelated Q&As) is a
# single 500-token chunk that matches a bit of everything.
_MAX_CHUNK_CHARS = 1100
_MIN_CHUNK_CHARS = 20

# The section heading is the most reliable topic label a chunk has, and the body often
# says "the card" where the heading says "NCMC". Repeating the heading path in the
# indexed text is a plain BM25 field boost.
_HEADING_WEIGHT = 3

# Cap on how many sub-chunks of the same section may occupy the top-k result list.
_MAX_CHUNKS_PER_SECTION = 2

# A name token shared by more counters than this is treated as generic ("jetty",
# "depot", "station") and is not used to resolve a counter by name.
_MAX_NAME_TOKEN_FANOUT = 8

# Terms too generic to carry relevance across turns. Rocchio re-weights the next
# retrieval using the terms our own last grounded answer emphasised - "counter" or
# "payment" appear in every answer and would just flatten the signal into noise.
_FEEDBACK_STOPWORDS = {
    "counter", "counters", "module", "modules", "payment", "payments",
    "amount", "amounts", "per", "one", "use", "used", "using", "users",
}

_FILES = {
    "payments_compliance.md": "Payments & Compliance",
    "counter_performance_methodology.md": "Counter Performance Methodology",
    "field_ops_faqs.md": "Field Operations FAQs",
    # 2026 enforcement batch: gateway/settlement error classes, effective-dated regulatory
    # schedule, ERP integration guide, security & DPDP policies, API/integration guide.
    "gateway_error_codes.md": "Gateway & Settlement Error Codes",
    "regulatory_schedule.md": "Regulatory & Compliance Schedule",
    "erp_integrations.md": "ERP & Accounting Integration",
    "security_policies.md": "Security & Data-Protection Policies",
    "api_guide.md": "Counter Copilot API Guide",
}

_SYSTEM = (
    "You are Counter Copilot's knowledge assistant for a Billeasy Area Partner Manager. "
    "Billeasy runs the digital payment and ticketing rail for retail outlets and government "
    "mass-transit counters (ferry jetties, bus depots, metro stations). "
    "Answer ONLY from the reference excerpts provided. Be concise, factual and practical. "
    "Use Indian payments, transit ticketing and GST context, and Rupees for all amounts. "
    "If the answer is not in the excerpts, say you don't have that in the knowledge base and "
    "suggest what is covered. Never invent figures."
)


def _tokenize(s: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(s)]


def _retrieval_tokens(s: str) -> list[str]:
    """Content tokens for BM25 - the interrogative frame removed, acronyms kept."""
    return [t for t in _tokenize(s) if t not in _RETRIEVAL_STOPWORDS]


def _expand_query(tokens: list[str]) -> list[str]:
    """Add the expansion of any domain acronym present, once, after the literal query."""
    seen = set(tokens)
    extra: list[str] = []
    for t in tokens:
        for e in _tokenize(_ACRONYM_EXPANSIONS.get(t, "")):
            if e not in seen and e not in _RETRIEVAL_STOPWORDS:
                seen.add(e)
                extra.append(e)
    return tokens + extra


def _paragraph_split(body: str) -> list[str]:
    """Break an over-long section into paragraph-bounded parts with one-para overlap.

    Blank lines are the only split points, so a markdown table, a numbered list or a
    single FAQ answer is never cut in half.
    """
    if len(body) <= _MAX_CHUNK_CHARS:
        return [body]
    paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
    parts: list[str] = []
    cur: list[str] = []
    size = 0
    for p in paras:
        if cur and size + len(p) > _MAX_CHUNK_CHARS:
            parts.append("\n\n".join(cur))
            cur = [cur[-1]] if len(cur) > 1 else []  # one-paragraph overlap
            size = sum(len(x) for x in cur)
        cur.append(p)
        size += len(p)
    if cur:
        tail = "\n\n".join(cur)
        if parts and len(tail) < _MIN_CHUNK_CHARS:
            parts[-1] += "\n\n" + tail
        else:
            parts.append(tail)
    return parts or [body]


def _normalise_name(s: str) -> str:
    return " ".join(_tokenize(s))


def _inr(value: Any) -> str:
    """Format an amount in Rupees with Indian digit grouping: 4860000 -> '₹48,60,000'."""
    n = int(value or 0)
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(?<=\d)(?=(\d\d)+$)", ",", head)
        s = f"{head},{tail}"
    return f"{sign}₹{s}"


def _ds_method(names: tuple[str, ...]) -> Any | None:
    """Resolve the first available datasource method from a list of candidate names."""
    ds = get_datasource()
    for name in names:
        fn = getattr(ds, name, None)
        if fn is not None:
            return fn
    return None


class KnowledgeBase:
    def __init__(self) -> None:
        self._chunks: list[dict[str, Any]] = []
        self._bm25: BM25Okapi | None = None
        self._ready = False
        self._name_index: dict[str, list[dict[str, Any]]] | None = None
        self._counters: list[dict[str, Any]] = []

    def _ensure(self) -> None:
        if self._ready:
            return
        chunks: list[dict[str, Any]] = []
        for fname, label in _FILES.items():
            path = _KB_DIR / fname
            if not path.exists():
                logger.warning("Knowledge file missing: %s", path)
                continue
            chunks.extend(self._split(path.read_text(encoding="utf-8"), label))
        self._chunks = chunks
        if chunks:
            self._bm25 = BM25Okapi([c["tokens"] for c in chunks])
        self._ready = True
        logger.info("KnowledgeBase ready: %d chunks from %d docs.", len(chunks), len(_FILES))

    @staticmethod
    def _split(text: str, source: str) -> list[dict[str, Any]]:
        """Split markdown at ## / ### headings, then sub-split oversized sections.

        Each chunk carries its full heading path (document label > section > subsection)
        both as searchable text and as a title, so a chunk whose body only says "the
        card" still carries the word NCMC from the heading it lives under.
        """
        lines = text.splitlines()
        chunks: list[dict[str, Any]] = []
        # level -> heading text; level 1 is pinned to the short document label because
        # the H1 line of these files lists every topic in the document ("... MDR, NCMC &
        # DPDP"), which would hand every chunk in the file the token "ncmc".
        stack: dict[int, str] = {1: source}
        buf: list[str] = []

        def path() -> list[str]:
            return [stack[lvl] for lvl in sorted(stack) if stack.get(lvl)]

        def flush() -> None:
            body = "\n".join(buf).strip()
            if len(body) < _MIN_CHUNK_CHARS:
                return
            crumbs = path()
            title = crumbs[-1] if len(crumbs) > 1 else source
            heading_text = " ".join(crumbs[1:]) or source
            for part in _paragraph_split(body):
                index_text = " ".join([heading_text] * _HEADING_WEIGHT + [source, part])
                chunks.append(
                    {
                        "source": source,
                        "title": title,
                        "heading_path": " > ".join(crumbs),
                        "text": part,
                        "tokens": _retrieval_tokens(index_text),
                    }
                )

        for line in lines:
            m = _HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                if level == 1:
                    continue  # document H1: the _FILES label is the cleaner root crumb
                flush()
                buf = []
                stack[level] = m.group(2).strip()
                for deeper in [lvl for lvl in stack if lvl > level]:
                    del stack[deeper]
            else:
                buf.append(line)
        flush()
        return chunks

    @staticmethod
    def _feedback_token_stats(text: str) -> dict[str, int]:
        stats: dict[str, int] = {}
        for t in _tokenize(text):
            if len(t) < 3 or t.isdigit() or t in _RETRIEVAL_STOPWORDS or t in _FEEDBACK_STOPWORDS:
                continue
            stats[t] = stats.get(t, 0) + 1
        return stats

    def feedback_terms(self, history_text: str, current_query: str) -> list[str]:
        """Terms our own last grounded answer emphasised, to re-weight the next retrieval.

        Rocchio feedback in its clean textbook form needs a scored index and relevance
        labels per document. We have neither, but BM25 scales each token by its query
        frequency, so *repeating* a term in the next query multiplies that term's score
        contribution - a keyless, no-index analogue. The term pool is the last turns of
        history (the answer we stand behind is the relevant feedback we have), minus any
        terms the user already put in the query.
        """
        settings = get_settings()
        exclude = set(_retrieval_tokens(current_query))
        stats = self._feedback_token_stats(history_text)
        ranked = sorted(stats.items(), key=lambda kv: (-kv[1], kv[0]))
        return [t for t, _ in ranked if t not in exclude][: settings.rocchio_max_feedback_terms]

    @staticmethod
    def _feedback_repeats(terms: list[str], current: list[str]) -> list[str]:
        settings = get_settings()
        repeats = max(1, settings.rocchio_expansion_repeats)
        seen = set(current)
        extra: list[str] = []
        for raw in terms:
            for t in _tokenize(str(raw)):
                if t in seen or t in _RETRIEVAL_STOPWORDS or t in _FEEDBACK_STOPWORDS or len(t) < 3:
                    continue
                seen.add(t)
                extra.extend([t] * repeats)
        return extra

    def search(
        self,
        query: str,
        k: int = 4,
        expand_terms: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure()
        if not self._chunks or not self._bm25:
            return []
        tokens = _retrieval_tokens(query) or _tokenize(query)
        query_terms = _expand_query(tokens) + self._feedback_repeats(expand_terms or [], tokens)
        scores = self._bm25.get_scores(query_terms)
        ranked = sorted(range(len(self._chunks)), key=lambda i: scores[i], reverse=True)
        out = []
        # A section is now several sub-chunks, so cap how many of them one section may
        # take: keep the depth that matters without spending the whole budget on one
        # heading and starving the answer of a second perspective.
        per_section: dict[str, int] = {}
        for i in ranked:
            if len(out) >= k:
                break
            if scores[i] <= 0:
                continue
            c = self._chunks[i]
            key = c["heading_path"]
            if per_section.get(key, 0) >= _MAX_CHUNKS_PER_SECTION:
                continue
            per_section[key] = per_section.get(key, 0) + 1
            out.append({
                "source": c["source"],
                "title": c["title"],
                "heading_path": c["heading_path"],
                "text": c["text"],
                "score": round(float(scores[i]), 3),
            })
        return out

    def sources(self) -> list[dict[str, Any]]:
        self._ensure()
        grouped: dict[str, list[str]] = {}
        for c in self._chunks:
            grouped.setdefault(c["source"], [])
            if c["title"] not in grouped[c["source"]] and c["title"] != c["source"]:
                grouped[c["source"]].append(c["title"])
        return [{"source": s, "sections": sections} for s, sections in grouped.items()]

    async def _name_map(self) -> dict[str, list[dict[str, Any]]]:
        """Distinctive name token (lowercase) -> counter records that carry it.

        Counter names are multi-word ("Gateway Jetty - Counter 3"), so every meaningful
        token is indexed and tokens shared across the network ("jetty", "depot") are
        dropped as generic.
        """
        if self._name_index is not None:
            return self._name_index
        index: dict[str, list[dict[str, Any]]] = {}
        counters: list[dict[str, Any]] = []
        find = _ds_method(("find_counters", "find_customers"))
        if find is None:
            logger.warning("KB name index build failed: datasource has no counter lookup.")
            self._name_index = index
            return index
        try:
            res = await find(CounterFilters(limit=2000))
            for c in res.data or []:
                name = (c.get("name") or "").strip()
                if not name:
                    continue
                counters.append(c)
                for tok in set(_tokenize(name)):
                    if tok in _STOPWORDS or len(tok) < 3 or tok.isdigit():
                        continue
                    index.setdefault(tok, []).append(c)
            for tok in [t for t, rows in index.items() if len(rows) > _MAX_NAME_TOKEN_FANOUT]:
                del index[tok]
        except Exception as e:  # noqa: BLE001
            logger.warning("KB name index build failed: %s", e)
        self._counters = counters
        self._name_index = index
        return index

    async def _resolve_counter(self, query: str) -> dict[str, Any] | None:
        """Resolve a counter named in the question ("Gateway Jetty's settlement history")."""
        tokens = await self._name_map()
        if not tokens and not self._counters:
            return None

        # Exact-ish match first: the counter's full name appears inside the question.
        norm_query = _normalise_name(query)
        best_exact: dict[str, Any] | None = None
        best_len = 0
        for c in self._counters:
            norm_name = _normalise_name(c.get("name") or "")
            if len(norm_name) > best_len and norm_name and norm_name in norm_query:
                best_exact, best_len = c, len(norm_name)
        if best_exact is not None:
            return best_exact

        # Otherwise vote with the distinctive name tokens present in the question.
        votes: dict[str, int] = {}
        by_id: dict[str, dict[str, Any]] = {}
        for tok in set(_tokenize(query)):
            for c in tokens.get(tok, []):
                cid = str(c.get("id", ""))
                votes[cid] = votes.get(cid, 0) + 1
                by_id[cid] = c
        if not votes:
            return None
        best_id = min(votes, key=lambda cid: (-votes[cid], cid))
        return by_id[best_id]

    async def _counter_context(self, counter: dict[str, Any]) -> tuple[str, str]:
        """Build (LLM grounding, extractive fallback) from the counter's real records."""
        cid = counter["id"]
        modules: list[dict[str, Any]] = []
        notes: list[dict[str, Any]] = []
        get_modules = _ds_method(("get_counter_modules", "get_modules_for_counter", "get_holdings"))
        get_notes = _ds_method(("get_field_notes", "get_interactions"))
        if get_modules is not None:
            try:
                modules = (await get_modules(cid)).data or []
            except Exception:  # noqa: BLE001
                modules = []
        if get_notes is not None:
            try:
                notes = (await get_notes(cid)).data or []
            except Exception:  # noqa: BLE001
                notes = []

        settlement = [m for m in modules if (m.get("category") or "").lower() in _SETTLEMENT_CATEGORIES]
        others = [m for m in modules if (m.get("category") or "").lower() not in _SETTLEMENT_CATEGORIES]
        name = counter.get("name", cid)

        def _module_line(m: dict[str, Any]) -> str:
            live = (m.get("activated_at") or m.get("opened_at") or "")[:10]
            return f"{m.get('name')} ({m.get('category')}), status {m.get('status', 'active')}" + (f", live since {live}" if live else "")

        settlement_txt = "; ".join(_module_line(m) for m in settlement) if settlement else "none live"
        others_txt = "; ".join(_module_line(m) for m in others) if others else "none"
        notes_txt = " | ".join((n.get("summary") or n.get("note") or "")[:160] for n in notes[:2])

        tpv = _inr(counter.get("monthly_tpv"))
        pending = _inr(counter.get("pending_settlement"))
        digital = counter.get("digital_share")
        digital_txt = f"{float(digital) * 100:.0f}%" if digital is not None else "unknown"
        daily = counter.get("avg_daily_txns")
        daily_txt = f"{float(daily):.0f}" if daily is not None else "unknown"

        ctx = (
            f"[Counter Record]\n"
            f"Name: {name} | City: {counter.get('city')} | Type: {counter.get('counter_type')} | "
            f"Tier: {counter.get('tier')} | Operator: {counter.get('operator')}\n"
            f"Monthly TPV: {tpv} | Digital share: {digital_txt} | Avg daily txns: {daily_txt}\n"
            f"Pending settlement: {pending} | Settlement cycle: "
            f"{counter.get('settlement_cycle', 'T+1')} | KYC: {counter.get('kyc_status', 'unknown')}\n"
            f"Settlement / payments / ticketing modules live: {settlement_txt}\n"
            f"Other modules live: {others_txt}\n"
            f"Recent field notes: {notes_txt or 'none'}"
        )

        if settlement:
            extract = (
                f"{name} runs {tpv} monthly TPV with {pending} pending settlement on a "
                f"{counter.get('settlement_cycle', 'T+1')} cycle. Settlement, payments and ticketing "
                f"modules live: {settlement_txt}. Recent field notes: {notes_txt.rstrip(' .') or 'none'}."
            )
        else:
            extract = (
                f"{name} runs {tpv} monthly TPV with {pending} pending settlement on a "
                f"{counter.get('settlement_cycle', 'T+1')} cycle. No settlement, payments or ticketing "
                f"module is live on this counter. Other modules live: {others_txt}. "
                f"Recent field notes: {notes_txt.rstrip(' .') or 'none'}."
            )
        return ctx, extract

    async def ask(
        self,
        query: str,
        expand_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        counter = await self._resolve_counter(query)
        hits = self.search(query, k=3 if counter else 4, expand_terms=expand_terms)

        context_parts: list[str] = []
        extractive_primary: str | None = None
        sources: list[str] = []

        if counter:
            counter_ctx, extractive_primary = await self._counter_context(counter)
            context_parts.append(counter_ctx)
            sources.append("Counter Record")

        if hits:
            context_parts.append(
                "\n\n".join(f"[{h.get('heading_path') or h['source'] + ' > ' + h['title']}]\n{h['text']}" for h in hits)
            )
            sources.extend(sorted({h["source"] for h in hits}))

        if not context_parts:
            return {
                "answer": "I couldn't find that in the knowledge base. I cover payments and GST "
                          "compliance, counter performance and revenue-leakage methodology, field "
                          "operations procedures, and specific counter records.",
                "sources": [],
                "excerpts": [],
                "llm_route": None,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }

        context = "\n\n".join(context_parts)
        router = get_llm_router()
        answer = ""
        route = None
        try:
            resp = await router.complete(
                kind="reasoning",
                messages=[
                    LLMMessage(role="system", content=_SYSTEM),
                    LLMMessage(role="user", content=f"Question: {query}\n\nReference excerpts:\n{context}"),
                ],
                temperature=0.2,
                max_tokens=320,
            )
            answer = resp.text.strip()
            route = resp.meta.get("route_used", resp.provider)
        except Exception as e:  # noqa: BLE001
            logger.warning("KB LLM answer failed (%s) - using extractive fallback.", e.__class__.__name__)

        # Extractive fallback so the answer is always grounded in real data/docs.
        if route in (None, "mock") or len(answer) < 15:
            if extractive_primary:
                answer = extractive_primary
            else:
                top = hits[0]
                snippet = top["text"]
                if len(snippet) > 700:
                    snippet = snippet[:700].rsplit("\n", 1)[0] + " ..."
                answer = f"From {top['source']} - {top['title']}:\n\n{snippet}"
            route = route or "documents"

        excerpts = [{"source": h["source"], "title": h["title"], "score": h["score"]} for h in hits]
        if counter:
            excerpts.insert(0, {"source": "Counter Record", "title": counter.get("name", ""), "score": 1.0})

        return {
            "answer": answer,
            "sources": list(dict.fromkeys(sources)),
            "excerpts": excerpts,
            "llm_route": route,
            "latency_ms": int((time.perf_counter() - started) * 1000),
        }


@lru_cache(maxsize=1)
def get_knowledge_base() -> KnowledgeBase:
    return KnowledgeBase()
