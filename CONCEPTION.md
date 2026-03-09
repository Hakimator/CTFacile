# CTFacile - Master Architectural Context

## 1. Project Identity & Purpose
**Name:** CTFacile
**Mission:** A multi-tenant, cloud-based Capture The Flag (CTF) and educational platform. Designed to be highly resilient to network drops, heavily gamified (Skill Trees, Duolingo-style tutorials), and secure (isolated Docker challenges routed via Traefik).

## 2. Technical Stack
* **Backend:** Python 3.11+, Django, Django Rest Framework (DRF).
* **Database (Persistent):** PostgreSQL (Strict 3NF).
* **Database (Ephemeral/Telemetry):** Redis.
* **Asynchronous Workers:** Celery.
* **Infrastructure:** Docker, Docker-Compose, Traefik (Reverse Proxy), MinIO (S3-compatible Object Storage).

## 3. Mandatory Architectural Rules (STRICT ENFORCEMENT)
Any code generated for this project MUST adhere to these architectural rules. 

1. **Service Layer Pattern (Clean Architecture):**
    * `models.py`: Strictly database schema definitions. NO business logic, NO score calculation, NO API calls.
    * `views.py` (API Layer): Strictly HTTP transport. Validates incoming JSON via Serializers, calls the appropriate Service, returns HTTP responses.
    * `services.py`: The Brain. All business logic lives here. (e.g., `FlagValidationService`, `DockerManagerService`, `AchievementService`).
2. **No Magic Numbers:** * Absolutely no hardcoded string lengths, default points, or choice tuples in `models.py`. 
    * All limits must be imported from a centralized `core/constants.py` file using `models.TextChoices`.
3. **Strict 3NF Normalization (PostgreSQL):**
    * Do not store calculable data (like `total_score` or `failed_attempts`) in PostgreSQL. Those metrics are tracked in Redis or calculated via Django `.annotate()`.

---

## 4. Exhaustive Relational Database Schema (PostgreSQL)

### Module A: Identity, Sessions & Teams
* **`CTFSession`**: The overarching event (e.g., "Cyberweek 2026"). Fields: `name`, `is_active`, `scoring_mode` (Enum: STATIC/DYNAMIC), `language_lock` (Enum: NONE/EN/FR), `start_time`, `end_time` (both nullable).
* **`User`**: Extends Django `AbstractUser`. Fields: `role` (Enum: ADMIN/PROF/STUDENT), `ui_theme` (Enum: LIGHT/DARK/HACKER), `preferred_language`.
* **`Team`**: Tied to `CTFSession`. Fields: `name`, `join_code` (UUID, unique).
* **`TeamMembership`**: (Pivot Table). Links `User` to `Team`. (Allows users to be in different teams across different sessions).

### Module B: The Gamified Skill Tree & Challenges
* **`Category`**: Fields: `name`, `description`.
* **`Challenge`**: The core playable node. Fields: 
    * `session_id` (FK to CTFSession)
    * `category_id` (FK to Category)
    * `title`, `description` (Markdown, supports dynamic Admin template tags)
    * `base_points`, `flag_hash` (SHA-256)
    * `is_tutorial` (Boolean - True for Duolingo-style questlines)
    * `is_entry_node` (Boolean - True if unlocked by default)
    * `docker_image_tag` (String, nullable. Triggers container deployment if present).
* **`ChallengePrerequisite`** (Skill Tree Logic): Many-to-Many pivot. Fields: `target_challenge_id`, `required_challenge_id`.

### Module C: Infrastructure & State
* **`ActiveInstance`**: Tracks running Docker containers. Expiration logic managed by server-side Celery, immune to client disconnects. Fields: 
    * `team_id` (FK to Team)
    * `challenge_id` (FK to Challenge)
    * `container_id` (String)
    * `traefik_subdomain` (String - unique, e.g., "team1-sqli.ctfacile.local")
    * `expires_at` (DateTime).

### Module D: Immutable Auditing, Education & Gamification
* **`Submission`**: Immutable log of all flag attempts. Fields: 
    * `user_id` (The actual typist)
    * `team_id` (The credited team)
    * `challenge_id`
    * `submitted_payload` (String)
    * `is_correct` (Boolean, default False, indexed)
    * `timestamp` (DateTime, indexed).
