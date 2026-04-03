# Design Document — Ingest Worker

**Component:** `backend/ingest/worker.py`  
**Date:** February 26, 2026  
**Project:** GitHub Sponsor Dashboard (ICSE 2026)

---

## 1. Overview

The ingest worker is the core data-collection engine of the system. It operates as a continuous background process that discovers GitHub users who participate in the GitHub Sponsors ecosystem, scrapes their metadata and sponsorship relationships via the GitHub REST and GraphQL APIs, and persists structured records to a PostgreSQL database. The worker drives a priority-based queue to ensure high-value users (those with many sponsor connections) are processed first.

---

## 2. Architecture Summary

```
IngestWorker.run()
      │
      ├── State & Seeding ──────────► getSponsorableUsers()
      │
      ├── Authentication ───────────► is_auth_expiring_soon() / get_auth()
      │
      ├── Stale Re-ingestion ───────► enqueueStaleUsers()
      │
      ├── Queue Fetch ──────────────► getFirstInQueue()
      │
      ├── User Resolution ──────────► findUser() → createUser() / enrichUser()
      │
      ├── Sponsorship Crawl ────────► get_sponsorships()
      │       ├── get_sponsors_from_api()      [GraphQL]
      │       └── get_sponsored_from_api()     [GraphQL]
      │
      ├── Batch Operations ─────────► batchCreateUser() / batchAddQueue()
      │
      ├── Activity Collection ──────► refreshActivityCheck() / getUserActivity()
      │
      ├── Sync & Finalize ──────────► syncSponsors() / syncSponsorships()
      │                               updateStatus() / finalizeUserScrape()
      │
      └── Error Recovery ───────────► psycopg2.OperationalError → reconnect
```

---

## 3. Primary Functions

### 3.1 `IngestWorker.run()`

**Location:** `backend/ingest/worker.py`  
**Purpose:** Entry point and main event loop for the entire ingest pipeline.

**Responsibilities:**
- Establishes the PostgreSQL database connection and initializes the logger.
- Reads `worker_state.json` on each iteration to determine whether a full or incremental seed is needed.
- Orchestrates all sub-components: authentication, queue management, user resolution, sponsorship crawling, activity collection, and finalization.
- Handles reconnection on `psycopg2.OperationalError` and graceful shutdown on unhandled exceptions.

**Key Parameters / State:**
| Variable | Description |
|---|---|
| `init_run` | Whether the worker has ever completed a full initialization pass |
| `last_init_run` | ISO 8601 timestamp of the last seeding run |
| `last_stale_check` | Unix timestamp used to gate the 4-hour stale re-ingestion cycle |
| `MAX_PRIORITY` | Ceiling value (`10`) for the queue priority score |

**Control Flow Summary:**

1. Load worker state → decide full seed vs. incremental seed.
2. Check/refresh GitHub auth token.
3. Every 4 h: re-establish DB connection + enqueue stale users.
4. Pop highest-priority user from queue.
5. Resolve user (create / enrich).
6. Crawl sponsorships.
7. Compute new priority and batch-enqueue discovered users.
8. Collect activity data if warranted.
9. Sync sponsorship edges; finalize scrape timestamp.

---

### 3.2 `getSponsorableUsers(conn, init_run)`

**Location:** `backend/ingest/utils.py`  
**Called from:** `IngestWorker.run()` — seeding step  
**Purpose:** Seeds the queue with GitHub user IDs that are eligible to participate in GitHub Sponsors. Uses Playwright to scrape the GitHub Sponsors Explore page, collecting IDs for all listed sponsorable users.

**Behavior:**
- `init_run=True` triggers a full pass across all pages.
- `init_run=False` performs an incremental pass (stops when previously-seen users are encountered).
- Delegates to `batchAddQueue()` to persist discovered IDs.

---

### 3.3 `getFirstInQueue(db)`

**Location:** `backend/db/queries/queue.py`  
**Called from:** `IngestWorker.run()` — queue fetch step  
**Purpose:** Returns the GitHub ID and priority score of the highest-priority `pending` user in the `queue` table.

**SQL:** `SELECT github_id, priority FROM queue WHERE status = 'pending' ORDER BY priority DESC LIMIT 1`

**Returns:** `{"github_id": int, "priority": int}` or `None` if the queue is empty.

---

### 3.4 `findUser(github_id, db)`

**Location:** `backend/db/queries/users.py`  
**Called from:** `IngestWorker.run()` — user resolution step  
**Purpose:** Looks up a user by `github_id` in the `users` table and returns their internal `id`, `user_exists` flag, and `is_enriched` flag.

This result drives the branch decision in the worker:

