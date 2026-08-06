# Phase 2 Design Review — Post v1.1.0 Planning

**Document type:** Roadmap + Design Review only (**no coding authorized**)  
**Date:** 2026-07-22  
**Baseline:** GitHub Release **v1.1.0** · tag `v1.1.0` · commit `6d80ef3`  
**Prior closed:** Phase 1 (Sprints 1–4) · Trust + Runtime Honesty + Product Shell  

**Spine (immutable unless a future Design Review explicitly reopens it):**

```text
Product Shell → Worker → Kernel → Skill → Policy → Data Plane → Trace / Artifacts
```

**Process constraints:**

- Do **not** create tag `v2.0.0` early  
- Do **not** code until a scoped Sprint is authorized after this review  
- Do **not** large-refactor without a dedicated Design Review PASS  
- Do **not** break Gate / Worker-as-governor / Skill-no-terminal-status invariants  

**Related SSOT:**  
`docs/V1_1_FINAL_AUDIT.md` · `docs/HITL_SQL_APPROVAL_DESIGN.md` · `docs/ADR_TOKEN_STORAGE.md` · `docs/ROADMAP_V2.md` · `docs/V2_IMPLEMENTATION_PLAN.md` (Phase 1 — closed)

---

## 0. Verdict of this review (planning)

| Question | Answer |
|----------|--------|
| Phase 1 closed? | **Yes** — v1.1.0 published |
| Enter coding now? | **No** — Design Review / roadmap confirmation only |
| Create `v2.0.0` tag? | **No** — evaluate only after major capability is **stable** |
| Spine change proposed now? | **None** |

**Recommended next human decision:** Confirm version split (§2–3) and choose **first Phase 2 Design Track** (§5) before any implementation Sprint.

---

## 1. Where we are (post v1.1.0)

### 1.1 Closed narrative

| Version | Meaning |
|---------|---------|
| **v1.0.0** | Governed platform spine frozen |
| **v1.1.0** | Trust + Runtime Honesty + Product Shell (Phase 1 complete) |

Phase 1 delivered: P1.1–P1.8, P1.10, HITL **design-only**.  
P1.9 (Settings / skill catalog coupling) was **explicitly out of v1.1 mainline**.

### 1.2 Residual non-blocking backlog (from Sprint reviews)

These are **hardening / UX polish**, not new platform narratives:

1. Dataset `/preview` dedicated HTTP smoke  
2. ACL member-picker UX (beyond raw UUID entry)  
3. Artifact **cold** fidelity (object store) — today omissions document post-slim hot refs  
4. `smoke_result_payload` assert of production defaults (optional)  
5. Preview redact fail-open policy documentation/hardening  

### 1.3 Explicitly deferred from v1.1 Non-goals

| Theme | v1.1 state |
|-------|------------|
| HITL SQL approval **code** | Design ADR only |
| Cookie / HttpOnly auth | ADR — localStorage accepted |
| Semantic Layer | Not started |
| Multi-Agent Runtime | Not started |
| Wave 4 IaC / K8s | Not started |
| Celery / RAG / Catalog mega-product | Won't-Do |

---

## 2. Version policy (v1.2.x vs v2.0.0)

### 2.1 Rule of thumb

| Line | When to use | Tag posture |
|------|-------------|-------------|
| **v1.2.x** | Spine-compatible increments: trust polish, UX, optional additive Run flags, thin refactors, cold storage, observation tooling | Patch/minor on `main` after Design → Impl → Review → Audit |
| **v2.0.0** | **Major product/architecture step** that changes the pilot narrative or Run collaboration model in a material way — only after capability is **implemented, gated, and stable** | **Do not pre-create**; cut only after Final Audit PASS |

**v2.0.0 is an outcome, not a workstream name.**  
“Phase 2 planning” may produce multiple **v1.2.x** releases before any `v2.0.0` is justified.

### 2.2 What belongs in **v1.2.x** (incremental)

Items that **extend** v1.1 without replacing the spine story:

