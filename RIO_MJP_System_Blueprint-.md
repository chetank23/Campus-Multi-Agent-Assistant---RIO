# RIO-MJP
## Multi-Agent Campus Assistant & Automated Timetable Engine
### Authoritative System Blueprint, Technical Architecture, and Future Roadmap

**Project:** RIO-MJP — Multi-Agent Campus Assistant & Automated Timetable Engine  
**Institutional context:** REVA University / campus academic-management use case  
**Center:** Center for Intelligent Enterprise Systems  
**Faculty Mentor:** Srinivas P  
**Center Lead:** Karthik Kashyap  
**Document purpose:** Single source of truth for architecture, implementation boundaries, engineering standards, evaluation, and staged completion.

> **Document status:** This blueprint separates (1) the system reported as implemented, (2) the target architecture, and (3) planned work. A class, route, screen, test file, or dependency does not by itself prove a feature is complete. Repository inspection and reproducible tests remain the source of implementation status.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem, Objectives, and Research Outcomes](#2-problem-objectives-and-research-outcomes)
3. [Product Scope and Non-Goals](#3-product-scope-and-non-goals)
4. [Current Implementation Baseline](#4-current-implementation-baseline)
5. [Target System Architecture](#5-target-system-architecture)
6. [Technology Stack and Architectural Decisions](#6-technology-stack-and-architectural-decisions)
7. [Repository Organization](#7-repository-organization)
8. [Domain Model and Data Ownership](#8-domain-model-and-data-ownership)
9. [Authentication, Authorization, and Privacy](#9-authentication-authorization-and-privacy)
10. [API and Service Boundaries](#10-api-and-service-boundaries)
11. [Multi-Agent Architecture](#11-multi-agent-architecture)
12. [Supervisor Agent](#12-supervisor-agent)
13. [Query Agent](#13-query-agent)
14. [Scheduling Agent](#14-scheduling-agent)
15. [Resource Agent](#15-resource-agent)
16. [Tool Contracts, Shared State, and Conversation Continuity](#16-tool-contracts-shared-state-and-conversation-continuity)
17. [Timetable Optimization Engine](#17-timetable-optimization-engine)
18. [Independent Validator and Scorer](#18-independent-validator-and-scorer)
19. [Resource Allocation Engine](#19-resource-allocation-engine)
20. [Workflow State Machines and Human Oversight](#20-workflow-state-machines-and-human-oversight)
21. [Notifications, Audit, and Operational Workflows](#21-notifications-audit-and-operational-workflows)
22. [Frontend and User Experience](#22-frontend-and-user-experience)
23. [Academic Data Readiness and Ingestion](#23-academic-data-readiness-and-ingestion)
24. [Optional Retrieval-Augmented Generation](#24-optional-retrieval-augmented-generation)
25. [Testing and Quality Engineering](#25-testing-and-quality-engineering)
26. [Research Evaluation and Metrics](#26-research-evaluation-and-metrics)
27. [Reliability, Observability, and Performance](#27-reliability-observability-and-performance)
28. [Security Checklist](#28-security-checklist)
29. [Development Roadmap](#29-development-roadmap)
30. [Acceptance Criteria and Definition of Done](#30-acceptance-criteria-and-definition-of-done)
31. [Capstone Demonstration Plan](#31-capstone-demonstration-plan)
32. [Final Deliverables Checklist](#32-final-deliverables-checklist)
33. [Key Architectural Decisions and Open Dependencies](#33-key-architectural-decisions-and-open-dependencies)

---

# 1. Executive Summary

RIO-MJP is a campus-management system combining academic data, timetable optimization, shared-resource allocation, role-specific portals, and natural-language assistance within one secured application.

The system has two complementary execution paths:

1. **Deterministic application path:** React client → FastAPI endpoint → validated service → SQLAlchemy/PostgreSQL, or the existing timetable/resource engine where applicable.
2. **Conversational agent path:** React assistant → authenticated chat API → LangGraph Supervisor → authorized specialist agent → typed tool/service → PostgreSQL or an existing domain engine → grounded response.

The central design principle is that the LLM interprets requests and explains results; it does not become the authority for campus facts, identity, permissions, scheduling validity, booking availability, or mutation success.

- **PostgreSQL** is the operational source of truth.
- **OR-Tools CP-SAT** is the timetable optimization engine.
- **Independent Python validation** is the safety check on generated and manually edited schedules.
- **Domain services** execute authorized mutations and enforce transaction boundaries.
- **LangGraph agents** coordinate understanding, tool selection, and explanation.
- **Human administrators** retain control over consequential timetable operations and publication.

## 1.1 Active roles

The application has exactly three active roles:

- `ADMIN`
- `FACULTY`
- `STUDENT`

HOD and Timetable Coordinator are not active application roles. The authoritative workflow places timetable generation, review, validation, finalization, and publication under `ADMIN` permissions. Do not implement role-specific dashboards or permission rules for removed roles.

## 1.2 Current implementation snapshot

The latest reported application checkpoint is `ddfa313` (`feat(agents): implement supervisor and grounded query assistant`), following Stage 7 resource-engine checkpoint `b769ee2`. The pre-push audit reported the local branch and GitHub `main` synchronized, while a later local inspection showed `.gitignore` modified to ignore `REVA_School_of_CSE_Faculty.xlsx`. Verify actual repository state before relying on either condition.

Reported as implemented:

- FastAPI backend, PostgreSQL/SQLAlchemy foundation, authentication, and role enforcement.
- Academic and campus CRUD APIs.
- Existing Google OR-Tools timetable generation and lifecycle UI.
- Independent timetable validation/scoring code.
- Faculty and student timetable portals.
- Resource inventory, booking lifecycle, conflict checks, and Admin resource UI.
- Stage 9A LangGraph Supervisor + Query Agent foundation and Campus Assistant drawer.
- Deterministic/offline query handling for supported patterns, including active-room inventory counts.

Important caveats:

- Reported test outcomes are historical results from the relevant implementation reports, not a guarantee about the current working tree.
- The live Anthropic provider path has not been confirmed through a paid/live API call in the supplied reports; tests use offline/mocked behavior.
- Scheduling Agent and Resource Agent conversational orchestration remain planned work. Existing timetable generation and resource booking engines do not imply that the corresponding conversational agents are complete.
- Notifications, change-request workflows, audit-log UI, real institutional data ingestion, optional RAG, evaluation automation, and deployment still require assessment or implementation according to the roadmap.
- The available faculty workbook is a protected local source asset; it is not yet a substitute for official course assignments, availability, curriculum, room inventory, and timetable configuration.

---

# 2. Problem, Objectives, and Research Outcomes

## 2.1 Problem statement

Campus activities—including answering academic queries, creating timetables, and allocating shared facilities—often rely on fragmented tools and manual coordination. This can lead to duplicate effort, slow responses, room/faculty/batch conflicts, poor room utilization, and limited visibility into why a proposed schedule cannot be produced.

Timetable construction is a constrained optimization problem involving faculty, sections/batches, rooms, course requirements, availability, time slots, electives, and academic-calendar restrictions. Natural-language questions also require reliable access to private and institutional records without exposing information across users or roles.

## 2.2 Overall objective

Build an intelligent multi-agent campus assistant that:

1. Resolves supported user questions using authorized, current campus data.
2. Orchestrates specialized agents through a controlled Supervisor.
3. Uses the existing timetable solver to generate candidate schedules.
4. Explains readiness blockers, solver outcomes, and measurable trade-offs.
5. Manages shared-resource inventory and bookings through a conflict-aware domain service.
6. Retains human oversight for consequential operations.
7. Presents role-appropriate experiences for Admin, Faculty, and Student.
8. Produces reproducible research evidence for query resolution and scheduling quality.

## 2.3 Research outcomes

The final project should demonstrate:

- A working Supervisor, Query Agent, Scheduling Agent, and Resource Agent integrated with actual backend tools.
- A solver-backed timetable-generation pipeline with no hard-constraint violations in accepted/published results.
- Independent post-generation validation and computed schedule-quality metrics.
- Resource booking with conflict detection and suitable alternatives.
- A measurable query test set with intent/tool accuracy and query resolution rate.
- Comparative timetable evaluation across representative datasets.
- Reproducible tests and a demonstrable end-to-end workflow.

## 2.4 Non-negotiable principles

1. The LLM cannot invent campus facts or use model memory as evidence for database-backed claims.
2. The LLM cannot write timetable slots itself. It proposes parameters; the existing solver constructs the timetable.
3. A generated timetable must pass independent deterministic validation before being treated as valid for review/publication.
4. Every privileged endpoint and mutating tool enforces authorization server-side.
5. Every consequential mutation writes an audit record in a consistent transaction wherever supported by the domain transaction.
6. A success message must be derived from actual service/database results, never from an LLM's assertion.
7. A draft is not a published timetable. Generation, review, validation, finalization, and publication remain distinct states.
8. Missing institutional data must be reported, not fabricated.
9. Each development stage has its own diff review, tests, and local Git checkpoint.
10. Deployment is a final project phase, not a prerequisite for ongoing local development.

---

# 3. Product Scope and Non-Goals

## 3.1 Core product capabilities

### Academic management

- Manage departments, programs, academic years, semesters, sections, batches, students, faculty, courses, and course assignments.
- Manage buildings, rooms, laboratories, time slots, faculty availability, and academic calendars.
- Enforce relational integrity and role-scoped access.

### Timetable management

- Prepare generation scope and scheduling inputs.
- Generate schedules with OR-Tools.
- Inspect solver outcomes, conflicts, scores, and diagnostics.
- Review and edit drafts through the Admin interface.
- Revalidate after edits.
- Finalize and publish only through authorized lifecycle operations.
- Ensure Faculty and Student portals retrieve their permitted published schedules.

### Resource allocation

- Maintain the resource catalog.
- Submit booking requests.
- Check time-window conflicts against approved bookings and relevant published timetable occupancy.
- Approve, reject, or cancel bookings according to permissions.
- Return actual alternative resources where availability can be established.

### AI assistant

- Route natural-language queries to authorized structured tools.
- Maintain safe request-scoped context for multi-turn clarification.
- Explain retrieved data with clear boundaries between evidence and interpretation.
- Use the Scheduling Agent to prepare and execute an explicitly confirmed generation request.
- Use the Resource Agent to inspect availability and request bookings through existing services when that later stage is implemented.
- Support institutional document retrieval through optional RAG when its data source and evaluation are ready.

## 3.2 Explicit non-goals

- Do not add HOD or Coordinator roles.
- Do not replace the OR-Tools engine with LLM-generated schedules.
- Do not treat the frontend as the security boundary.
- Do not allow arbitrary LLM-generated SQL execution.
- Do not pretend synthetic data is official REVA data.
- Do not auto-publish a timetable generated conversationally.
- Do not deploy incomplete features just to demonstrate a working endpoint.

---

# 4. Current Implementation Baseline

This section is a project-status reference, not a substitute for inspecting the live repository before a change.

| Area | Last reported status | Notes / limitations |
|---|---|---|
| Git checkpoints | Implemented | Checkpoints include `f0715b0`, `c14a7dc`, `b769ee2`, and `ddfa313`; verify current `HEAD` and remote before a new stage. |
| Backend foundation | Implemented | FastAPI, shared SQLAlchemy engine/session, auth, and configuration are reported in place. |
| Academic CRUD | Implemented | Existing APIs and screens cover many core entities; each workflow should still be evaluated for real end-to-end persistence. |
| Timetable generator | Implemented | Admin UI invokes existing OR-Tools-based generation. Do not rebuild it for the Scheduling Agent. |
| Timetable lifecycle | Implemented | Draft/review/validate/finalize/publish behavior is present; actual status names must follow current code. |
| Validator/scorer | Implemented | Independent validation and computed metrics are reported as present; do not assume every target metric is already covered without inspecting code. |
| Faculty and Student portals | Implemented | Published personal schedules and role isolation are reported as present. |
| Resource Allocation Engine | Implemented | Local checkpoint `b769ee2`; CRUD, booking state transitions, overlap checking, timetable conflicts, alternatives, and Admin UI reported. |
| Supervisor + Query Agent | Foundation implemented | Local checkpoint `ddfa313`; authenticated chat endpoint, LangGraph routing, typed database tools, and assistant drawer reported. |
| Chat query integration | Basic supported queries verified by report | Room inventory query returned a grounded active-facility count; broader query coverage and live provider mode need continued testing. |
| Scheduling Agent | Planned | Must orchestrate existing timetable service, add readiness/explainability and safe conversational workflow. |
| Resource Agent | Planned | Must orchestrate the already implemented resource service, not reimplement booking rules. |
| Multi-turn durable confirmation | To verify/implement in Stage 9B | Must not rely on insecure global state or client-provided authorization.
| Notifications/change requests/audit UI | Partial / needs audit | Underlying models/audit records exist, but operational APIs/UI were previously identified as incomplete. |
| Official REVA data ingestion | Planned / blocked by missing source data | Faculty workbook alone does not provide curriculum or assignment truth. |
| RAG | Planned | Structured operational facts remain in PostgreSQL; RAG is for unstructured institutional policy documents. |
| Evaluation framework | Planned | Build labelled query set, solver metrics and baseline comparisons. |
| CI/production deployment | Deferred | Do not begin until feature completion, security checks, and staging readiness.

## 4.1 Verified checkpoint history (reported)

- `f0715b0` — backend configuration and health checks.
- `c14a7dc` — API routing and session compatibility.
- `b769ee2` — resource allocation engine and Admin workspace.
- `ddfa313` — Supervisor and grounded Query Agent.

A later `.gitignore` change was observed locally to add `REVA_School_of_CSE_Faculty.xlsx` to the ignore rules. Verify whether it has since been committed; never silently fold it into unrelated feature work.

---

# 5. Target System Architecture

## 5.1 Component diagram

```text
                         ┌──────────────────────────┐
                         │      User / Browser      │
                         │ ADMIN / FACULTY / STUDENT│
                         └────────────┬─────────────┘
                                      │ HTTPS in deployment
                                      ▼
                         ┌──────────────────────────┐
                         │ React + TypeScript UI    │
                         │ Role portals + RIO chat  │
                         └────────────┬─────────────┘
                                      │ Axios / API client
                                      ▼
                         ┌──────────────────────────┐
                         │ FastAPI API boundary     │
                         │ Auth · RBAC · validation │
                         └─────┬───────────┬────────┘
                               │           │
                    CRUD / UI  │           │ Natural-language request
                               ▼           ▼
                      ┌────────────┐  ┌────────────────────┐
                      │ Domain     │  │ LangGraph          │
                      │ services   │  │ Supervisor         │
                      └─────┬──────┘  └─────────┬──────────┘
                            │                   │
               ┌────────────┼───────────┐       ├───────────────┐
               │            │           │       │               │
               ▼            ▼           ▼       ▼               ▼
        ┌────────────┐ ┌────────────┐ ┌──────┐ ┌────────────┐ ┌────────────┐
        │ Timetable  │ │ Resource   │ │Other │ │ Query      │ │ Scheduling │
        │ service    │ │ service    │ │tools │ │ Agent      │ │ Agent      │
        └─────┬──────┘ └─────┬──────┘ └──────┘ └──────┬─────┘ └──────┬─────┘
              │              │                        │              │
              ▼              ▼                        └──────┬───────┘
        ┌────────────┐ ┌────────────┐                        │
        │ OR-Tools   │ │ Booking    │                ┌───────▼────────┐
        │ CP-SAT     │ │ conflict   │                │ Typed tools /  │
        └─────┬──────┘ └─────┬──────┘                │ policy checks  │
              │              │                       └───────┬────────┘
              ▼              ▼                               │
        ┌─────────────────────────────────────────────────────▼────────┐
        │ PostgreSQL / SQLAlchemy — operational source of truth        │
        │ academic data · timetables · bookings · notifications · audit │
        └──────────────────────────────┬────────────────────────────────┘
                                       │
                             ┌─────────▼──────────┐
                             │ Independent        │
                             │ validator + scorer │
                             └────────────────────┘
```

The diagram shows the target design. Components marked planned in Section 4 must not be assumed to exist just because they appear here.

## 5.2 Request paths

**Direct application operation**

```text
Browser → FastAPI authentication/authorization → schema validation
→ domain service → SQLAlchemy transaction → PostgreSQL → response
```

**Informational chat request**

```text
Browser → authenticated chat endpoint → Supervisor
→ Query Agent → authorized typed tool → PostgreSQL
→ evidence-grounded answer → browser
```

**Conversational timetable generation (target)**

```text
Admin request → Supervisor → Scheduling Agent
→ scope resolution → readiness analysis → proposal
→ explicit confirmation → existing timetable service
→ OR-Tools → independent validator → scorer
→ persisted draft/version → actual result and diagnostics
```

**Conversational resource request (target)**

```text
User request → Supervisor → Resource Agent
→ resource/scope resolution → availability check
→ alternatives if needed → explicit booking request
→ existing resource service → conflict-safe persistence
→ approval workflow → response
```

## 5.3 Boundary rules

- The API layer authenticates and enforces access to endpoints.
- Domain services own business rules and mutation transactions.
- Agent tools expose narrow typed operations, not unrestricted database access.
- The Supervisor selects a route but is not a substitute for authorization.
- Specialist agents interpret requests and orchestrate tools but do not bypass domain services.
- PostgreSQL and persisted service results determine what happened.
- A response synthesizer explains results; it cannot convert failure into success.

---

# 6. Technology Stack and Architectural Decisions

## 6.1 Existing stack

| Layer | Technology / convention | Use |
|---|---|---|
| Frontend | React, TypeScript, Vite, React Router | Role-based UI and chat drawer |
| Styling/UI | Existing project design system and components | Consistent Admin, Faculty, Student experience |
| Frontend data | Axios API client and existing query/cache patterns | Authenticated service calls and invalidation |
| Backend | Python, FastAPI, Pydantic | APIs, schema validation, request handling |
| ORM/database | SQLAlchemy and PostgreSQL | Persisted academic and operational data |
| Migrations | Alembic | Version-controlled schema evolution |
| Auth | JWT access token and HTTP-only refresh-cookie flow | Authenticated session and roles |
| Agent framework | LangGraph | Supervisor graph and controlled routing |
| LLM provider | Anthropic Claude API per project specification, with local/offline fallback for supported patterns | Language understanding/tool selection/response synthesis |
| Scheduling | Google OR-Tools CP-SAT | Timetable constraint solving and optimization |
| Tests | pytest and existing frontend build/lint scripts | Regression, isolation, API, agent and UI quality checks |
| Version control | Git / private GitHub remote | Local checkpoints and remote backup |

Before changing dependencies, inspect versions installed in the project virtual environment and declared in `requirements.txt`. Avoid introducing a second database/session/auth stack or redundant agent framework.

## 6.2 Planned infrastructure, not assumed current

Celery/Redis background jobs, Docker Compose, GitHub Actions CI, structured tracing, and cloud deployment appear in the broader target plan. Treat them as planned or requiring verification until repository configuration and a working execution path prove they are implemented.

Long-running solver jobs should eventually be moved to a durable job mechanism if measured workload and deployment architecture justify it. Do not add infrastructure simply because it appears in a blueprint; specify the operational need, migration path, tests, and local developer workflow first.

---

# 7. Repository Organization

The current repository may differ from this conceptual layout. Extend actual modules instead of generating a second parallel project tree.

```text
RIO-MJP/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py                 # compatibility/re-export only if current architecture uses it
│   ├── dependencies.py             # authenticated identity and role dependencies
│   ├── models/                     # SQLAlchemy domain models
│   ├── schemas/                    # Pydantic request/response schemas
│   ├── routes/                     # FastAPI route modules
│   ├── services/                   # transactional domain/application logic
│   └── optimizer/                  # existing timetable solver, validator and scorer
├── agents/
│   ├── state/                      # typed request-scoped graph state/contracts
│   ├── supervisor/                 # intent routing and policy pre-checks
│   ├── query_agent/                # grounded informational query workflows
│   ├── scheduling_agent/           # planned conversational scheduling orchestration
│   ├── resource_agent/             # planned conversational resource orchestration
│   └── tools/                      # narrow typed, authorized tool adapters
├── frontend/
│   ├── src/
│   │   ├── api/                    # existing HTTP client and domain APIs
│   │   ├── auth/                   # session context and protected navigation
│   │   ├── components/
│   │   ├── layouts/
│   │   ├── pages/admin/
│   │   ├── pages/faculty/
│   │   ├── pages/student/
│   │   └── routes/
│   └── package.json
├── tests/
│   ├── api/
│   ├── agents/
│   ├── optimizer/
│   ├── database/
│   └── integration/
├── data/
│   └── sample/                     # controlled synthetic datasets for testing
├── scripts/                        # intentionally invoked, audited maintenance scripts
├── PROJECT_SPECIFICATION.md        # authoritative architecture/requirements once updated
├── requirements.txt
└── README.md
```

**Source-of-truth rule:** Repository files, current schemas, and passing reproducible tests take precedence over stale examples in old documentation. When code and this blueprint disagree, first identify whether the code is intentionally ahead of the document, then update the document or propose a justified code change; do not silently duplicate architecture.

---

# 8. Domain Model and Data Ownership

PostgreSQL is the operational source of truth. The entities below describe logical domains; exact class names, fields, types, and foreign keys must match actual SQLAlchemy models and Alembic migrations.

## 8.1 Identity and access

- `users`: authenticated account, role, active status, and identity metadata.
- Student/faculty domain profiles map users to student/faculty records.
- Department ownership and role scope are enforced in the backend, not inferred from UI navigation.

Never pass password hashes, access tokens, refresh tokens, secret configuration, or unrelated personal attributes to an LLM.

## 8.2 Academic structure

- Departments.
- Programs.
- Academic years and semesters.
- Sections and batches.
- Students and faculty.
- Courses and course assignments.
- Elective groups and related courses when represented in the schema.
- Faculty availability and workload requirements.
- Academic calendar and institutional time slots.

The relationship among course, assigned faculty, section/batch, class type, and weekly instructional requirements is essential for trustworthy timetable generation.

## 8.3 Campus space and timetable data

- Buildings.
- Rooms and laboratories.
- Room capacities, types, equipment, and active status.
- Time slots.
- Timetable versions.
- Timetable entries linking academic scope, course, faculty, room, and slot.

Published timetables are the authoritative operational schedule visible to students/faculty. Draft timetable versions must not leak into their personal views.

## 8.4 Resource and workflow data

- Resources and resource bookings.
- Change requests.
- Notifications.
- Audit logs.
- Any proposal/idempotency records introduced in the future only if needed and approved by architecture review.

Do not duplicate booking state into agent memory and treat it as authoritative. Agents must query the service or database for current status.

## 8.5 Conceptual relationship map

```text
Department ── Programs ── Sections ── Batches ── Students
     │              │          │         │
     ├── Faculty ───┘          └── Course assignments ── Courses
     │       └── Faculty availability
     └── Courses / academic ownership

Building ── Rooms ── Labs / facility capabilities
Time slots + Academic calendar + Availability
                      │
Timetable version ── Timetable entries
                      │
Resource ── Resource bookings
Users ── Change requests / Notifications / Audit logs
```

## 8.6 Schema governance

- Do not claim all conceptual tables are complete without checking migrations and models.
- Do not add a migration merely to match a sample DDL in an old blueprint.
- New schema is justified only when an actual feature requirement cannot be represented safely by the current models.
- Every schema change must include migration review, downgrade/rollback consideration, isolated integration tests, and a plan for when/how it is applied.
- Never use application tests that reset or drop the development database.

---

# 9. Authentication, Authorization, and Privacy

## 9.1 Session flow

The current implementation is reported to use:

1. `POST /auth/login` verifies credentials.
2. The backend returns a short-lived access token and sets an HTTP-only refresh cookie.
3. The frontend keeps the access token in memory and sends it as a bearer token.
4. Session restoration/refresh uses the HTTP-only cookie.
5. Logout clears the client session and invalidates/clears refresh state according to the current implementation.

Verify actual cookie and token behavior in code. Production secure-cookie settings depend on deployed origin/topology and must be handled during the final deployment phase.

## 9.2 Role model

| Capability | STUDENT | FACULTY | ADMIN |
|---|---|---|---|
| View own published timetable | Yes | Yes | Yes |
| View other students' private timetable | No | No | Only if explicitly justified by an authorized administrative workflow |
| View own faculty schedule | No | Yes | Yes |
| View department timetable | No by default; only permitted public/academic data | Own department, subject to API policy | Authorized departments |
| Manage academic master data | No | No | Yes |
| Generate timetable | No | No | Yes |
| Review/edit/validate/finalize/publish | No | No | Yes |
| Request resource booking | As permitted by policy | As permitted by policy | Yes |
| Approve/reject resource booking | No | No | Yes |
| Access audit viewer | No | No | Yes, subject to current API scope |
| Invoke Query Agent | Permitted tools only | Permitted tools only | Permitted administrative tools |
| Invoke Scheduling Agent | No | No | Yes |
| Invoke Resource Agent | Non-mutating availability/request paths only as policy allows | Non-mutating availability/request paths only as policy allows | Authorized resource operations |

All permissions must match the implemented policy and project requirements. The table sets the intended policy, not proof that each endpoint currently enforces it.

## 9.3 Three-layer agent safety

1. **API layer:** authenticates user and enforces endpoint role/department rules.
2. **Supervisor layer:** checks that the requested intent is appropriate for the caller before dispatch.
3. **Tool/service layer:** independently revalidates user scope and allowed operation before returning private data or mutating state.

Supervisor checks improve defense in depth but never replace tool-level authorization.

## 9.4 Privacy rules

- Derive user ID, role, and department scope from the authenticated backend identity.
- Never trust user IDs/roles supplied by the LLM or frontend for authorization.
- Keep results to minimum necessary fields.
- Mask private contact data when not needed or not authorized.
- Prevent prompt injection or retrieved text from granting authority or changing tool policy.
- Do not expose internal stack traces, credentials, database values, or private records through chat errors.

---

# 10. API and Service Boundaries

Use current API contracts as the source of truth. The following is a logical responsibility map, not a promise that every endpoint currently exists.

## 10.1 Authentication

- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`

## 10.2 Academic and campus management

Existing route modules cover many of the following domains:

- Departments, programs, academic years, semesters, sections, batches.
- Faculty, students, courses, course assignments.
- Buildings, rooms, labs, time slots, faculty availability, academic calendar.
- Resource inventory and bookings.

Verify each implemented method/route and permission before advertising it in the frontend or AI tools.

## 10.3 Timetable management

The current implementation includes a timetable generation route and separate version lifecycle endpoints. The exact route names/status transitions must be taken from `backend/routes/timetable.py`, schemas, and tests. The intended lifecycle includes generation, review, validation, finalization, and publication as separate auditable actions.

Do not rename or duplicate current routes purely to match a generic specification example.

## 10.4 Resource management

The Stage 7 engine provides resource inventory and booking operations, including request state changes and availability/conflict checking. The Resource Agent should call the existing service or typed tool adapters. It must not implement a second booking engine.

## 10.5 Chat

The reported chat interface calls `POST /agents/chat`; `/chat` is also reported as a compatibility endpoint. Verify route registration and proxy behavior before changing either path.

## 10.6 Service-layer ownership

Use service functions as the shared execution boundary whenever both a direct API and AI agent need to perform the same operation. Avoid internal self-HTTP calls and avoid duplicating transactions, authorization, conflict logic, or lifecycle transitions.

---

# 11. Multi-Agent Architecture

The target multi-agent system contains four specialist/core components coordinated by a single Supervisor. Not all four are implemented yet.

## 11.1 Agent topology

```text
                         Authenticated Request
                                  │
                                  ▼
                          ┌──────────────┐
                          │  Supervisor  │
                          │ route + RBAC │
                          └──────┬───────┘
                                 │
               ┌─────────────────┼──────────────────┐
               │                 │                  │
               ▼                 ▼                  ▼
        ┌────────────┐    ┌──────────────┐    ┌────────────┐
        │ Query      │    │ Scheduling   │    │ Resource   │
        │ Agent      │    │ Agent        │    │ Agent      │
        └─────┬──────┘    └──────┬───────┘    └─────┬──────┘
              │                  │                  │
       Read-only tools      Existing timetable   Existing resource
       + optional RAG       service + OR-Tools   booking service
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 ▼
                       ┌────────────────────┐
                       │ Response assembly  │
                       │ from actual results│
                       └────────────────────┘
```

The Supervisor should route to one specialist for normal tasks. Cross-agent coordination may be added for a genuinely multi-domain task, but only after the individual tools have stable contracts, permissions, budgets, and traceable outputs.

## 11.2 Responsibilities

| Component | Responsibility | State-changing authority |
|---|---|---|
| Supervisor | Intent routing, permission pre-check, specialist dispatch, bounded response coordination | None by itself |
| Query Agent | Read-only information retrieval and explanation | None |
| Scheduling Agent | Resolve scope, readiness analysis, propose/confirm timetable generation, analyze real solver output | May invoke existing generation service only after server-validated Admin confirmation |
| Resource Agent | Resolve resource requests, check availability, present alternatives, initiate allowed booking workflow | May request a booking through existing service under policy; only Admin can approve/reject |
| Tools/services | Typed access to data and domain operations | Only the specific operation allowed by backend policy |

## 11.3 Intelligence versus deterministic execution

The LLM may:
- Interpret natural language.
- Classify likely intent.
- Extract proposed typed parameters.
- Select among explicitly allowed tools.
- Ask clarifying questions.
- Summarize real tool/service outputs.

The LLM may not:
- Authenticate itself or choose its own user role.
- Grant permissions or bypass policy.
- Execute arbitrary SQL.
- Invent campus facts, IDs, availability, solver scores, or status transitions.
- Create timetable slots or booking persistence independently of existing services.
- Claim an operation succeeded without a verified service result.

---

# 12. Supervisor Agent

The Supervisor is the controlled entry point for conversational tasks.

## 12.1 Intent taxonomy

The target taxonomy includes:

- `STUDENT_QUERY` → Query Agent.
- `FACULTY_QUERY` → Query Agent.
- `DEPARTMENT_QUERY` → Query Agent, subject to department scope.
- `CLASS_STATUS_QUERY` → Query Agent, using published timetable and deterministic time logic.
- `ROOM_OR_COURSE_QUERY` → Query Agent.
- `TIMETABLE_GENERATION` → Scheduling Agent; Admin only.
- `TIMETABLE_DIAGNOSIS` → Scheduling Agent or read-only diagnostic tool; permission and data scope required.
- `TIMETABLE_SCENARIO_COMPARISON` → Scheduling Agent when genuine scenario evaluation is supported.
- `RESOURCE_AVAILABILITY` → Resource Agent when integrated; authorized read path.
- `RESOURCE_BOOKING` → Resource Agent when integrated; policy-controlled mutation.
- `UNKNOWN` → clarification or bounded unsupported response, with no unsafe tool call.

Intent labels are proposals, not authorization. A text classifier or LLM output does not determine access.

## 12.2 Routing policy

- Validate request length and message structure.
- Use the authenticated request context, not client-supplied identity claims.
- Route only to registered, implemented agents.
- Reject unsupported actions explicitly.
- Bound retries, tool calls, recursion, token/context size, and total execution time.
- Handle malformed provider outputs, unavailable model API, and tool exceptions safely.
- Preserve query handling while the Scheduling and Resource Agents are introduced.

## 12.3 Future multi-agent coordination

Cross-agent workflows (for example, a schedule change affecting a room booking) should be implemented only with an explicit plan, defined state transitions, bounded steps, compensating/rollback strategy where applicable, and tests for partial failure. Avoid agent-to-agent free-form loops.

---

# 13. Query Agent

## 13.1 Current baseline

The Query Agent foundation and chat interface are reported as implemented in checkpoint `ddfa313`. Current tools include student timetable, faculty schedule/profile, department timetable, course information, room/lab details, academic calendar, class status, and active-room inventory count. The exact current tool list must be verified in `agents/tools/`.

The reported classroom-inventory test answered with database-derived counts: 7 classrooms, 2 seminar halls, 1 lab, and 10 active rooms in the dataset used at that time. Those values are dataset-specific, not permanent institutional constants.

## 13.2 Query execution protocol

1. Validate the user request and authenticated scope.
2. Classify the query to an explicit supported category.
3. Select a typed tool or ask for clarification.
4. Execute a bounded parameterized SQLAlchemy query through the existing session.
5. Filter fields and rows according to role/privacy policy before model context.
6. Generate a response grounded in retrieved outputs.
7. Attach source/result metadata when supported.
8. If the answer cannot be established, say what is missing rather than inventing information.

## 13.3 Query requirements

- No arbitrary LLM-generated SQL.
- No direct access to another student's timetable.
- Student personal schedules are scoped to authenticated student profile/section/batch and published versions only.
- Faculty schedule is scoped to the authenticated faculty profile; department-level access follows role policy.
- Faculty phone/contact details are returned only when authorized and necessary.
- Inventory count must not be presented as current-time availability.
- Current class status is computed from persisted published schedule, status, and current time—not guessed by the LLM.
- Tool outputs have result limits and safe error contracts.

## 13.4 Query quality improvements

Future improvements should include:
- More robust intent and entity extraction for varied phrasing.
- Multi-turn reference resolution (e.g. "what about tomorrow?") with safe session-scoped context.
- Query result ranking and ambiguity handling.
- Source labels and traceable tool execution.
- A labelled evaluation set for intent accuracy, tool accuracy, grounded resolution rate, latency, and refusal correctness.

---

# 14. Scheduling Agent

## 14.1 Purpose

The Scheduling Agent adds intelligent orchestration around the existing timetable engine. It does not replace timetable generation from the Admin UI and must reuse the existing solver/service.

It adds:
- Natural-language scope resolution.
- Readiness checks on academic inputs.
- Clarification for missing or ambiguous scope.
- Proposal and explicit Admin confirmation.
- Optimization-strategy selection where the solver supports it.
- Result explanation based on real solver/validator/scorer output.
- Infeasibility investigation using evidence-backed diagnostics.
- Candidate comparison/what-if analysis where the application can run genuinely independent evaluations.

## 14.2 Proposed interaction

```text
Admin: "Generate a timetable for CSE Semester 5."
  → Supervisor recognizes TIMETABLE_GENERATION
  → role check: ADMIN only
  → Scheduling Agent resolves real department/program/semester/sections
  → missing/ambiguous scope? ask a focused question
  → readiness check against actual required data
  → readiness blocked? explain blockers and stop
  → otherwise show proposal, strategy, warnings, and expected effect
  → wait for explicit confirmation tied to that proposal
  → revalidate identity, scope, proposal freshness and prerequisites
  → invoke the existing generation service once
  → OR-Tools solves; independent validator and scorer run
  → persist draft/version through the existing service
  → return actual status, version reference, metrics, and review link
```

## 14.3 Readiness analysis

Readiness should inspect the actual input loader's requirements. Depending on the real schema, these may include:

- Required sections/batches and enrollment counts.
- Course assignment, faculty eligibility, and weekly class-hour requirements.
- Time slots and available instructional periods.
- Active eligible rooms/labs and capacity.
- Faculty unavailability/preferences.
- Calendar restrictions.
- Elective group rules.

Use `READY`, `READY_WITH_WARNINGS`, and `BLOCKED` only when their semantics are explicitly defined in code/contracts. A readiness check is not proof of solver feasibility.

## 14.4 Optimization intelligence

Where the solver and scorer genuinely support it, compare legitimate objective profiles such as balanced schedule, faculty comfort, room utilization, or lab timing. Do not advertise a strategy that has no corresponding solver objective or tested parameterization.

Candidate comparisons must use actual solver runs and consistently calculated metrics. Candidate schedules should remain temporary/unpersisted until selection, unless the existing service has a safe candidate lifecycle. Hard constraints stay fixed across all scenarios.

## 14.5 Infeasibility explanation

Distinguish:
- Missing/inconsistent input data.
- Preflight indicators of insufficient capacity/availability.
- Solver `INFEASIBLE`.
- Solver timeout/`UNKNOWN`.
- Independent validator failure.

Only provide cause-level explanation that can be substantiated by actual diagnostics. A generic solver status does not prove which input caused failure.

## 14.6 Confirmation and execution security

- Admin-only at API/service/tool layers.
- Proposal must refer to resolved scope, generation parameters, and a specific action.
- Revalidate data freshness/readiness on confirmation.
- Prevent replay and duplicate submissions using a suitable server-side mechanism.
- Do not rely on global in-memory flags for cross-worker durable guarantees.
- Do not automatically validate/finalize/publish as part of the chat generation action.
- Treat persisted generation results as the only evidence of success.

## 14.7 Current state

Conversational Scheduling Agent work is planned after Stage 9A. The existing Admin timetable UI and OR-Tools engine are already reported implemented; this stage should be a thin but sophisticated integration plus readiness/explainability, not a second generator.

---

# 15. Resource Agent

## 15.1 Purpose

The Resource Agent is a conversational orchestration layer over the already implemented Resource Allocation Engine.

The booking service, not the LLM, remains authoritative for availability, conflicts, permissions, status transitions, concurrency, and audit records.

## 15.2 Planned capabilities

- Parse natural-language resource type, purpose, date/time interval, capacity, and location needs.
- Ask for missing date/time, resource category, or capacity information.
- Resolve resources against the real resource catalog.
- Call the existing availability endpoint/service.
- Explain confirmed conflicts and propose compatible alternatives.
- Create a booking request through the existing booking service after appropriate user confirmation.
- Explain the resulting `PENDING` status and authorized approval workflow.
- Retrieve booking status from PostgreSQL for follow-up queries.

## 15.3 Safety and policy

- Use authenticated requester identity.
- Never trust an LLM-supplied `requested_by`, `approved_by`, or role.
- Only Admin may approve/reject bookings, as enforced by the existing service.
- Recheck availability at the mutation/approval boundary.
- Protect against overlapping concurrent bookings and duplicate requests.
- Do not promise a booking until the service confirms the persisted result.
- Treat inventory count and free availability as different questions.
- Use time-interval overlap semantics rather than relying only on matching time-slot identifiers.

## 15.4 Current state

The resource engine was reported completed in checkpoint `b769ee2`. The conversational Resource Agent remains planned; it must reuse current APIs/services rather than duplicate the booking engine.

---

# 16. Tool Contracts, Shared State, and Conversation Continuity

## 16.1 Request-scoped state

The existing `AgentState` foundation includes identity/scope, user message, intent, selected agent, tool calls/results, and final response. Inspect the actual definition before extending it.

A future state contract may include:

- Authenticated user ID, role, and resolved department scope.
- Current turn message and validated conversation context.
- Selected intent/agent.
- Typed tool arguments/results and source metadata.
- Clarification/proposal state.
- Safe error class and final response.
- Correlation/request identifier.

Never put secret material, full credentials, or raw refresh cookies into graph state.

## 16.2 Typed tool contract

Every tool must define:

- Stable name and purpose.
- Input schema with bounded values.
- Output schema or typed result.
- Allowed roles/scope.
- Read/write classification.
- Timeout/result-size limits.
- Error behavior.
- Audit/idempotency expectations for mutations.

The authorization dispatcher must enforce policy independently of the LLM's tool selection.

## 16.3 Multi-turn state and confirmation

Conversation history can help resolve language such as "that semester" or "the second option," but client-submitted history is not proof of authorization or confirmation.

For consequential operations, use a server-validated proposal or action identifier bound to the authenticated user, resolved scope, chosen parameters, expiry/freshness, and operation type. The backend must revalidate the proposal before execution.

Do not store pending action state in a process-global mutable variable. Choose ephemeral session state or durable persistence based on explicit reliability requirements and current architecture.

## 16.4 Tool traces

For development/demo observability, expose safe traces such as selected agent, tool name, duration, success/failure, and redacted source identifiers. Never expose secrets, raw private tool payloads, hidden system prompts, or unauthorized records in the UI.

---

# 17. Timetable Optimization Engine

## 17.1 Role of OR-Tools

Google OR-Tools CP-SAT is the authoritative scheduling engine. The Scheduling Agent can parameterize requests and inspect outcomes but cannot directly construct assignments as an LLM-generated answer.

## 17.2 Decision model

The exact variable representation must follow the existing implementation. Conceptually, a decision variable represents assigning a course/session to an eligible faculty member, section/batch, room, and time slot.

Candidate assignments must be filtered by the actual models and requirements, including eligibility, capacity, room/lab type, availability, and allowed slots.

## 17.3 Hard constraints

The existing solver's constraints must be inspected and preserved. The blueprint's required invariants include:

1. No faculty member teaches overlapping sessions.
2. No room hosts overlapping sessions.
3. No student section/batch attends overlapping sessions.
4. Room capacity is sufficient for the relevant class size.
5. Faculty unavailability is respected.
6. Lab/course room-type restrictions are respected.
7. Weekly course requirements are satisfied.
8. Relevant academic-calendar exclusions are respected.
9. Elective-group non-overlap rules are respected where applicable.

Additional existing constraints must not be dropped. A missing constraint should be handled as an explicit engineering defect, not silently assumed covered.

## 17.4 Soft objective

The current implementation and specification should be inspected to establish which soft objectives truly exist. Candidate objectives from the project plan include:

- Reduce undesirable faculty gaps/consecutive-load patterns.
- Reduce student idle gaps.
- Prefer requested slots where allowed.
- Reduce unnecessary room changes.
- Prefer appropriate lab timing.
- Balance faculty workload.
- Improve room utilization without violating hard constraints.

Weights and scores must come from actual solver configuration and scorer code, not hard-coded UI claims. Changes to objective weights must be tested and evaluated empirically.

## 17.5 Solver outcomes

Preserve the distinction between solver outcomes such as optimal, feasible, infeasible, timeout/unknown, and execution error, using the current library/API semantics.

- `OPTIMAL`/`FEASIBLE` results still require the independent validator.
- An infeasible result must not produce a fabricated timetable.
- A timeout must not be presented as proof of infeasibility.
- Solver logs should be bounded and avoid private input dumps.
- Record the configured time limit and worker count as actual settings rather than assuming example values.

## 17.6 Long-running execution

The existing implementation was previously reported as running generation synchronously with a solver time limit. The long-term plan considers a durable background-job mechanism for large datasets.

Before adopting Celery/Redis or another job system:
- Measure generation latency and request-worker contention.
- Specify idempotency and job ownership.
- Define queued/running/succeeded/failed/cancelled states.
- Persist progress/result metadata safely.
- Provide authenticated status polling.
- Keep current direct generation workflow working during migration.
- Add local development services and integration tests.

Do not claim that background execution exists until a functioning worker/task/result path is verified.

---

# 18. Independent Validator and Scorer

## 18.1 Independent validator

The validator must re-check a candidate using deterministic Python logic independent of the solver model construction. This protects against modeling mistakes and post-generation manual edits.

Required checks, based on actual schema support, include:

- Faculty overlaps.
- Room overlaps.
- Section/batch overlaps.
- Room capacity.
- Faculty availability.
- Room/lab suitability.
- Required course-session counts/hours.
- Elective conflicts.
- Applicable calendar restrictions.

Validation output must identify violation type, severity, affected entities, and relevant interval/slot identifiers with enough context for the authorized admin to resolve the issue. Avoid exposing other users' private data.

Any hard violation blocks a version from advancing into a valid/publishable state. A validator failure should fail closed.

## 18.2 Scorer

The scorer computes metrics from actual schedule and validator data. Target metrics include:

- Total/composite score using documented weights.
- Hard-constraint violation count.
- Soft-constraint violation count.
- Room utilization.
- Faculty workload balance.
- Average student gap minutes.
- Relevant elective conflict count.
- Generation elapsed time and solver status.

Do not hard-code score values or claim two scenarios are comparable if they use different metric definitions.

## 18.3 Revalidation

Manual timetable edits must trigger the established validation workflow. Finalization/publication must re-check the permitted version state and validation result. A previously valid score cannot be reused after material schedule changes unless recomputed.

---

# 19. Resource Allocation Engine

## 19.1 Existing engine

The Stage 7 implementation report describes resource CRUD, booking requests, approval/rejection/cancellation, availability inspection, alternative suggestions, published timetable conflict checking, requester privacy masking, and audit logging.

The Resource Agent must reuse this engine. Keep all booking rules in domain services and route/service authorization, not in prompt instructions alone.

## 19.2 Time overlap

For half-open intervals `[start, end)`, two intervals overlap exactly when:

```text
existing_start < requested_end
AND requested_start < existing_end
```

Adjacent reservations can be permitted when the system's operational rules allow it. End time must be later than start time.

## 19.3 Conflicts

Check conflicts against:

- Approved bookings for the same resource.
- Published timetable occupancy for relevant room-backed resources.
- Any other current restriction the actual model/specification establishes.

Pending requests are not confirmed reservations by default; approval must recheck current availability. Resource-level lock strategy and its concurrency tests should be maintained and reviewed as the booking service evolves.

## 19.4 Alternatives

Alternative resources must:

- Be active and compatible with resource type and capacity.
- Be available for the requested time interval.
- Satisfy relevant location/equipment constraints where provided.
- Be ranked using a documented criterion.
- Be described as alternatives, not a booking confirmation.

## 19.5 Audit and approval

Approval/rejection/cancellation transitions must enforce valid prior status, authorized actor, and consistent audit writes. Duplicate transitions and concurrent requests must be safe. The only role that can approve/reject resource bookings is `ADMIN` under the intended policy.

---

# 20. Workflow State Machines and Human Oversight

## 20.1 Timetable lifecycle

Follow actual current status names and transition code. The intended semantic stages are:

```text
Generated draft → Admin review/edit → Validation → Finalization → Publication
       │                 │                │               │
       └──── failure/rejection with reason and controlled regeneration ────┘

Old published version → Archived when a replacement is published
```

The existing implementation has been reported to use distinct states similar to `GENERATED`, `REVIEWED`, `VALIDATED`, `FINALIZED`, and `PUBLISHED`, with additional draft/rejected/archive states. The actual enum and allowed transitions are authoritative.

- The agent can request generation only after authorized confirmation.
- A new timetable version remains a draft/review artifact.
- Edits require revalidation.
- Finalization locks or restricts further edits as defined by current lifecycle policy.
- Publication is a distinct authorized Admin action.
- Published replacement/archive behavior must preserve history.

## 20.2 Conversational scheduling states (target)

```text
REQUEST_RECEIVED
  → SCOPE_RESOLUTION
  → READINESS_CHECK
  → PROPOSAL_READY
  → AWAITING_ADMIN_CONFIRMATION
  → GENERATION_RUNNING
  → DRAFT_GENERATED | BLOCKED | INFEASIBLE | TIMED_OUT | FAILED
```

Clarification and failure paths are first-class outcomes. A proposal must be tied to its scope and operation, expire or be invalidated when stale, and be revalidated on confirmation.

## 20.3 Resource booking states

The reported resource service uses states along the lines of:

```text
PENDING → APPROVED
        → REJECTED
PENDING/APPROVED → CANCELLED where policy permits
```

Use actual enum/status values and reject invalid transitions.

## 20.4 Change-request lifecycle (future completion)

Target:

```text
Submitted → Pending Admin review → Approved / Rejected
    → (if approved and timetable changes) controlled re-optimization
    → validation → Admin finalization/publication → affected users notified
```

There are no HOD/Coordinator review stages. Do not introduce them.

---

# 21. Notifications, Audit, and Operational Workflows

## 21.1 Audit logs

Audit records should identify actor, action, entity type/ID, timestamp, and relevant old/new values when safe. Never store passwords, access tokens, refresh cookies, or full secrets in audit data.

For a mutation that requires auditability, write the audit record in the same transaction as the mutation whenever supported by the transaction model. A failed mutation must not leave a false success audit record.

Events to cover include:

- Resource create/update/deactivate and booking status transitions.
- Timetable generation, edits, validation, finalization, publication, rejection/archive.
- Academic master-data changes.
- Faculty availability changes.
- Change-request review decisions.

## 21.2 Notifications

Target internal notifications include timetable publication/update, resource booking decisions, change-request decisions, and relevant scheduling changes. External email/SMS/push delivery is optional future infrastructure and must not be represented as implemented until it has working provider integration, retry policy, and tests.

## 21.3 Operational UI gaps

Previously reported placeholder routes include resource/booking UI (since implemented in Stage 7), change requests, notifications, and audit viewers. Re-audit these pages and backing APIs before considering the operational workflow complete.

## 21.4 Change requests

Implement as a separate stage after the primary agents are stable. Use the existing `ADMIN` review authority, request reasons, status transitions, audit trail, and explicit re-optimization path where needed. Do not mutate a published timetable in place without a versioned lifecycle.

---

# 22. Frontend and User Experience

## 22.1 Shared product shell

Preserve the existing RIO-MJP design system and role-specific portal layouts. New capabilities should fit existing patterns rather than trigger broad redesigns.

## 22.2 Student portal

Target capabilities:

- Student dashboard and permitted academic summary.
- Own published timetable.
- Class status derived from actual published timetable and current time.
- Permitted room/course information.
- Notifications/announcements when implemented.
- Campus Assistant.

A student must never see an unpublished draft through their personal timetable API, chat tool, or frontend state.

## 22.3 Faculty portal

Target capabilities:

- Faculty dashboard and personal schedule.
- Permitted department timetable view.
- Availability submission where the current API supports it.
- Resource requests and change requests when their workflows are implemented.
- Notifications when implemented.
- Campus Assistant.

## 22.4 Admin portal

Target capabilities:

- Academic master data.
- Faculty/course assignments and campus infrastructure.
- Resource inventory and booking approval.
- Timetable generation, review, edit, validate, finalize, publish, and version history.
- Change requests, notifications, audit logs, and system settings as their modules are completed.
- Campus Assistant with clear confirmation UI for consequential actions.

## 22.5 Assistant UX

The assistant must render structured clarification, evidence sources, operation proposals, confirmation states, and real results. At minimum, distinguish:

- Thinking/processing.
- Clarification required.
- Tool/data unavailable.
- Proposal ready.
- Awaiting confirmation.
- Action executing.
- Action succeeded with persisted reference.
- Blocked, infeasible, timed out, or failed.

Do not show invented data, simulated progress that implies actual work, or success merely because a message was generated.

## 22.6 Accessibility and resilience

- Keyboard navigation and clear focus state.
- Accessible labels/announcements for dialogs and loading/error states.
- Responsive layout.
- Empty/loading/error/permission-denied states for data screens.
- Explicit confirmation for consequential destructive or generation actions.
- Double-submit prevention complemented by backend idempotency/concurrency controls.

---

# 23. Academic Data Readiness and Ingestion

## 23.1 Official scheduling prerequisites

A trustworthy real-campus timetable requires institutional source data for:

- Academic years, semesters, programs, sections, and batches.
- Courses and official course codes/types/credits.
- Required weekly theory/tutorial/practical hours.
- Faculty-course-section/batch assignment matrix.
- Faculty availability and workload constraints.
- Real buildings, room types, room capacity, and lab/equipment details.
- Actual institutional time slots, breaks, and academic calendar exclusions.
- Elective group definitions and relevant student enrollment/counts.

The faculty directory workbook alone is insufficient to construct those relationships.

## 23.2 Workbook handling

`REVA_School_of_CSE_Faculty.xlsx` is a protected local asset and must remain untracked unless the owner explicitly chooses an appropriate controlled data-sharing procedure. It must not be modified during normal feature development.

If a future import pipeline is implemented:

1. Define the accepted workbook schema and version.
2. Validate rows and required identifiers in a preview-only mode.
3. Detect duplicates, missing attributes, unmatched faculty, and ambiguous names.
4. Require a user-reviewed mapping to existing faculty identities.
5. Do not infer course assignments from interests/specialization.
6. Produce an import report and explicit confirmation before writing data.
7. Use transactional, idempotent imports with rollback strategy.
8. Audit changes and protect personal information.
9. Test against a disposable isolated database.

## 23.3 Synthetic data versus official data

Dataset A and other controlled synthetic datasets are useful for solver/unit/integration testing. They must be labelled synthetic and must never be represented in the UI or research report as real institutional records.

Do not replace or clean production/development records just to align with sample CSVs.

## 23.4 Data readiness gates

Before a real timetable is generated, provide a readiness report that distinguishes:

- Present and valid.
- Present but inconsistent.
- Missing.
- Not verified.

Only proceed when mandatory inputs are sufficient. Readiness is not a substitute for solver feasibility or independent validation.

---

# 24. Optional Retrieval-Augmented Generation

RAG is for unstructured institutional knowledge, not operational timetable facts.

## 24.1 Appropriate sources

Examples include:

- Academic regulations.
- Examination/attendance policies.
- Student and faculty handbooks.
- Laboratory rules.
- Leave policies.
- Official campus procedures.

## 24.2 Target pipeline

```text
Approved document → extraction → chunking → metadata/ACL assignment
→ embeddings → vector store (e.g. pgvector or FAISS)
→ authorized retrieval → Query Agent synthesis with source references
```

## 24.3 Boundaries

- Timetable, booking, identity, room occupancy, and academic-record facts must come from structured PostgreSQL/tool results.
- RAG passages do not authorize mutations.
- Respect document-level access controls.
- Return source metadata where possible.
- Treat retrieved documents as untrusted content, not system instructions.
- Version document ingestion and support re-indexing/deletion according to retention policy.
- Evaluate retrieval precision/recall and grounded answer quality before enabling it for important queries.

RAG remains a future optional module unless the current code and tests demonstrate otherwise.

---

# 25. Testing and Quality Engineering

## 25.1 Test layers

```text
tests/
├── api/            # route contracts, authentication, authorization, CRUD
├── agents/         # intent, routing, tools, grounded responses, action boundaries
├── optimizer/      # solver constraints, infeasibility, score/validator
├── database/      # schema/migration/FK integrity against disposable DB
└── integration/    # end-to-end chat, generation lifecycle, resource workflows
```

Use existing repository paths and naming where they differ from this conceptual organization.

## 25.2 Database isolation

Inspect `tests/conftest.py` before running a database-backed test. The historical fixture setup has been reported to drop and recreate `test_schema`. Ensure the fixture's connection is isolated from the development schema before executing it.

Never run tests against the application's `public` development schema if the fixture can drop/truncate tables or schemas. Do not run migrations or seed scripts against real data as a shortcut for test setup.

## 25.3 Solver tests

- Verify all implemented hard constraints using controlled input fixtures.
- Include deliberately conflicting fixtures that should be infeasible.
- Verify validator independence by perturbing a generated/manual candidate and checking that the validator detects the defect.
- Verify objective/score calculations from real results.
- Check that hard violations prevent a candidate from becoming valid/publishable.
- Test deterministic/reproducible cases where the solver configuration supports them.
- Evaluate Dataset A/B/C only with controlled generators and safe isolated databases.

## 25.4 Agent tests

- Intent routing and tool selection.
- Unknown/ambiguous intent handling.
- Authentication and role/department enforcement at API and tool layers.
- Grounding: returned facts must match tool outputs.
- Empty result and data-missing behavior.
- Prompt injection/hostile retrieved content.
- Arbitrary SQL and identity override attempts.
- Bounded tool loops and provider failure behavior.
- Multi-turn state isolation and confirmation replay handling.
- No claims of successful mutation without persisted service success.

Mock external LLM calls in routine CI tests. Live provider tests should be opt-in, explicitly budgeted, and never required for normal local builds.

## 25.5 Resource tests

- Interval boundary and overlapping reservation scenarios.
- Published timetable room occupancy.
- Pending/approved/rejected/cancelled transition rules.
- Revalidation at approval time.
- Concurrent approvals for overlapping bookings on the same resource.
- Alternative-resource compatibility and real availability.
- Actor/requester permission boundaries.
- Audit record consistency with transaction outcomes.

## 25.6 Frontend checks

Run the repository's available production build, type checks, lint, and component tests. Browser test the actual critical flow when the required local services are available. A build alone does not prove that a request is routed to the correct backend endpoint or returns a useful response.

## 25.7 Change review

Every stage should report:

- Baseline branch/HEAD and working tree.
- Exact changed files and rationale.
- Commands actually executed and results.
- Tests not run and why.
- Security/data risks found.
- Remaining unverified acceptance criteria.
- Final Git state and proposed checkpoint message.

Never claim a test passed based only on an earlier report unless that distinction is explicitly stated.

---

# 26. Research Evaluation and Metrics

Evaluation must measure the actual system, not just demonstrate a few screenshots.

## 26.1 Query system metrics

- Intent classification accuracy.
- Tool selection accuracy.
- Grounded query resolution rate.
- Correct refusal/clarification rate.
- Permission-violation rate (target zero).
- Unsupported-answer/hallucination rate (target zero for database claims).
- Median/p95 end-to-end latency.
- Tool failures and provider-failure rate.

Create a labelled set of approximately 100–300 representative queries across student schedules, faculty schedules, class status, room/lab details, course information, calendar events, resource availability, and Admin queries. Balance simple questions, ambiguous phrasing, empty records, unauthorized requests, and adversarial attempts.

Report dataset source, expected answer/tool, scoring criteria, model/provider configuration, and confidence/limitations. Do not fabricate evaluation numbers.

## 26.2 Timetable metrics

- Hard-constraint violations (zero required for accepted/published versions).
- Soft-constraint violations and objective score.
- Generation runtime and solver status.
- Room utilization.
- Faculty workload balance (e.g. standard deviation where appropriate).
- Average student idle gaps.
- Elective clash count.
- Validator detections of deliberately broken candidates.
- Readiness-blocker precision and diagnostic usefulness where evaluated.

## 26.3 Resource metrics

- Conflict detection accuracy.
- False-positive/false-negative conflict rate.
- Successful booking request rate.
- Approval conflict recheck success.
- Alternative recommendation usefulness/availability correctness.
- Booking operation latency.

## 26.4 Dataset plan

The original research design proposes three scale levels:

- Dataset A: small proof-of-functionality dataset.
- Dataset B: medium-scale departmental dataset.
- Dataset C: large multi-department dataset.

The exact counts must be reconciled with the current dataset generator and actual schema. Label generated data synthetic; do not equate a sample target with existing data.

## 26.5 Baseline experiment

Compare manual/baseline scheduling with OR-Tools scheduling using repeatable scenarios. Measure time, conflicts, room utilization, faculty/student gaps, and solver runtime. Record the solver configuration, dataset version, machine/runtime environment, and scoring definitions so the experiment is reproducible.

---

# 27. Reliability, Observability, and Performance

## 27.1 Structured execution telemetry

The target observability model should correlate API requests, graph runs, tool calls, solver jobs, database transactions, and resulting timetable/resource versions using a safe request/correlation ID.

Record appropriate metadata:

- Correlation ID.
- Authenticated role (not secrets or unnecessary personal data).
- Selected agent and tool name.
- Elapsed time, result class, retries, and failure category.
- Solver status, execution duration, and diagnostic counts where appropriate.
- Persisted entity/version identifiers when safe.

Never log access/refresh tokens, passwords, full secrets, or unnecessarily complete student/faculty records. Redact user messages if they may contain private data.

## 27.2 Timeouts and budgets

Establish separate bounded timeouts for:

- LLM/provider calls.
- Individual tool/database queries.
- Entire agent graph execution.
- Timetable solver execution.
- Resource transactions.

Add bounded retries only for transient/idempotent operations. Never blindly retry a non-idempotent mutation.

## 27.3 Background scheduling jobs

The blueprint's long-term target includes background processing for solver runs that may take tens of seconds or longer. The current project was previously reported to execute synchronously. Before implementing Celery/Redis or another queue, define job state, idempotency, cancellation semantics, persistence, failure retry, result polling, local developer setup, and integration tests.

## 27.4 Operational resilience

- Provider outage must not break normal CRUD or timetable APIs.
- Query Agent should return a controlled error or use a supported deterministic fallback; it must not claim to have queried data when no tool ran.
- Database outage must fail clearly, not return stale fabricated facts.
- Agent loops must have a maximum number of steps.
- Solver timeout must be distinguished from proven infeasibility.
- Booking/timetable mutations must be transactionally consistent and safe against duplicates.

---

# 28. Security Checklist

## Authentication and access

- [ ] Passwords are stored as hashes only.
- [ ] Access tokens are short-lived and refresh behavior is verified.
- [ ] Refresh cookie attributes are correct for the actual deployment topology.
- [ ] Protected APIs enforce role/scope in backend code.
- [ ] Student data is scoped to authenticated student records/section/batch.
- [ ] Faculty data respects own-profile/department scope.
- [ ] Only Admin can generate, manage lifecycle, and publish timetables under the target policy.
- [ ] Only Admin can approve/reject resource bookings.

## Agent security

- [ ] Supervisor permission checks are backed by tool/service checks.
- [ ] Agent inputs/outputs are typed and bounded.
- [ ] No arbitrary LLM-generated SQL is executed.
- [ ] Tool results are filtered before entering model context.
- [ ] Retrieved content cannot override system/tool permissions.
- [ ] Consequential actions use explicit, server-validated confirmation.
- [ ] Proposals are protected against tampering, stale state, and duplicate/replayed actions.
- [ ] Provider errors and tool errors cannot become false success responses.
- [ ] Rate limiting and time budgets exist for chat/API requests where needed.

## Data, transactions, secrets

- [ ] No secrets are hardcoded or exposed in frontend builds.
- [ ] `.env` files and personal local assets are excluded from Git.
- [ ] Secret scanning covers all outgoing Git history before push/release.
- [ ] Mutations and required audit events are transactionally consistent.
- [ ] Resource booking conflicts are concurrency-safe.
- [ ] Migrations are reviewed and applied only to the intended database.
- [ ] Tests cannot reset or mutate the development database.
- [ ] Faculty workbook is preserved and not committed without explicit authorization.

## Release security

- [ ] Separate local, staging, and production configurations.
- [ ] Rotate any credential previously exposed in command history/logs.
- [ ] Use fresh production secrets, HTTPS, strict CORS, safe cookie settings, and appropriate logging.
- [ ] Verify dependency vulnerabilities and update strategy.
- [ ] Restrict database network access and privileges.

---

# 29. Development Roadmap

This roadmap is ordered by dependencies and the current implementation baseline. It is not a claim that every numbered step is already complete.

## Phase 0 — Repository and working-state integrity

**Status:** Ongoing maintenance.

- Maintain small local Git checkpoints.
- Keep the faculty workbook untracked and ignored where appropriate.
- Keep secrets out of commits and push only to the verified private repository.
- Test before checkpointing.
- Keep deployment deferred.

## Phase 1 — Core platform and timetable workflow

**Reported implemented:**

- Database models/migrations, auth/RBAC, CRUD APIs.
- OR-Tools generation, validator/scorer, Admin timetable workflow.
- Faculty/Student published timetable views.

**Remaining work:** Keep validating correctness and actual integrations; do not rebuild existing components without an identified defect.

## Phase 2 — Resource Allocation Engine

**Reported checkpoint:** `b769ee2`.

- Resource inventory and booking API.
- Conflict detection, timetable occupancy checks, alternate suggestions.
- Booking lifecycle, authorization, audit records.
- Admin resource workspace and regression tests.

**Future:** The conversational Resource Agent integrates over this engine.

## Phase 3 — Supervisor and Query Agent foundation

**Reported checkpoint:** `ddfa313`.

- LangGraph Supervisor.
- Query Agent with typed structured-data tools.
- Authenticated chat endpoint and assistant UI.
- Supported offline query handling and role-based tool tests.

**Remaining:** Expand query/evaluation coverage, improve multi-turn behavior, verify live provider mode and end-to-end tool traces, then extend to policy RAG later.

## Phase 4 — Advanced Scheduling Agent (next major feature stage)

Build a sophisticated orchestration layer around the existing solver:

1. Intent routing from Supervisor.
2. Natural-language scope resolution.
3. Academic data readiness checks.
4. Missing/ambiguous-scope clarification.
5. Evidence-backed infeasibility explanation.
6. Typed optimization strategies only where supported by solver objectives.
7. Optional alternative scenario comparison using real solver/score results.
8. Proposal and explicit Admin confirmation.
9. Server-side authorization, freshness/idempotency protection.
10. Invoke existing timetable service once and return actual result.
11. Preserve draft/review/validation/publication separation.
12. Browser and regression tests for the complete proposal-to-result flow.

## Phase 5 — Resource Agent

1. Intent routing and resource-specific parsing.
2. Resolve actual resource/date/time/capacity requirements.
3. Clarify ambiguous bookings.
4. Query current availability through existing service.
5. Rank compatible available alternatives based on actual data.
6. Submit request only after appropriate user confirmation.
7. Preserve Admin-only approve/reject and existing conflict/transaction rules.
8. Return actual booking IDs/statuses and read-after-write verified state.

## Phase 6 — End-to-end multi-agent coordination

- Stable shared state/contracts across Query, Scheduling, and Resource Agents.
- Follow-up reference resolution with per-user/session isolation.
- Bounded graph execution and explicit handoffs.
- Cross-agent tasks only where use cases justify them.
- Shared tracing and response assembly based on actual results.
- Partial-failure handling and idempotency tests.
- Prevent free-form circular agent-to-agent loops.

## Phase 7 — Operational workflows

Complete the remaining operational capabilities verified to be missing:

- Change-request API and UI.
- Admin request review and reasoned decisions.
- Notifications API/UI and read/unread handling.
- Audit-log viewer with role-appropriate access and filters.
- Timetable change flow with versioning/re-optimization and affected-user notification.
- Internal event persistence, retries, and tests where needed.

Re-audit existing routes/screens before starting work to avoid rebuilding already completed functionality.

## Phase 8 — Academic data ingestion and readiness tooling

- Define official input templates/schema contracts.
- Preview/validate CSV/Excel imports.
- Map imported faculty to existing identities safely.
- Add course/faculty assignments only from authoritative records.
- Ingest rooms, capacities, time slots, course weekly requirements, and availability when supplied.
- Produce detailed import/readiness reports.
- Require confirmation and transactional/idempotent persistence.
- Test in a disposable database and preserve the workbook.

## Phase 9 — Optional RAG

- Establish approved document sources and access controls.
- Extract/chunk/version documents.
- Use pgvector or FAISS only after evaluating retrieval needs and existing dependencies.
- Retrieve relevant citations for policy/handbook questions.
- Keep operational facts on structured SQL tools.
- Evaluate grounded answer quality and retrieval precision.

## Phase 10 — Research evaluation and quality hardening

- Build labelled query corpus.
- Measure intent/tool accuracy and query resolution rate.
- Measure solver quality and runtime on controlled datasets A/B/C.
- Compare baseline/manual and OR-Tools outcomes reproducibly.
- Measure resource conflict/alternative accuracy.
- Add API contract and integration tests.
- Track critical quality regressions in CI.

## Phase 11 — Reliability and performance

- Measure solver request duration and workload before choosing a background job architecture.
- If needed, implement durable solver tasks and authenticated progress/result APIs.
- Add structured request/agent/tool correlation.
- Add safe retries, job state, idempotency and failure diagnostics.
- Load test realistic datasets.
- Reduce avoidable database queries and frontend bundle costs based on measurements.

## Phase 12 — Deployment and release (last)

Deployment begins only after core workflows are complete, tested, secured, and reproducible locally.

- Verify private repository and final source history.
- Use separate staging and production databases.
- Rotate exposed/local credentials and create fresh production secrets.
- Finalize API origins, SPA fallback/proxying, CORS, and secure cookies.
- Run migrations only on the intended target after backup and review.
- Deploy backend, database, frontend, and any required job worker.
- Validate login/refresh/logout, resource booking, agent queries, generation, validation, and publication against staging.
- Establish backup/restore, monitoring, error reporting, and rollback.
- Rehearse the capstone demonstration and report actual limits.

---

# 30. Acceptance Criteria and Definition of Done

A stage is done only when its acceptance criteria are demonstrated by source review and actual validation.

## 30.1 Agent-stage acceptance

- [ ] Correct intent routing under normal, ambiguous, and adversarial phrasing.
- [ ] Real authorized tools are invoked for supported queries.
- [ ] Role and data-scope rules are enforced inside tools/services.
- [ ] No invented database-backed facts.
- [ ] Clarification and unsupported-operation behavior is correct.
- [ ] Provider/tool failures are controlled and truthfully reported.
- [ ] No unbounded recursion or tool execution.
- [ ] Multi-turn/confirmation state is correctly isolated.

## 30.2 Scheduling acceptance

- [ ] Existing solver invoked, not duplicated.
- [ ] Readiness gates block generation when mandatory data is absent.
- [ ] Proposal precedes execution.
- [ ] Only Admin can confirm generation.
- [ ] Solver result is independent-validator checked.
- [ ] Hard violations prevent progression.
- [ ] Score/metrics are computed from actual output.
- [ ] Draft remains unpublished until the Admin lifecycle is completed.

## 30.3 Resource acceptance

- [ ] Inventory and bookings use existing backend service.
- [ ] Overlaps and timetable occupancy are checked correctly.
- [ ] Concurrent booking conflicts are protected.
- [ ] Approvals obey role and state-transition rules.
- [ ] Alternatives are actually compatible and available.
- [ ] Audit records are consistent with mutation results.

## 30.4 Product/release acceptance

- [ ] Core Admin, Faculty, Student workflows use real backend data.
- [ ] Placeholder pages identified by audit have a disposition: implemented or explicitly planned.
- [ ] Tests are isolated from the development database.
- [ ] Build/lint/type tests pass or blockers are recorded.
- [ ] Browser evidence exists for critical end-to-end flows where feasible.
- [ ] All claims distinguish verified behavior from unverified assumptions.
- [ ] Git changes are scoped; no secrets or protected workbook committed.
- [ ] Deployment is deferred until the release phase.

---

# 31. Capstone Demonstration Plan

The final demo should demonstrate the system as an integrated product, not a collection of disconnected screens.

## Demo 1 — Problem and architecture

Explain the scheduling and campus query problem. Show the three roles, FastAPI/PostgreSQL foundation, Supervisor/agents, OR-Tools solver, independent validator, and human-in-the-loop boundaries.

## Demo 2 — Grounded Query Agent

As a student, ask a supported question such as "What is my next class?" Trace the authenticated request through the Supervisor, authorized tool, database, and response. Show the source/record grounding and demonstrate that unpublished versions are not returned.

## Demo 3 — Scheduling workflow

As Admin, submit a natural-language scheduling request. Resolve any missing scope, inspect the readiness report and proposal, confirm generation, and show the actual OR-Tools outcome, validator result, and computed metrics. Then inspect the draft in the existing timetable review UI. Do not publish automatically.

## Demo 4 — Infeasible/blocked case

Use a safe isolated dataset to demonstrate missing prerequisites or a genuinely infeasible scenario. Show the real diagnostic evidence and a useful explanation rather than a fabricated schedule.

## Demo 5 — Resource allocation

Request a resource in a safe dataset, demonstrate a conflict and compatible alternatives, submit a booking request, and show the Admin review lifecycle. Demonstrate that concurrent conflicting approvals cannot both succeed.

## Demo 6 — Security boundaries

Show that students/faculty cannot trigger generation or access another user's private schedule, and that direct API/tool authorization remains effective even if the assistant is prompted to bypass policy.

## Demo 7 — Evaluation

Present actual query intent/tool/resolution metrics, timetable violations and scores, runtime, resource conflict accuracy, and baseline comparisons. State dataset provenance and test limitations.

---

# 32. Final Deliverables Checklist

## Platform

- [ ] Authenticated FastAPI application with enforced RBAC and scope checks.
- [ ] Validated academic/campus APIs and database integrity.
- [ ] Three working role portals using actual backend data.
- [ ] Timetable generation, independent validation/scoring, versioning, and Admin publication workflow.
- [ ] Resource inventory and conflict-aware booking lifecycle.

## AI

- [x] Reported Stage 9A Supervisor + Query Agent foundation (verify current integration before release).
- [ ] Advanced Scheduling Agent integrated with existing OR-Tools service.
- [ ] Resource Agent integrated with existing booking service.
- [ ] Multi-agent coordination and safe multi-turn workflows.
- [ ] Structured, authorized tool contracts and truthful response grounding.
- [ ] Development-visible safe tool trace.
- [ ] Optional RAG for institutional policies, if selected for the final scope.

## Operations

- [ ] Change-request workflows.
- [ ] Notification API/UI and appropriate delivery behavior.
- [ ] Audit-log viewer and comprehensive audit coverage.
- [ ] Official academic-data ingestion and readiness reports.
- [ ] Repeatable test datasets A/B/C.

## Quality and research

- [ ] Isolated backend tests and integration suite.
- [ ] Frontend build/lint and critical browser-path verification.
- [ ] Solver constraint and validator tests.
- [ ] Query evaluation corpus and reproducible metrics.
- [ ] Scheduling/resource experiments and research write-up.
- [ ] Security review and secret-history audit.

## Delivery

- [ ] Git checkpoints and private remote synchronized.
- [ ] No secrets or protected local workbook in repository history.
- [ ] CI and operational reliability requirements implemented as justified.
- [ ] Staging and production deployment performed only in the final phase.
- [ ] Backups, monitoring, rollback, and demonstration rehearsed.

---

# 33. Key Architectural Decisions and Open Dependencies

## 33.1 Decisions fixed by the project

- Roles are `ADMIN`, `FACULTY`, and `STUDENT` only.
- PostgreSQL is the authoritative store for operational data.
- OR-Tools is authoritative for schedule optimization.
- The deterministic validator is independent from model reasoning and solver construction.
- LLMs can parse/route/explain, but cannot invent records or bypass services.
- Existing timetable and resource engines are reused by conversational agents.
- High-impact mutations require backend authorization and auditable, appropriately confirmed workflows.
- Published schedules are distinct from drafts.
- Official academic data is never fabricated to satisfy a demonstration.
- Deployment remains deferred until development and verification are complete.

## 33.2 Dependencies requiring evidence before implementation

- Current route/schema contracts for timetable generation.
- Availability and completeness of official course assignment/room/availability data.
- Need for persistent proposals and confirmation/idempotency records.
- Measured requirement for background solver execution.
- Provider key availability and behavior in the local runtime.
- Actual state of change-request, notification, and audit-log APIs/UI.
- Feasibility and schema support for multiple weighted optimization scenarios.
- Source documents, permission model, and vector-store choice for RAG.
- Requirements for staging/production resources, backups, logging, and recovery.

## 33.3 Change-control rule

Before implementing a future stage, inspect the repository and current Git state, compare the requirements with the existing code, define a narrow acceptance boundary, implement only that stage, run safe targeted and regression tests, review the diff, and report actual results. Commit locally after review; push to the private remote at deliberate checkpoints; deploy only during the final release phase.

---

**End of RIO-MJP System Blueprint v4**