| `user_exists` | `is_enriched` | Action taken |
|---|---|---|
| `False` | — | `createUser()` |
| `True` | `False` | `enrichUser()` (first enrichment pass) |
| `True` | `True` | `enrichUser()` (refresh pass) |

---

### 3.5 `createUser(github_id, db)`

**Location:** `backend/db/queries/users.py`  
**Called from:** `IngestWorker.run()` — when user does not exist  
**Purpose:** Fetches complete user metadata from the GitHub REST API and writes a full user record to the `users` table.

**Data collected:**
- Username, display name, account type (`user` / `organization`)
- Location, bio, avatar URL, profile URL, company
- Follower / following counts, public repos, public gists
- Twitter username, email, `hireable` flag
- Inferred gender (via OpenAI API) and `has_pronouns` flag
- Account creation date (`github_created_at`)

**Returns:** `(UserModel, user_id)`

---

### 3.6 `enrichUser(github_id, db, enriched, identity)`

**Location:** `backend/db/queries/users.py`  
**Called from:** `IngestWorker.run()` — when user exists but needs updated metadata  
**Purpose:** Re-fetches user data from GitHub and updates the existing row. The `enriched` flag controls whether identity information already cached in `identity` can be reused, reducing redundant API calls on subsequent passes.

**Returns:** `UserModel`

---

### 3.7 `get_sponsorships(username, github_id, user_type)`

**Location:** `backend/ingest/utils.py`  
**Called from:** `IngestWorker.run()` — sponsorship crawl step  
**Purpose:** Parent wrapper that invokes both sponsorship direction queries and returns the consolidated result.

**Returns:** `(sponsors: list[int], sponsoring: list[int], private_count: int, min_sponsor_tier: float)`

---

### 3.8 `get_sponsors_from_api(github_id, user_type)`

**Location:** `backend/ingest/utils.py`  
**Called from:** `get_sponsorships()`  
**Purpose:** Fetches all GitHub users / organizations that **sponsor** the given user using the `sponsorshipsAsMaintainer` GraphQL field. Handles pagination (`first: 100, after: $cursor`) transparently.

**Notable behavior:**
- Encodes the `github_id` into GitHub's Base64 node ID format (prefix `04:User` or `12:Organization`).
- Counts private sponsors separately (`privacyLevel == "PRIVATE"`), returning them as `private_count`.
- Extracts the lowest non-one-time monthly sponsorship tier price in dollars.
- Raises `Exception("Partial fetch detected: ...")` on GraphQL errors to prevent incomplete data from being committed.

---

### 3.9 `get_sponsored_from_api(github_id, user_type)`

**Location:** `backend/ingest/utils.py`  
**Called from:** `get_sponsorships()`  
**Purpose:** Fetches all GitHub users / organizations that the given user is **sponsoring** using the `sponsorshipsAsSponsor` GraphQL field. Uses the same pagination and Base64 node ID encoding strategy as `get_sponsors_from_api()`.

**Returns:** `list[int]` of GitHub database IDs.

---

### 3.10 `batchCreateUser(github_ids, db)`

**Location:** `backend/db/queries/users.py`  
**Called from:** `IngestWorker.run()` — after sponsorship traversal  
**Purpose:** Inserts placeholder rows into `users` for every newly discovered GitHub ID. Uses `ON CONFLICT (github_id) DO NOTHING` to safely handle duplicates. These stubs satisfy foreign key constraints so that `batchAddQueue()` can immediately reference them.

---

### 3.11 `batchAddQueue(github_ids, priority, db)`

**Location:** `backend/db/queries/queue.py`  
**Called from:** `IngestWorker.run()` and `getSponsorableUsers()`  
**Purpose:** Inserts a batch of GitHub IDs into the `queue` table at a specified priority. Uses an upsert strategy:
- On conflict, keeps the **higher** of the existing and incoming priority values.
- Resets `status` to `pending` if the existing status is `failed`.

---

### 3.12 `batchRequeue(db)`

**Location:** `backend/db/queries/queue.py`  
**Called from:** `IngestWorker.run()` — when the queue is fully drained  
**Purpose:** Resets the status of every `completed` row in the queue back to `pending`, allowing all previously processed users to be re-scraped in a subsequent cycle.

---

### 3.13 `enqueueStaleUsers(db, days_old)`

**Location:** `backend/db/queries/queue.py`  
**Called from:** `IngestWorker.run()` — on 4-hour timer  
**Purpose:** Re-enqueues users whose `last_scraped` timestamp is older than the `days_old` threshold (default: 7 days). Updates `created_at` to `NOW()` so they appear at the end of the current pending batch rather than jumping the queue.

---

### 3.14 `updateStatus(github_id, status, db, priority)`