| ID | Candidate | Notes | Spine risk |
|----|-----------|-------|------------|
| **R1** | Residual Sprint P2 polish (preview smoke, ACL picker UX) | Low cost; raises demo quality | Low |
| **R2** | P1.9 Settings / skill-catalog coupling **thin** cleanup | Design-gated; no mega-refactor day without review | Med (if unbounded) |
| **R3** | Cookie / HttpOnly MVP (when ADR triggers fire) | Auth surface only; CSRF/CORS design first | Low–Med |
| **R4** | Cold object-store (or equivalent) for truncated artifacts | Completes P1.4 cold path; Worker persist policy only | Low |
| **R5** | Cost / budget read-only UI (thin) | Shell visibility of existing budget counters | Low |
| **R6** | OIDC login UI + staging IdP soak | Feature-flagged; no Gate change | Low |
| **R7** | mysql-ro FE bind when DSN configured | Finish stub from P1.10 | Low |
| **R8** | Eval observation helpers / gate report diff | Ops quality; not product sprawl | Low |
| **R9** | HITL **MVP** (optional flag, `awaiting_approval`, approve/reject) | **Only after dedicated HITL Implementation Design Review**; additive status + Shell→Worker commands; Skill still never terminals | **Med–High** (state machine) |

**Guidance on R9:** Prefer shipping HITL MVP as **v1.2.x** *if* Design Review proves it is additive to existing Run states and Gate remains authoritative. If implementation forces a Run-model rewrite or multi-party workflow product, **reclassify as v2.0.0 driver** (§2.3).

### 2.3 What may justify **v2.0.0** (future major)

Cut `v2.0.0` only when **at least one** major differentiator is **stable** and Exit Criteria written. Candidates:

| ID | Candidate | Why major | Spine impact |
|----|-----------|-----------|--------------|
| **M1** | HITL as full analyst workflow (policy-required approval, audit export, multi-role) | Changes trust UX narrative beyond “optional pause” | Worker status model + Shell |
| **M2** | Workspace **Semantic Layer** (thin metrics/dimensions → linking) | New governed knowledge plane into Skill linking | Skill/linking; Gate still final |
| **M3** | Fixed-role **Multi-Agent** (Planner / Writer / Critic) | New Kernel orchestration pattern; not free ReAct | Kernel; Skill must stay gated |
| **M4** | Wave 4 **single-cloud IaC** + secret hygiene (pilot deployable) | Changes delivery maturity claim | Ops; not analysis spine |
| **M5** | Controlled **Agentic BI** multi-step plans under Worker | Extends Run semantics beyond single Skill path | Worker/Kernel |

**Not enough alone for v2.0.0:** Cookie MVP, ACL picker polish, cold blob store, budget UI, P1.9 thin cleanup — those stay **v1.2.x**.

### 2.4 Explicit Won't-Do (still)

- Free-form ReAct / open Agent marketplace  
- RAG-as-primary product  
- Full LookML/dbt semantic platform / universal Catalog vendor  
- Multi-cloud IaC in one release  
- Softening Policy Gate to “make demos pass”  
- Large directory rewrites without Design Review  

---

## 3. Phase 2 planning map (tracks, not yet Sprints)

```text
Phase 2 Planning (now)
        │
        ├─ Track A — Hardening & Shell polish     → typically v1.2.0 / v1.2.1
        ├─ Track B — Trust storage (Cookie)       → v1.2.x when triggers met
        ├─ Track C — Payload cold path            → v1.2.x
        ├─ Track D — HITL implementation design   → v1.2.x MVP or v2.0 driver
        ├─ Track E — Semantic thin layer design   → likely v2.0.0 driver
        ├─ Track F — Fixed-role Multi-Agent design→ likely v2.0.0 / later
        └─ Track G — Wave 4 deploy design         → likely v2.0.0 co-driver
```

No Track is authorized for coding by this document.

---

## 4. Spine guardrails (non-negotiable for Phase 2)

1. **Worker** remains sole Run governor (status, cancel, timeout, HITL transitions).  
2. **Skill** never writes terminal status; never bypasses Policy Gate for SQL execute.  
3. **Policy Gate** semantics unchanged unless a dedicated ADR + Eval cases say otherwise.  
4. **Product Shell** consumes APIs only — no direct Agent / Plane calls.  
5. **Trace / Artifacts** remain execution truth; UI must not invent success.  
6. Large refactors (P1.9 mega-clean, Connector protocol rewrite, Celery migration) require **separate Design Review PASS** and a bounded PR charter.

