"""
agents.py — Phase 1 Stabilized
================================
Multi-Agent PMO Intelligence Pipeline
Provider : Anthropic Claude
Pattern  : Single-responsibility agents → Orchestrator aggregation
Phase    : 1 (core analysis pipeline)
Designed for Phase 2+ expansion: conversational AI, multi-agent mesh, RAG.

Agents (Phase 1):
  1. ProjectSummaryAgent    — structured brief from raw project text
  2. MethodologyAgent       — delivery methodology recommendation
  3. GoNoGoAgent            — viability gate assessment
  4. SiteReadinessAgent     — operational & environment readiness
  5. ExecutiveSummaryAgent  — C-suite synthesis (runs after all others)

Supporting modules consumed (passive, no writes in Phase 1):
  - lifecycle_engine.LifecycleAdvisor  → informs methodology scoring
  - reasoning.PMReasoningEngine        → informs Go/No-Go blockers
  - memory.OperationalMemory           → result storage (read + write)
  - dependency_graph.DependencyGraph   → available for Phase 2 wiring
"""

from __future__ import annotations

import os
import re
import time
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

import anthropic

# ── Optional internal module imports (graceful if missing) ─────────────────────
try:
    from lifecycle_engine import LifecycleAdvisor
    _LIFECYCLE_AVAILABLE = True
except ImportError:
    _LIFECYCLE_AVAILABLE = False

try:
    from reasoning import PMReasoningEngine
    _REASONING_AVAILABLE = True
except ImportError:
    _REASONING_AVAILABLE = False

try:
    from memory import OperationalMemory
    _MEMORY_AVAILABLE = True
except ImportError:
    _MEMORY_AVAILABLE = False

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("agents")


# ── Constants ──────────────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-6"      # Sonnet: best quality/speed balance for Phase 1
MAX_TOKENS = 2048
RETRY_ATTEMPTS = 3
RETRY_BACKOFF = [2, 5, 10]       # seconds between retries


# ── Enums ──────────────────────────────────────────────────────────────────────
class DeliveryMethodology(str, Enum):
    AGILE      = "Agile"
    WATERFALL  = "Waterfall"
    HYBRID     = "Hybrid"
    PRINCE2    = "PRINCE2"
    SAFe       = "SAFe"
    ITERATIVE  = "Iterative"
    PREDICTIVE = "Predictive / Waterfall"
    UNKNOWN    = "Undetermined"


class GoNoGoDecision(str, Enum):
    GO               = "GO"
    NO_GO            = "NO-GO"
    CONDITIONAL_GO   = "CONDITIONAL GO"
    INSUFFICIENT     = "INSUFFICIENT DATA"


# ── Data Contracts ─────────────────────────────────────────────────────────────
@dataclass
class ProjectContext:
    """
    Shared context object threaded through every agent.
    Extend in Phase 2 with: conversation_history, vector_context, agent_memory.
    """
    raw_input:    str
    source_type:  str = "text"       # 'text' | 'file'
    filename:     Optional[str] = None
    project_name: Optional[str] = None   # populated by ProjectSummaryAgent


@dataclass
class AgentResult:
    """Standardised envelope returned by every agent."""
    agent_name:  str
    reasoning:   str
    output:      Any                 # str | dict — agent-specific
    confidence:  str = "medium"      # low | medium | high
    warnings:    list[str] = field(default_factory=list)
    elapsed_ms:  float = 0.0
    error:       Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


@dataclass
class PipelineReport:
    """
    Full aggregated output from one pipeline run.
    Stored in OperationalMemory when available.
    """
    project_summary:   AgentResult
    methodology:       AgentResult
    go_no_go:          AgentResult
    site_readiness:    AgentResult
    executive_summary: AgentResult
    total_elapsed_ms:  float = 0.0
    run_timestamp:     str = ""