* **`Achievement`**: Dynamic gamification rules. Fields: `title`, `description`, `trigger_type` (Enum: FIRST_BLOOD, ATTEMPT_COUNT, SOLVE_STREAK, etc.), `threshold_value` (Integer), `is_secret` (Boolean, default False), `icon_reference` (Char, for Lottie file names).
* **`TeamAchievement`**: Pivot table locking in a badge. Fields: `team_id` (FK), `achievement_id` (FK), `unlocked_at` (DateTime), `unlocked_by_user_id` (FK to User). Unique together on (team, achievement).
* **`WriteUp`**: Methodology reports. Fields: `team_id`, `challenge_id`, `content` (Markdown), `submitted_at`.
* **`SOSTicket`**: Help desk for stuck students. Fields: `team_id`, `challenge_id` (nullable), `issue_description`, `status` (Enum: OPEN/IN_PROGRESS/RESOLVED).

### Module E: Global Controls
* **`SiteSettings`**: strictly a Singleton model (override `save()` to prevent multiple rows). Fields: `is_ctf_paused` (Boolean), `global_announcement` (Text), `discord_webhook_url` (URL).

---

## 5. Redis Telemetry & Gamification Engine
To preserve PostgreSQL performance and strict 3NF normalization, all rapid-fire metrics, counters, and leaderboard calculations MUST be handled in Redis. 



* **Dynamic Scoring Rule:** Do NOT calculate dynamic challenge points by querying the `Submission` table repeatedly. Maintain a Redis counter `challenge:{id}:solves`. The `ScoringService` reads this counter to calculate the current point degradation.
* **Anti-Cheat & Rate Limiting:** Track `user:{id}:submissions_per_minute` in Redis. If it exceeds threshold, the API immediately throws HTTP 429 Too Many Requests.
* **Team & User Telemetry:** Track the following keys in Redis Hash Maps for fast achievement validation:
    * `team:{id}:total_failed_attempts`
    * `team:{id}:hints_purchased`
    * `user:{id}:first_bloods`
    * `user:{id}:consecutive_solves`

## 6. Event-Driven Architecture (Achievements)
* **Rule of Decoupling:** The `FlagValidationService` MUST NOT contain the logic for checking achievements (e.g., no `if fails == 3: grant_achievement()`).
* **Implementation:** Use an Event Bus (Django Signals or Celery Tasks). When a flag is correct, emit a `FlagSolvedEvent`. A separate `AchievementService` listens for this event, reads the Redis telemetry, and determines if a badge is unlocked.
* **Custom Achievements:** Achievement rules should be dynamic (evaluating Redis metrics against a threshold operator like `>=`, `==`), allowing Admins to create new achievements via the UI without code changes.

## 7. The Asset Pipeline (MinIO / S3)
* **Stateless Backends:** Django backend containers must remain stateless. Local storage of user uploads is STRICTLY FORBIDDEN.
* **Media Management:** Use `django-storages` and `boto3`. All user-uploaded media (Write-Up PDFs, custom Admin achievement icons) must be routed directly to the MinIO (S3-compatible) Object Storage bucket.
* **Gamification Assets:** Achievement pop-up animations must use lightweight **Lottie (.json)** vector files, not heavy GIFs. Default Lottie files are served by the frontend static directory; custom ones are served via MinIO.

## 8. State Resilience (The "Cockroach" Protocol)
* **Frontend Auto-Save:** The frontend UI must implement `onChange` or `onBlur` listeners on all text inputs (Write-ups, flag submissions) to continuously cache data in browser `localStorage`. 
* **Heartbeat Monitor:** The frontend must ping `GET /api/v1/health/ping` every 15 seconds. If the network drops, the UI transitions to "Offline Mode" but retains cached input state. 
* **Decoupled Containers:** The `DockerManagerService` manages container lifecycle entirely on the backend via Celery Beat querying the `ActiveInstance.expires_at` column. Client network disconnections have ZERO impact on running containers.