---

## 5. Recommended Design Track order (confirmation menu)

| Priority | Track | First deliverable (docs only) | Likely version |
|----------|-------|-------------------------------|----------------|
| **1** | **D — HITL Implementation Design** | Expand `HITL_SQL_APPROVAL_DESIGN.md` → implementable checklist (states, timeout policy, failure_class, FE wireframe, Gate interaction, Eval) | v1.2.x MVP *or* reclass to v2 |
| **2** | **A — Hardening pack** | Mini-charter for R1 leftovers (smokes + ACL picker) | v1.2.0 |
| **3** | **C — Cold artifacts** | ADR: object store vs DB blob vs accept hot-only forever | v1.2.x |
| **4** | **B — Cookie** | Only if ADR triggers (threat model / same-site / pen-test) | v1.2.x |
| **5** | **E — Semantic thin layer** | Metrics/dimensions schema + linking contract draft | **v2.0.0 candidate** |
| **6** | **F / G** | Multi-Agent fixed graph · Wave 4 IaC | **v2.0.0 candidates** |

**Default recommendation for confirmation:**  
Start with **Track D (HITL Implementation Design Review)** in parallel with a **small Track A charter** for v1.2.0 polish — still **docs only** until coding is authorized.

---

## 6. Exit ideas (draft — not binding)

### 6.1 Example v1.2.0 (hardening)

- Residual R1 items closed or explicitly deferred with owners  
- Gate / Eval still PASS  
- No Spine drift · no v2 tag  

### 6.2 Example v1.2.x (HITL MVP) — if classified incremental

- `awaiting_approval` + approve/reject APIs · Shell banner · cancel/timeout honesty  
- Feature flag default **off** for back-compat  
- Eval/smoke for approve/reject/cancel-while-waiting  
- Still **not** Semantic / Multi-Agent / IaC  

### 6.3 Example v2.0.0 (only when ready)

Pick a **primary narrative** (recommend one):

- **Pilot Differentiated:** Semantic thin layer **and/or** HITL-as-required workflow stable, **or**  
- **Pilot Deployable:** Wave 4 single-cloud path stable  

Plus: Final Audit PASS · CHANGELOG · Release notes · **then** tag `v2.0.0`.

---

## 7. Decisions requested from operator

Please confirm or adjust:

| # | Decision | Options |
|---|----------|---------|
| **D1** | Accept version split (§2): polish/Cookie/cold/HITL-MVP → **v1.2.x**; Semantic / Multi-Agent / Wave4 / HITL-as-product → **v2.0.0 candidates** | Accept / Amend |
| **D2** | First Design Track | **D (HITL)** / **A (Hardening)** / **C (Cold)** / Other |
| **D3** | HITL classification preference | Prefer **v1.2.x MVP** if additive / Prefer hold HITL for **v2.0.0** |
| **D4** | Coding freeze | Remain **Design-only** until explicit Sprint auth | **Required: Yes** |

---

## 8. Explicit non-actions (this document)

| Action | Status |
|--------|--------|
| Business coding | **Not authorized** |
| Tag `v2.0.0` | **Forbidden** |
| Force push / history rewrite | **Forbidden** |
| Scope expansion into RAG / free Multi-Agent / Catalog platform | **Rejected** |

---

## 9. Next step after confirmation

1. Operator returns D1–D4.  
2. Author a **Track-specific Design Review** (e.g. `docs/HITL_IMPLEMENTATION_DESIGN_REVIEW.md` or `docs/V1_2_HARDENING_CHARTER.md`).  
3. Only then: Implementation → Review → Commit → Audit → (optional) tag `v1.2.x`.  
4. Defer any `v2.0.0` discussion until a major track is **stable**.

---

**End of Phase 2 Design Review (planning).**  
Awaiting operator confirmation of D1–D4 before any further design deep-dive or coding.
