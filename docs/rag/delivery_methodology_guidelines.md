# Delivery Methodology Guidelines

Use this guide to recommend an indicative delivery approach from Discovery, Requirements, Solution, and customer facts.

Methodology is how the team develops and delivers work. Delivery constraints are how delivery is planned, governed, and controlled. A constraint does not automatically change the methodology.

Iterative or agile development commonly operates inside fixed timeframes, budgets, capacity, scope boundaries, milestones, external dependencies, UAT or release gates, and contractual or regulatory constraints. That is normal delivery management, not a reason to abandon Scrum or Kanban.

The recommendation is not a customer-confirmed commitment unless the customer explicitly selected the methodology. If evidence is insufficient, state the unconfirmed assumptions and keep confidence low. Do not invent a methodology. Do not default to Hybrid.

## Methodology selection criteria

Form the recommendation from:

- delivery approach signals
- delivery constraints
- evidence of additional control or governance requirements

No single factor is decisive. Do not use numeric scores or weights. Do not treat mixed evidence as Hybrid.

### Delivery approach signals

1. **Requirements stability / volatility.** Evolving or incompletely known requirements favor Scrum or Kanban. Stable, fully specified scope favors Waterfall.
2. **Incremental vs single-cutover delivery.** Incremental value favors Scrum or Kanban. A single or tightly coupled go-live favors Waterfall, or Hybrid only if the product is still built iteratively behind an explicit release gate.
3. **Stakeholder feedback and reprioritization.** Frequent review and backlog reordering favor Scrum. Continuous flow visibility favors Kanban. Formal stage reviews as the main control favor Waterfall.
4. **Backlog / prioritization model.** An owned, ordered Product Backlog supports Scrum. A managed queue with WIP discipline supports Kanban. A frozen scope baseline supports Waterfall.
5. **Planned vs flow-based work.** Planned product work fits Scrum. Continuously arriving or interrupt-driven work fits Kanban. A genuine mix of both operating models can support Hybrid (Scrumban).
6. **Dependency structure.** Ordinary system or vendor work inside sprints or flow is not a methodology change. Sequential phase dependencies that cannot overlap safely favor Waterfall. Dependencies that need a separate checkpoint regime alongside iteration can support Hybrid.

### Delivery constraints

Typical constraints:

- fixed timeframe / target date
- fixed budget or capacity
- fixed scope / scope boundaries
- contractual milestones
- external dependencies
- regulatory / compliance gates
- UAT / release gates
- environment / vendor constraints

A deadline, budget, named integration, or short delivery window alone is not evidence for Hybrid or Waterfall.

Scrum can manage a fixed date or budget through backlog ordering, sprint goals, forecasting and scope management.

Kanban can operate within delivery constraints through flow management, WIP limits and forecasting.

Hybrid is appropriate when iterative/agile delivery operates alongside explicit additional planning, milestone, governance, change-control, integration, UAT, compliance or release mechanisms that create a second control layer.

These are examples of that second layer, not automatic rules:

- 2-week Scrum iterations + fixed overall delivery window + explicit milestone plan
- Scrum iterations + mandatory UAT/release gate
- iterative product development + contractual approval gate
- iterative delivery + external integration checkpoints coordinated separately from Sprint or flow reviews
- Scrum/Kanban delivery + a separate fixed budget/capacity change-control process
- planned product work + interrupt-driven support flow (Scrumban)

## 1. Scrum

Iterative product delivery with a prioritized backlog, timeboxed Sprints, incremental value, regular inspection/adaptation and stakeholder feedback. Delivery constraints can be managed inside this operating model.

### Best suited for

- evolving requirements
- product development
- incremental delivery
- regular stakeholder feedback
- prioritized backlog
- Product Owner available
- stable team able to protect Sprint Goals
- requirements that can continue to evolve within Sprint boundaries
- fixed date, budget, or capacity constraints that can be managed through backlog ordering, forecasting and scope management without a separate phase or milestone control regime

### Less suited for

- mostly interrupt-driven work
- continuously arriving work where Sprint cadence adds little value
- environments where Sprint Goals cannot be protected
- highly sequential phase-gated delivery
- contractual or regulatory gates that sit outside the normal Scrum operating model
- single-cutover delivery with little opportunity for incremental value

### Typical cadence / delivery model

1–2 week Sprints are typical. A short overall delivery window, including a 1–2 month target, does not make Scrum inappropriate. Do not assume a universal ceremony overhead.

### Core practices / events

- Sprint Planning
- Daily Scrum
- Sprint Review
- Sprint Retrospective
- Product Backlog refinement / ongoing backlog management
- Sprint Goals
- Incremental delivery

### Governance characteristics

Date, budget, and capacity can be managed through backlog ordering, scope management, Sprint Goals, forecasting, and regular stakeholder inspection. These are Scrum controls, not Waterfall gates.

## 2. Kanban

Continuous-flow delivery where WIP and flow are managed explicitly. A fixed Sprint cadence is optional, not required.

### Best suited for

- interrupt-driven work
- continuously arriving work
- support / operations
- mixed BAU and enhancement queues
- independently releasable work
- variable item size
- situations where a fixed Sprint cadence is less useful

