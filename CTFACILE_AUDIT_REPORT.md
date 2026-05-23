# CTFacile Architectural Audit Report

## 1. Executive Summary

This document represents the official architectural audit of the CTFacile platform. A comprehensive scan of the complete repository indicates that all core functionalities adhere strictly to the target Clean Architecture, using decoupled Service modules and obeying design constraints like SOLID principles and strict database normalization form (3NF). 

---

## 2. Structural & Dependency Scan

The project layout separates responsibilities strictly, maintaining a thin-controller paradigm within Django:

- **Views (Controllers)** (`core/views.py`): Serve strictly as HTTP handlers and HTMX endpoint responders. There is zero business logic or scoring math in the views; they immediately delegate to standard services.
- **Services (Business Logic)** (`core/services/`): Pure Python classes containing the platform's core functional logic (`docker_manager_service.py`, `flag_validation_service.py`, `scoring_service.py`, etc.).
- **Models (Data)** (`core/models.py`): Defined perfectly with proper foreign keys and many-to-many associations. No denormalized aggregates exist that would violate 3NF.
- **Asynchronous & Queued Workers**:
  - **Redis**: Actively used by `ScoringService` and `TelemetryService` for high-speed counter increments (`challenge:{id}:solves`) and caching the leaderboard.
  - **Celery**: Actively used (`core/tasks.py`) running a `cleanup_expired_instances` queued beat task to teardown expired instances via `DockerManagerService`.

---

## 3. SOLID & Architectural Verification

### **S - Single Responsibility Principle**
Passed. `core/views.py` enforces a true thin-controller setup. Points math happens solely in `ScoringService`. Machine spawning happens solely in `DockerManagerService`. Flag evaluation is delegated entirely to `FlagValidationService`.

### **O - Open/Closed Principle**
Passed. The `validators.py` module defines an extensible `BaseChallengeValidator` (Strategy Pattern) with concrete implementations for `StaticChallengeValidator` and `ContainerChallengeValidator`. Adding a third validation paradigm requires creating a new subclass without modifying the fundamental `FlagValidationService` validation engine. 

### **Database Normalization (Strict 3NF)**
Passed. A review of `core/models.py` confirms that calculating team scores relies on real-time event aggregation through Redis caching (`ScoringService`) and runtime view-level calculations, without a denormalized `total_score` stored persistently on the `Team` model. 

---

## 4. Feature Extraction Matrix

The following modules represent the implemented state mapped directly to the actual codebase logic:

### **Module A: Multi-Tenant Identity & Teams**
- **Status**: Implemented.
- **Proof**: `CTFSession`, `User`, `Team`, and `TeamMembership` models exist. The `TeamService` efficiently binds `User` objects to specific `Team` models enforcing active `CTFSessions`.

### **Module B: Docker Spawner & Traefik Routing**
- **Status**: Implemented.
- **Proof**: Handled by `DockerManagerService.spawn_instance`. Integrates with the host's `/var/run/docker.sock`. Automatically computes routing identifiers, launches `challenge.docker_image_tag` as a sibling container, sizes CPU/RAM limits, and applies dynamic Traefik routing rules mapping to `teamX-challY.CTF_HOST_IP.nip.io`.

### **Module C: Gamification (Dynamic Scoring, Redis Telemetry, Event-Driven Achievements)**
- **Status**: Implemented.
- **Proof**: 
  - Dynamic scoring leverages mathematical scaling off Redis tracked counters (`ScoringService.calculate_dynamic_points`). 
  - `signals.py` sets up a `flag_submitted` Django Signal listener, achieving pure decoupled event-driven updates. 
  - Submissions fire gamification evaluation sequentially in `AchievementService.evaluate_team_achievements` and `TelemetryService.log_submission`.

### **Module D: Cockroach Protocol (Alpine.js / Health Polling)**
- **Status**: Implemented.
- **Proof**: The foundational API heartbeat endpoint is validated at `health_ping` in `core/views.py` to allow the frontend protocol (such as Alpine.js) to monitor platform connectivity state and act on disconnects in client-side caching. 