# ── Base Agent ─────────────────────────────────────────────────────────────────
class BaseAgent:
    """
    Abstract base for all Phase 1 agents.

    Subclasses must implement:
        _system_prompt(self) -> str
        _user_prompt(self, ctx: ProjectContext) -> str

    Subclasses may override:
        _parse_output(self, raw: str) -> Any
        reason(self, ctx: ProjectContext) -> str
    """

    name: str = "BaseAgent"

    def __init__(self, api_key: str):
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. "
                "Export it in your shell: export ANTHROPIC_API_KEY='sk-ant-...'"
            )
        self._client = anthropic.Anthropic(api_key=api_key)

    # ── Abstract interface ────────────────────────────────────────────────────

    def _system_prompt(self) -> str:
        raise NotImplementedError(f"{self.name} must implement _system_prompt()")

    def _user_prompt(self, ctx: ProjectContext) -> str:
        raise NotImplementedError(f"{self.name} must implement _user_prompt()")

    def _parse_output(self, raw: str) -> Any:
        """Default: return stripped text. Override for structured extraction."""
        return raw.strip()

    # ── Reasoning hook (Phase 2: override for chain-of-thought introspection) ─

    def reason(self, ctx: ProjectContext) -> str:
        """
        Pre-flight reasoning: why is this agent relevant to this input?
        Phase 2: replace with LLM-driven chain-of-thought.
        """
        chars = len(ctx.raw_input)
        src   = ctx.source_type
        name  = ctx.project_name or "unnamed project"
        return (
            f"[{self.name}] Analysing {chars:,} chars from {src} "
            f"for project '{name}'."
        )

    # ── LLM caller with retry ─────────────────────────────────────────────────

    def _call_llm(self, system: str, user: str) -> str:
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                response = self._client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return response.content[0].text
            except anthropic.RateLimitError:
                wait = RETRY_BACKOFF[min(attempt - 1, len(RETRY_BACKOFF) - 1)]
                logger.warning(
                    f"[{self.name}] Rate limit (attempt {attempt}/{RETRY_ATTEMPTS}). "
                    f"Waiting {wait}s..."
                )
                time.sleep(wait)
            except anthropic.APIStatusError as exc:
                logger.error(f"[{self.name}] API error: {exc}")
                raise
        raise RuntimeError(
            f"[{self.name}] All {RETRY_ATTEMPTS} LLM call attempts failed."
        )

    # ── Public run interface ──────────────────────────────────────────────────

    def run(self, ctx: ProjectContext) -> AgentResult:
        t0        = time.time()
        reasoning = self.reason(ctx)
        logger.info(reasoning)

        try:
            raw    = self._call_llm(self._system_prompt(), self._user_prompt(ctx))
            output = self._parse_output(raw)
            error  = None
        except Exception as exc:
            logger.error(f"[{self.name}] Failed: {exc}")
            output = None
            error  = str(exc)

        elapsed = round((time.time() - t0) * 1000, 2)
        return AgentResult(
            agent_name=self.name,
            reasoning=reasoning,
            output=output,
            elapsed_ms=elapsed,
            error=error,
        )


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT 1 — Project Summary
# ══════════════════════════════════════════════════════════════════════════════
class ProjectSummaryAgent(BaseAgent):
    """
    Reads raw project text and produces a structured project brief.
    Populates ctx.project_name for downstream agents.
    """
    name = "ProjectSummaryAgent"

    def _system_prompt(self) -> str:
        return (
            "You are a Senior Business Analyst and Project Strategist with 20 years of "
            "cross-sector programme delivery experience. "
            "Your role: read any project document — no matter how raw or unstructured — "
            "and extract a precise, structured project brief. "
            "Rules: Be factual. State 'Not specified' for missing information. "
            "NEVER fabricate figures, names, or dates. "
            "NEVER pad with generic filler text."
        )

    def _user_prompt(self, ctx: ProjectContext) -> str:
        return f"""
Analyse the following project input and return a structured project brief.
Use EXACTLY this format. Do not add extra sections.

**PROJECT BRIEF**

**Project Name:** (inferred or stated; use 'Unnamed Project' if absent)
**Sector / Domain:** (e.g. IT, Infrastructure, Construction, Services)
**Objectives:**
- (bullet list, max 5, each one sentence)

**Key Stakeholders:** (roles / departments / individuals mentioned or clearly inferable)
**Scope Summary:** (2–3 sentences, factual, no padding)
**Stated Constraints:**
- Budget: (figure or 'Not specified')
- Timeline: (duration or end date or 'Not specified')
- Resources: (headcount, teams, or 'Not specified')

**Timeline Signals:** (any dates, phases, milestones mentioned; or 'None found')
**Key Risks Identified:**
- (bullet list, max 5; or 'None explicitly stated')

**Missing Critical Information:** (what's absent that a PM would need before planning)

---
PROJECT INPUT:
{ctx.raw_input}
""".strip()

    def _parse_output(self, raw: str) -> dict:
        # Extract project name for context propagation
        name_match = re.search(r"\*\*Project Name:\*\*\s*(.+)", raw)
        project_name = name_match.group(1).strip() if name_match else "Unnamed Project"
        return {
            "project_name": project_name,
            "full_brief":   raw.strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT 2 — Delivery Methodology
# ══════════════════════════════════════════════════════════════════════════════
class MethodologyAgent(BaseAgent):
    """
    Recommends a delivery methodology.
    Optionally enriched by LifecycleAdvisor signal scoring.
    """
    name = "MethodologyAgent"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self._lifecycle = LifecycleAdvisor() if _LIFECYCLE_AVAILABLE else None

    def _system_prompt(self) -> str:
        return (
            "You are a delivery methodology expert with deep knowledge of Agile, "
            "Waterfall, Hybrid, PRINCE2, SAFe, Iterative, and Predictive frameworks. "
            "You recommend the most suitable methodology by reasoning step by step "
            "across: requirements certainty, compliance intensity, team scale, "
            "stakeholder complexity, and delivery cadence. "
            "You are decisive — you give ONE primary recommendation. "
            "You acknowledge trade-offs honestly."
        )

    def _user_prompt(self, ctx: ProjectContext) -> str:
        # Enrich with LifecycleAdvisor signals if available
        lifecycle_hint = ""
        if self._lifecycle:
            try:
                signals = self._extract_signals(ctx.raw_input)
                advice  = self._lifecycle.recommend(signals)
                lifecycle_hint = (
                    f"\n\n[Internal signal scoring suggests: "
                    f"{advice['methodology']} (confidence {advice['confidence']}%) "
                    f"— {advice['reason']}. Use this as one input, not the only factor.]"
                )
            except Exception:
                pass

        return f"""
Based on the project description below, recommend the most suitable delivery methodology.
{lifecycle_hint}

Think step by step before answering:
1. What is the level of requirements certainty?
2. What is the regulatory/compliance burden?
3. What is the stakeholder and governance complexity?
4. What is the scale and duration of delivery?
5. What delivery cadence suits this team and context?

Then return your answer in EXACTLY this format:

**METHODOLOGY RECOMMENDATION**

**Recommended Methodology:** (one of: Agile | Waterfall | Hybrid | PRINCE2 | SAFe | Iterative | Predictive / Waterfall | Undetermined)
**Confidence:** (Low | Medium | High)

**Step-by-Step Reasoning:**
1. Requirements certainty: ...
2. Compliance burden: ...
3. Stakeholder complexity: ...
4. Scale and duration: ...
5. Delivery cadence fit: ...

**Rationale Summary:** (3–5 sentences)

**Why Not Alternatives:**
- [Alternative 1]: (brief dismissal)
- [Alternative 2]: (brief dismissal)

**Methodology-Specific Risks:**
- (2–3 risks of applying this methodology to THIS project)

**Recommended Governance Model:** (brief description)

---
PROJECT INPUT:
{ctx.raw_input}
""".strip()

    def _extract_signals(self, text: str) -> dict:
        """Heuristic signal extraction for LifecycleAdvisor."""
        text_lower = text.lower()
        return {
            "infra_dependency": 8 if any(
                w in text_lower for w in ["infrastructure", "network", "server", "data centre", "dc"]
            ) else 4,
            "compliance": 8 if any(
                w in text_lower for w in ["gdpr", "iso", "regulatory", "audit", "compliance", "governance"]
            ) else 3,
            "requirement_volatility": 8 if any(
                w in text_lower for w in ["agile", "iterative", "evolving", "unclear", "tbd", "to be confirmed"]
            ) else 3,
            "procurement": 6 if any(
                w in text_lower for w in ["vendor", "procurement", "tender", "rfp", "contract", "sow"]
            ) else 2,
            "innovation": 7 if any(
                w in text_lower for w in ["ai", "ml", "innovation", "greenfield", "new technology"]
            ) else 3,
        }

    def _parse_output(self, raw: str) -> dict:
        methodology = DeliveryMethodology.UNKNOWN
        for m in DeliveryMethodology:
            if m.value.lower() in raw.lower():
                methodology = m
                break

        confidence = "Medium"
        conf_match = re.search(r"\*\*Confidence:\*\*\s*(\w+)", raw, re.IGNORECASE)
        if conf_match:
            confidence = conf_match.group(1).strip()

        return {
            "methodology": methodology.value,
            "confidence":  confidence,
            "full_analysis": raw.strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT 3 — Go / No-Go
# ══════════════════════════════════════════════════════════════════════════════
class GoNoGoAgent(BaseAgent):
    """
    Structured Go/No-Go viability gate.
    Enriched by PMReasoningEngine blocker detection where available.
    """
    name = "GoNoGoAgent"

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self._engine = PMReasoningEngine() if _REASONING_AVAILABLE else None

    def _system_prompt(self) -> str:
        return (
            "You are a senior Programme Director and Investment Decision Advisor "
            "with a track record of leading major programme reviews. "
            "You perform rigorous Go/No-Go assessments. "
            "You score five dimensions with explicit reasoning for each. "
            "You are direct and honest — you will recommend NO-GO when evidence warrants it. "
            "You never hedge a clear signal into vagueness."
        )

    def _user_prompt(self, ctx: ProjectContext) -> str:
        # Surface known hard blockers from PMReasoningEngine
        blocker_hint = ""
        if self._engine:
            try:
                # Map text signals to PMReasoningEngine data format
                text_lower = ctx.raw_input.lower()
                check = self._engine.evaluate_migration_readiness({
                    "wan_ready":   "wan" not in text_lower or "wan ready" in text_lower,
                    "cab_approved": "cab" not in text_lower or "cab approved" in text_lower,
                    "uat_signed":  "uat" not in text_lower or "uat signed" in text_lower,
                })
                if check["decision"] == "NO-GO" and check["blockers"]:
                    blocker_hint = (
                        f"\n\n[Internal blocker scan detected: {', '.join(check['blockers'])}. "
                        f"Factor these into your assessment.]"
                    )
            except Exception:
                pass

        return f"""
Perform a Go/No-Go assessment for the project described below.
{blocker_hint}

Score each dimension 1–5 (1 = critical concern, 5 = no concerns).
Reason explicitly for each score before assigning it.

**GO / NO-GO ASSESSMENT**

**Dimension Scores:**

| Dimension               | Score (1–5) | Key Reasoning |
|-------------------------|-------------|---------------|
| Strategic Fit           |             |               |
| Financial Viability     |             |               |
| Delivery Feasibility    |             |               |
| Risk Exposure           |             |               |
| Stakeholder Alignment   |             |               |

**Composite Score:** (sum / 25 × 100 = %)

**Overall Decision:** (GO | NO-GO | CONDITIONAL GO | INSUFFICIENT DATA)
**Decision Rationale:** (3–5 sentences — be direct)

**Conditions (if CONDITIONAL GO):**
- (list of conditions that MUST be met before proceeding)

**Critical Blockers (if NO-GO):**
- (explicit blockers preventing delivery)

**Next Recommended Steps:**
- (bullet list, max 4 actions)

---
PROJECT INPUT:
{ctx.raw_input}
""".strip()

    def _parse_output(self, raw: str) -> dict:
        decision = GoNoGoDecision.INSUFFICIENT
        for d in GoNoGoDecision:
            if d.value.lower() in raw.lower():
                decision = d
                break

        # Extract composite score
        score = None
        score_match = re.search(r"Composite Score.*?(\d+(?:\.\d+)?)\s*%", raw, re.IGNORECASE)
        if score_match:
            try:
                score = float(score_match.group(1))
            except ValueError:
                pass

        return {
            "decision":      decision.value,
            "composite_pct": score,
            "full_analysis": raw.strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT 4 — Site Readiness
# ══════════════════════════════════════════════════════════════════════════════
class SiteReadinessAgent(BaseAgent):
    """
    Operational and site-level readiness for delivery.
    Broad definition: 'site' = physical site, digital environment, or operational context.
    """
    name = "SiteReadinessAgent"

    def _system_prompt(self) -> str:
        return (
            "You are an Infrastructure Delivery Programme Manager and Site Readiness Expert. "
            "You assess whether a site, environment, or operational context is ready "
            "for project delivery to commence. "
            "'Site' is interpreted broadly: physical sites, cloud environments, "
            "office locations, data centres, or operational setups. "
            "Where information is absent, you flag it clearly rather than assuming readiness. "
            "You are methodical and conservative — readiness gaps are risks, not opinions."
        )

    def _user_prompt(self, ctx: ProjectContext) -> str:
        return f"""
Assess the site and operational readiness for the project described below.

Use status flags: ✅ Ready | ⚠️ Partial | ❌ Not Ready | ❓ Unknown

**SITE READINESS ASSESSMENT**

**Readiness Checklist:**

| Domain                              | Status | Evidence / Notes |
|-------------------------------------|--------|-----------------|
| Physical / Digital Infrastructure   |        |                 |
| Resource & Staffing Availability    |        |                 |
| Access Rights & Permissions         |        |                 |
| Predecessor Dependencies Closed     |        |                 |
| Environmental / Regulatory Approvals|        |                 |
| Tooling & Systems Readiness         |        |                 |
| Supply Chain / Vendor Readiness     |        |                 |
| Connectivity & Network Readiness    |        |                 |

**Overall Readiness Score:** (0–100% — be conservative; unknown = not ready)
**Readiness Narrative:** (3–5 sentences)

**Top Readiness Blockers:**
- (bullet list, max 3; most critical first)

**Recommended Pre-Delivery Actions:**
- (bullet list, max 5; prioritised)

**Earliest Realistic Start Date Assessment:** (based on stated or inferable information)

---
PROJECT INPUT:
{ctx.raw_input}
""".strip()

    def _parse_output(self, raw: str) -> dict:
        score = None
        score_match = re.search(
            r"Overall Readiness Score.*?(\d+(?:\.\d+)?)\s*%", raw, re.IGNORECASE
        )
        if score_match:
            try:
                score = float(score_match.group(1))
            except ValueError:
                pass

        return {
            "readiness_pct": score,
            "full_analysis": raw.strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT 5 — Executive Summary
# ══════════════════════════════════════════════════════════════════════════════
class ExecutiveSummaryAgent(BaseAgent):
    """
    Synthesises all prior agent outputs into a C-suite executive summary.
    Runs LAST after all other agents complete.
    Receives enriched context via a combined prompt.
    """
    name = "ExecutiveSummaryAgent"

    def _system_prompt(self) -> str:
        return (
            "You are an executive ghostwriter and Chief of Staff advisor "
            "to a Programme Director. "
            "You synthesise complex programme analyses into crisp, board-ready "
            "executive summaries. "
            "Rules: No jargon. No padding. No hedging. "
            "Structured for a 90-second read. "
            "Every sentence must earn its place. "
            "Missing data = explicit gap statement, not silence."
        )

    def _user_prompt(self, ctx: ProjectContext) -> str:
        # ctx.raw_input for this agent contains the synthesised prior outputs
        return f"""
Using the full project analysis below, write a concise Executive Summary
suitable for a C-suite or Board audience.

Use EXACTLY this structure:

**EXECUTIVE SUMMARY**

**Project at a Glance:**
(2–3 sentences: what the project is, why it exists, key timeline)

**Delivery Approach:**
(1–2 sentences: recommended methodology and why)

**Decision:** [GO ✅ | NO-GO ❌ | CONDITIONAL GO ⚠️ | INSUFFICIENT DATA ❓]
(1–2 sentences explaining the basis for the decision)

**Readiness Status:** [score]%
(1 sentence on the primary readiness concern, or 'Operationally ready to proceed')

**Top 3 Risks / Concerns:**
1. ...
2. ...
3. ...

**Recommended Immediate Actions:**
1. (owner — action — due)
2. (owner — action — due)
3. (owner — action — due)

**Bottom Line:**
(One punchy sentence: the single most important thing the board should know)

---
ANALYSIS INPUT (do not reproduce verbatim — synthesise):
{ctx.raw_input}
""".strip()

    def _parse_output(self, raw: str) -> dict:
        # Extract the decision line for quick display
        decision_match = re.search(
            r"\*\*Decision:\*\*\s*\[(.+?)\]", raw, re.IGNORECASE
        )
        decision_label = decision_match.group(1).strip() if decision_match else "See report"

        return {
            "decision_label": decision_label,
            "full_summary":   raw.strip(),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT ORCHESTRATOR
# ══════════════════════════════════════════════════════════════════════════════
class AgentOrchestrator:
    """
    Orchestrates the Phase 1 pipeline.

    Execution pattern:
      - Agents 1–4 run in PARALLEL (threads).
      - Agent 5 (ExecutiveSummary) runs AFTER all others complete,
        receiving synthesised outputs as its context.

    Phase 2 hooks (not active):
      - Conversational history: pass conversation_history to ProjectContext
      - Agent-to-agent messaging: route agent outputs to downstream agents
      - RAG enrichment: inject vector_context into each agent prompt
      - Memory persistence: already wired to OperationalMemory below

    Args:
        api_key: Anthropic API key. Defaults to ANTHROPIC_API_KEY env var.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not found. "
                "Set it via: export ANTHROPIC_API_KEY='sk-ant-...'"
            )

        # Instantiate Phase 1 agents
        self._summary_agent    = ProjectSummaryAgent(self._api_key)
        self._method_agent     = MethodologyAgent(self._api_key)
        self._gonogo_agent     = GoNoGoAgent(self._api_key)
        self._readiness_agent  = SiteReadinessAgent(self._api_key)
        self._exec_agent       = ExecutiveSummaryAgent(self._api_key)

        # Memory (optional — graceful if unavailable)
        self._memory = OperationalMemory() if _MEMORY_AVAILABLE else None

    # ── Public interface ──────────────────────────────────────────────────────

    def run_pipeline(
        self,
        raw_text: str,
        source_type: str = "text",
        filename: Optional[str] = None,
        progress_callback=None,  # callable(agent_name, status) for UI updates
    ) -> PipelineReport:
        """
        Execute the full Phase 1 analysis pipeline.

        Args:
            raw_text:          Project text to analyse.
            source_type:       'text' or 'file'.
            filename:          Original filename if source_type is 'file'.
            progress_callback: Optional UI hook for streaming progress updates.

        Returns:
            PipelineReport with all agent outputs.
        """
        t_pipeline_start = time.time()

        ctx = ProjectContext(
            raw_input=raw_text,
            source_type=source_type,
            filename=filename,
        )

        # ── Phase A: Agents 1–4 in parallel ──────────────────────────────────
        results: dict[str, Optional[AgentResult]] = {
            "summary":   None,
            "method":    None,
            "gonogo":    None,
            "readiness": None,
        }

        def run_agent(key: str, agent: BaseAgent, agent_ctx: ProjectContext):
            if progress_callback:
                progress_callback(agent.name, "running")
            results[key] = agent.run(agent_ctx)
            if progress_callback:
                progress_callback(agent.name, "done")

        threads = [
            threading.Thread(
                target=run_agent, args=("summary",   self._summary_agent,   ctx)
            ),
            threading.Thread(
                target=run_agent, args=("method",    self._method_agent,    ctx)
            ),
            threading.Thread(
                target=run_agent, args=("gonogo",    self._gonogo_agent,    ctx)
            ),
            threading.Thread(
                target=run_agent, args=("readiness", self._readiness_agent, ctx)
            ),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Propagate detected project name
        if results["summary"] and results["summary"].succeeded:
            data = results["summary"].output
            if isinstance(data, dict):
                ctx.project_name = data.get("project_name")

        # ── Phase B: Executive Summary (sequential, reads all prior outputs) ─
        if progress_callback:
            progress_callback(self._exec_agent.name, "running")

        exec_ctx = self._build_exec_context(ctx, results)
        exec_result = self._exec_agent.run(exec_ctx)

        if progress_callback:
            progress_callback(self._exec_agent.name, "done")

        # ── Assemble report ───────────────────────────────────────────────────
        total_ms = round((time.time() - t_pipeline_start) * 1000, 2)

        report = PipelineReport(
            project_summary=results["summary"]
                or self._error_result("ProjectSummaryAgent"),
            methodology=results["method"]
                or self._error_result("MethodologyAgent"),
            go_no_go=results["gonogo"]
                or self._error_result("GoNoGoAgent"),
            site_readiness=results["readiness"]
                or self._error_result("SiteReadinessAgent"),
            executive_summary=exec_result,
            total_elapsed_ms=total_ms,
            run_timestamp=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        )

        # ── Persist to memory ─────────────────────────────────────────────────
        self._persist_to_memory(ctx, report)

        logger.info(
            f"[Orchestrator] Pipeline complete in {total_ms:.0f}ms "
            f"for project '{ctx.project_name or 'unnamed'}'."
        )
        return report

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_exec_context(
        self,
        ctx: ProjectContext,
        results: dict[str, Optional[AgentResult]],
    ) -> ProjectContext:
        """
        Build a synthetic context for the ExecutiveSummaryAgent
        by concatenating all prior outputs into a single text block.
        """

        def safe_text(key: str, label: str) -> str:
            r = results.get(key)
            if r and r.succeeded and r.output:
                if isinstance(r.output, dict):
                    return f"=== {label} ===\n{r.output.get('full_brief') or r.output.get('full_analysis') or str(r.output)}"
                return f"=== {label} ===\n{r.output}"
            return f"=== {label} ===\n[AGENT ERROR — output not available]"

        combined = "\n\n".join([
            f"Original Project Input (excerpt, first 1000 chars):\n{ctx.raw_input[:1000]}",
            safe_text("summary",   "PROJECT BRIEF"),
            safe_text("method",    "METHODOLOGY RECOMMENDATION"),
            safe_text("gonogo",    "GO/NO-GO ASSESSMENT"),
            safe_text("readiness", "SITE READINESS"),
        ])

        return ProjectContext(
            raw_input=combined,
            source_type="synthesised",
            project_name=ctx.project_name,
        )

    def _persist_to_memory(self, ctx: ProjectContext, report: PipelineReport) -> None:
        """Write key decisions to OperationalMemory if available."""
        if not self._memory:
            return
        try:
            if report.go_no_go.succeeded and isinstance(report.go_no_go.output, dict):
                self._memory.add("decisions", {
                    "project":   ctx.project_name,
                    "decision":  report.go_no_go.output.get("decision"),
                    "timestamp": report.run_timestamp,
                })
            if report.methodology.succeeded and isinstance(report.methodology.output, dict):
                self._memory.add("lifecycle_recommendations", {
                    "project":     ctx.project_name,
                    "methodology": report.methodology.output.get("methodology"),
                    "confidence":  report.methodology.output.get("confidence"),
                })
            if report.site_readiness.succeeded and isinstance(report.site_readiness.output, dict):
                pct = report.site_readiness.output.get("readiness_pct")
                if pct is not None:
                    self._memory.add("cutover_readiness", {
                        "project": ctx.project_name,
                        "score":   pct,
                    })
        except Exception as exc:
            logger.warning(f"[Orchestrator] Memory persist failed: {exc}")

    @staticmethod
    def _error_result(agent_name: str) -> AgentResult:
        return AgentResult(
            agent_name=agent_name,
            reasoning="Agent did not complete.",
            output=None,
            error="No result returned from thread.",
        )


# ── Module-level convenience ───────────────────────────────────────────────────
def get_orchestrator(api_key: Optional[str] = None) -> AgentOrchestrator:
    """Factory function — use in app.py to obtain a cached orchestrator."""
    return AgentOrchestrator(api_key=api_key)