### Less suited for

- large coordinated increments requiring shared Sprint Goals
- work that needs fixed multi-week batch planning
- phase-gated programmes
- situations where WIP discipline cannot be maintained

### Typical cadence / delivery model

Continuous flow rather than a mandatory Sprint cadence. Replenishment and review happen as needed.

### Core practices / governance

- WIP limits
- explicit workflow policies
- replenishment
- flow metrics
- cycle / lead time
- regular review of priorities and flow

## 3. Waterfall / Phase-gated

Sequential, phase-gated delivery where stable requirements and explicit phase dependencies make iterative adaptation less central.

### Best suited for

- stable, well-specified requirements
- sequential dependencies that cannot safely overlap
- contractual or regulatory stage gates
- single-cutover delivery
- tightly coupled go-live
- vendor, infrastructure, or environment freeze windows
- formal approval gates

### Less suited for

- evolving requirements
- discovery-heavy work
- frequent stakeholder feedback and reprioritization
- early incremental customer value
- product teams that can iterate effectively, even if a date or budget exists

### Typical cadence / delivery model

Sequential phases with planned transitions and explicit gates (for example analysis, design, build, test, deploy).

### Governance characteristics

- baseline and change control
- formal decision rights
- phase exit criteria
- documented approvals
- progress against plan and gate criteria

## 4. Hybrid / Scrumban

Hybrid combines iterative or flow-based delivery with an explicit additional control layer or a genuinely mixed operating model.

Hybrid is NOT simply Scrum plus a deadline.

Hybrid is NOT required just because the project is short.

Hybrid is NOT required just because external systems are involved.

When recommending Hybrid, name the additional control layer or the mixed operating model.

### Best suited for

These are examples, not automatic rules:

1. Scrum-style 2-week iterations + fixed overall delivery window + explicit milestone plan
2. Iterative product development + mandatory integration, UAT, or release gates
3. Agile development + contractual or regulatory phase gates
4. Iterative delivery inside fixed budget or capacity constraints where separate change-control is required
5. Scrum or Kanban product work + interrupt-driven support flow
6. External dependencies requiring coordinated checkpoints or environment freeze windows in addition to normal Sprint or flow reviews
7. Programmes where the product is built iteratively but final release is controlled by explicit gates

### Less suited for

- a deadline alone
- a fixed budget alone
- a named integration alone
- a short 1–2 month project alone
- a healthy Scrum team that can manage constraints within Scrum
- a pure continuous-flow team that only needs Kanban
- a stable phase-gated project that only needs Waterfall
- situations where Hybrid is used as a vague label without identifying the additional control layer

### Typical cadence / delivery model

State what is iterative or flow-based and what is gated. Examples: 2-week Sprints for product development plus milestone or release controls; continuous flow plus fixed release gates; iterative development plus a UAT or release window.

### Core practices

Include only practices that match the identified Hybrid shape:

- backlog / queue management
- Sprint events where appropriate
- WIP limits where appropriate
- milestone tracking
- integration checkpoints
- UAT gates
- release readiness gates
- contractual / compliance gates
- change-control where explicitly required

### Governance characteristics

Identify the additional control layer. Avoid duplicate ceremonies and duplicate reporting. Explain what runs iteratively, what is controlled through milestones or gates, and why that extra layer is needed.

## Same project: Scrum vs Hybrid

The difference is not the existence of the deadline. The difference is whether the delivery constraints require a second control mechanism alongside the iterative workflow.

### Example A — Scrum

The project has evolving requirements, a prioritized backlog, a Product Owner, regular stakeholder reviews, incremental delivery, a 2-month target, and a fixed budget or capacity. The team manages the date through backlog ordering, scope control, Sprint Goals, and forecasting. Recommendation can still be Scrum.

### Example B — Hybrid

The same project also has an explicit milestone plan, mandatory SAP/Stripe integration checkpoints, a fixed UAT window, and a release readiness gate. Recommendation can reasonably be Hybrid because there is an explicit additional control layer alongside iterative development.

## Important example

Customer self-service web application with SAP S/4HANA and Stripe integration, evolving UI/UX, Product Owner and stakeholder reviews, a prioritized backlog, incremental delivery, a 2-month internal target, and no regulatory phase gates.

That evidence can support Scrum: the integrations are ordinary product work, and the date is a forecast horizon managed inside Scrum.

If the same project also has an explicit milestone plan, mandatory integration checkpoints, a fixed UAT window, and a release gate, Hybrid becomes reasonable because those mechanisms are a second control layer.

Do not force one answer from the example. Use it to apply the distinction.

## Recommendation language

- Recommend one primary methodology.
- Explain the evidence supporting it.
- Mention alternatives only when useful.
- If confidence is low, state the missing evidence.
- Do not invent customer commitments.
- Do not use numeric scores.
- Do not infer Hybrid merely from deadline, budget, short duration, or integrations.
- When recommending Hybrid, explicitly name the additional control layer or mixed operating model that makes it Hybrid.
- If recommending Scrum under fixed delivery constraints, explicitly explain how those constraints are managed within Scrum.