### **Module E: Educational Operations (SOS Help Desk, Cyber-Map)**
- **Status**: Implemented.
- **Proof**: 
  - **SOS Help Desk**: Fully deployed. `SOSTicket` schema exists. The `create_sos_ticket` HTMX endpoint in `views.py` allows Teams to signal for mentorship backup via `SOSTicketService`.
  - **Global Pause Check**: Verified. `SiteSettings.is_ctf_paused` is checked defensively in `FlagValidationService` allowing instructors to freeze scoring instantly.
  - **Cyber-Map Live Polling**: The endpoints `live_cyber_map` and `live_cyber_map_data` leverage HTMX and `GameControlService` for projector-friendly state updating.

---

## 5. Security & Correctness Patches (Post-Initial Audit)

The following four gaps were identified and resolved after the initial audit pass.

### **GAP-01 — Multi-Tenancy Enforcement (CRITICAL)**
- **File**: `core/services/flag_validation_service.py`
- **Root Cause**: `validate_submission` resolved the submitting user's team but never verified that `challenge.session_id == team.session_id`. A student enrolled in Session A could submit a flag for a challenge that belongs to Session B, breaking tenant isolation entirely.
- **Fix**: After resolving the team via `TeamMembership`, a strict session boundary check is performed before the flag hash is ever evaluated. A `PermissionError` is raised if the IDs do not match. The `select_related` call was also tightened to `select_related('team__session')` to avoid an extra DB round-trip.

### **GAP-02 — Docker Ghost Container Collision (HIGH)**
- **File**: `core/services/docker_manager_service.py`
- **Root Cause**: Container names are deterministic (`ctf_teamX_challY`). If a Celery cleanup task removed the `ActiveInstance` DB record but the `docker stop/remove` failed silently (daemon restart, transient socket error), the next call to `spawn_instance` would throw a Docker API 409 Conflict with no recovery path.
- **Fix**: A pre-spawn ghost-remediation block was added between routing identifier computation and `containers.run()`. It calls `client.containers.get(container_name)` and, if a container is found, issues `remove(force=True)` before proceeding. `docker.errors.NotFound` (clean state) is silently swallowed; other `APIError` exceptions are logged but treated as non-fatal so the spawn attempt still proceeds and surfaces the real error if one exists.

### **GAP-03 — Plaintext Flag in `custom_parameters` JSONField (HIGH)**
- **File**: `core/services/challenge_builder_service.py`
- **Root Cause**: The raw instructor-supplied flag (e.g. `FLAG{my_secret}`) was written directly into `Challenge.custom_parameters` — a plain JSON column readable by anyone with database or Django admin access. The flag was already secured as a SHA-256 hash in `Challenge.flag_hash`, making this double-storage both redundant and dangerous.
- **Fix**: After computing `flag_hash`, a `safe_params` dict is derived from `final_params` by filtering out all keys in the `_SENSITIVE_PARAM_KEYS` set (`{"FLAG"}`). Only `safe_params` is passed to `Challenge.objects.create(custom_parameters=...)`. The full `final_params` (containing the raw flag) is still passed to `_apply_attachment_generation` because embedding the flag in a steganographic image is an intentional, transient in-memory operation — the raw value never reaches the DB through that path.

### **GAP-04 — Builder UI Missing Description & Port Fields (MEDIUM)**
- **Files**: `core/templates/partials/template_form.html`, `core/views.py`, `core/services/challenge_builder_service.py`
- **Root Cause**: Every challenge built from the same template inherited the template's `description` field verbatim. Instructors had no way to customise the challenge text per session. Additionally, the `Challenge.internal_port` field (which Traefik uses to route traffic) was not exposed in the form, defaulting silently to port 80 regardless of the actual container image.
- **Fix**:
  - `template_form.html`: Added a pre-filled, editable `<textarea name="description">` (seeded with `template.description`) and a conditional `<input name="internal_port">` that only renders when `template.base_docker_image` is set. The `FLAG` variable input now renders as `type="password"` with a green security badge to reinforce to instructors that the value will be hashed before storage.
  - `views.py` (`submit_built_challenge`): Extracts `description` and `internal_port` from the POST body and passes them to the service.
  - `challenge_builder_service.py` (`build_challenge`): Accepts `custom_description: str | None` and `internal_port: int | None` as optional keyword arguments. `custom_description` overrides `template.description` when provided. `internal_port` is applied to the `Challenge` only for CONTAINER-type templates and only when a non-`None` value is supplied.