**Location:** `backend/db/queries/queue.py`  
**Called from:** `IngestWorker.run()` — after processing each user  
**Purpose:** Updates the `status` column (and optionally `priority`) for a specific user in the `queue` table. Statuses used by the worker: `pending`, `completed`, `skipped`, `failed`.

---

### 3.15 `syncSponsors(github_id, sponsors, db)` / `syncSponsorships(github_id, sponsoring, db)`

**Location:** `backend/db/queries/sponsors.py`  
**Called from:** `IngestWorker.run()` — after a successful sponsorship fetch  
**Purpose:** Performs a full replace of the sponsor / sponsoring edge sets for the given user in the `sponsorships` table. Existing edges no longer in the API response are removed; new edges are inserted.

---

### 3.16 `finalizeUserScrape(github_id, private_count, min_sponsor_tier, db)`

**Location:** `backend/db/queries/users.py`  
**Called from:** `IngestWorker.run()` — last step before moving to the next user  
**Purpose:** Writes the `last_scraped` timestamp, `private_sponsors_count`, and `min_sponsor_tier` back to the `users` table, marking the user as fully processed for this cycle.

---

### 3.17 `refreshActivityCheck(user_id, db)` / `getUserActivity(...)`

**Location:** `backend/db/queries/user_activity.py`  
**Called from:** `IngestWorker.run()` — conditionally, only for users with sponsor relations  
**Purpose:**
- `refreshActivityCheck` returns `True` if the user has no activity record or it is more than 365 days old.
- `getUserActivity` fetches the user's public contribution history from GitHub and writes it to the `user_activity` table. This step is intentionally gated to reduce API usage, since activity data is only meaningful for users who have at least one sponsorship edge.

---

### 3.18 `is_auth_expiring_soon()` / `get_auth()`

**Location:** `backend/ingest/use_auth.py`  
**Called from:** `IngestWorker.run()` — top of each loop iteration  
**Purpose:**
- `is_auth_expiring_soon()` checks the expiry of the GitHub Personal Access Token stored in `auth.json` and returns `True` if renewal is needed.
- `get_auth()` refreshes the token (via a device flow or pre-configured rotation mechanism) and updates `auth.json`.

---

### 3.19 `load_worker_state()` / `update_worker_state()`

**Location:** `backend/ingest/init_check.py`  
**Called from:** `IngestWorker.run()` — top of each loop iteration  
**Purpose:** Reads and writes `backend/ingest/worker_state.json`, which persists:
- `init_run` — whether the initial full seed has been completed.
- `last_init_run` — ISO 8601 timestamp of the last time `getSponsorableUsers()` was called.

These values control seeding frequency: a full seed is triggered when `last_init_run` is absent or older than 1 year; an incremental pass is triggered when it is older than 2 weeks.

---

## 4. Priority Scoring

The worker applies a simple dynamic priority scheme to guide crawl order:

| Condition | Priority Change |
|---|---|
| New unique users discovered in sponsorship result | `min(current + 1, 10)` |
| Existing relationships found but no new users | unchanged |
| No sponsorship relationships at all | `max(current - 1, 1)` |

Newly discovered batch users are always inserted at a default middle priority of **5**.

---

## 5. Error Handling Strategy

| Exception Type | Handling |
|---|---|
| `psycopg2.OperationalError` | Log warning, reconnect to DB, `continue` loop |
| `ValueError` from `createUser` / `enrichUser` | User deleted on GitHub — log and `continue` |
| Any exception in `get_sponsorships()` | Log and `continue` — `last_scraped` is NOT updated so the user is retried |
| Unhandled `Exception` | Log with traceback, `time.sleep(10)`, `break` (worker exits) |

---

## 6. Periodic Maintenance Tasks

| Interval | Task |
|---|---|
| Every loop iteration | Check auth token expiry |
| Every 2 weeks | Incremental `getSponsorableUsers()` pass |
| Every 1 year (or first run) | Full `getSponsorableUsers()` seed |
| Every 4 hours | `enqueueStaleUsers(days_old=7)` + DB reconnect |
| Queue drained | `batchRequeue()` to restart full cycle |

---

## 7. Data Flow Diagram

```
GitHub REST API ──────► getUserData() ──────────► users table
                                                         ▲
GitHub GraphQL API ───► get_sponsors_from_api()          │
                    └─► get_sponsored_from_api()          │
                              │                           │
                              ▼                           │
                        sponsorships table         finalizeUserScrape()
                              │                           │
                              ▼                           │
                        batchCreateUser() ───────────────►│
                        batchAddQueue()  ──► queue table  │
                                                          │
GitHub REST API ──────► getUserActivity() ──► user_activity table
```
