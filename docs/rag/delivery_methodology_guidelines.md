# Delivery Methodology & Framework Guidelines

Use this guide to recommend a delivery approach from project characteristics. Present the recommendation as indicative, not as a customer-confirmed commitment, unless the customer has already selected a methodology.

## Methodology selection criteria

Consider these characteristics together. No single factor is decisive.

- **Requirements stability.** Evolving or incompletely known requirements favor iterative or flow-based methods. Stable, fully specified scope favors phase-gated delivery.
- **Planned vs interrupt-driven work.** Planned, backlog-driven work fits Scrum or Waterfall. Unpredictable incoming work fits Kanban. Mixed intake often fits Hybrid.
- **Stakeholder feedback.** Frequent review and reprioritization favor Scrum. Continuous visibility of flow favors Kanban. Formal stage reviews favor Waterfall. Mixed cadence favors Hybrid.
- **Incremental vs single-cutover release.** Incremental value favors Scrum or Kanban. A single cutover, big-bang go-live, or tightly coupled release train favors Waterfall or a Hybrid with a gated final phase.
- **Contractual / compliance phase gates.** Mandatory design, security, or acceptance gates favor Waterfall or Hybrid with explicit gated stages. Lightweight product delivery does not require them.
- **Backlog / prioritization maturity.** A owned, ordered backlog supports Scrum. A managed queue with WIP discipline supports Kanban. A frozen scope baseline supports Waterfall. Partial maturity often points to Hybrid.
- **Dependency structure.** Independent, parallelizable work favors Scrum or Kanban. Long sequential dependencies, vendor handoffs, or environment freeze windows favor Waterfall or Hybrid with phase gates around those constraints.

Do not invent a methodology the customer already confirmed. If evidence is mixed or thin, prefer Hybrid and state the unconfirmed assumptions.

---

## 1. Scrum

### Best suited for
- evolving requirements
- product development
- incremental delivery
- regular stakeholder feedback
- prioritizable backlog
- a stable team that can commit to a sprint goal

### Less suited for
- mostly interrupt-driven work
- highly unpredictable incoming work
- fixed sequential phases
- environments where priorities cannot be changed
- single-cutover releases with little room for increment
- contractual stage gates that freeze scope between phases

### Typical cadence / delivery model
1–2 week timeboxed sprints with a potentially shippable increment each sprint.

### Core practices / events
- Sprint Planning
- Daily Scrum
- Backlog Refinement
- Sprint Review
- Sprint Retrospective
- Product Owner ownership of ordered backlog and sprint goal

### Governance characteristics
- lightweight inspection and adaptation each sprint
- progress shown through increment demo and backlog burn-down, not stage-gate sign-off
- change is expected inside the product backlog; the sprint goal is protected
- stakeholder authority sits mainly with the Product Owner, not a phase review board

---

## 2. Kanban

### Best suited for
- interrupt-driven or continuously arriving work
- support, operations, or mixed BAU and enhancement queues
- flow of small, independently releasable items
- teams that need to limit work in progress rather than commit to a sprint
- variable item size where timeboxing a batch is artificial

### Less suited for
- large coordinated increments that need a shared sprint goal
- work that must be planned and estimated as a fixed multi-week batch
- environments that require a frozen scope baseline for a phase
- teams without willingness to enforce WIP limits
- single-cutover programmes where flow of small items is not the delivery unit

### Typical cadence / delivery model
Continuous flow. Replenishment, delivery, and review happen on a cadence, but work is not timeboxed into sprints.

### Core practices / events
- explicit workflow stages and policies
- WIP limits
- replenishment / commitment meeting
- service delivery review
- flow metrics (lead time, throughput, ageing)
- pull-based intake rather than sprint commitment

### Governance characteristics
- manage flow and queue health rather than sprint commitment
- policies and WIP limits are the control mechanism
- change can enter when capacity exists, subject to classes of service
- reviews focus on service level, blockers, and ageing work, not a phase-gate packet

---

## 3. Waterfall / Phase-gated

### Best suited for
- stable, well-specified requirements
- contractual or regulatory stage gates
- sequential dependencies that cannot overlap safely
- single-cutover or tightly coupled go-live
- vendor, infrastructure, or environment freeze windows
- acceptance against a baselined specification

### Less suited for
- evolving product requirements
- frequent reprioritization during build
- interrupt-driven operational work
- early incremental customer value as the primary goal
- discovery-heavy work where the solution is still being shaped

### Typical cadence / delivery model
Sequential phases (for example analysis, design, build, test, deploy) with a planned end-to-end timeline and a gated transition between phases.

### Core practices / events
- baseline scope and specification
- phase kickoff and phase-end review
- design / architecture sign-off
- integrated test and acceptance against the baseline
- controlled change request after baseline
- cutover / go-live rehearsal where a single release is required

### Governance characteristics
- formal phase gates and documented decision rights
- change after baseline is exceptional and governed
- progress is measured against the plan, baseline, and gate criteria
- compliance, security, and customer acceptance often sit on the gate, not on a sprint review

---

## 4. Hybrid / Scrumban

### Best suited for
- mixed planned delivery and interrupt-driven work
- incremental build with a gated cutover, compliance, or release window
- partial backlog maturity: some work is sprintable, some is flow
- programmes that need Scrum-style iteration inside a phase-gated wrapper
- teams moving from Scrum toward flow, or from Waterfall toward iteration
- dependencies that force a few hard gates without freezing all delivery

### Less suited for
- purely interrupt-driven queues that only need Kanban
- fully stable, gated programmes that only need Waterfall
- product teams with a healthy backlog that can run Scrum without extra gates
- situations where mixing cadences would create unclear ownership of scope and WIP

### Typical cadence / delivery model
A combination of timeboxed iteration or continuous flow for build, plus explicit gates or a release train for integration, compliance, or go-live. Cadence is stated per stream (for example 2-week sprints for product work, continuous flow for incoming defects, gated release for production cutover).

### Core practices / events
- ordered backlog or queue for iterative / flow work
- WIP limits on flow streams; sprint planning only where a sprint goal is useful
- selected Scrum events (planning, review, retro) where they add inspection
- explicit replenishment for unplanned work so it does not silently consume sprint capacity
- phase or release gates only where contract, compliance, or cutover require them
- a single visible board or plan that shows both flow work and gated milestones

### Governance characteristics
- dual control: lightweight iteration for changeable work, formal gates for constrained work
- policies must say what may change mid-stream and what is baselined
- avoid duplicate status rituals; each event should serve either flow, sprint, or gate
- recommendation should name which parts are Scrum-like, Kanban-like, or gated, rather than using "hybrid" as a label with no shape
