# Scheduling, Evidence Freshness, and Drift Detection

## Scheduling
- Each connector has a sync schedule (default hourly).
- Each test has an evaluation schedule (default hourly or on each sync completion).
- Scheduler uses a job queue with priority and tenant isolation.
- Ad-hoc runs supported for auditors and administrators.

## Evidence Freshness
- Every evidence record carries `collected_at` and `expires_at`.
- Dashboards show freshness indicator (green < 24h, yellow 24-48h, red > 48h).
- Stale evidence triggers re-collection and alerts.
- Manual uploads can be marked with review date and reviewer.

## Drift Detection
- Baseline: expected state from passing test runs and policies.
- Current state: latest resource snapshot.
- Drift engine compares snapshots and re-evaluates tests when significant changes occur.
- Examples: new admin user, disabled MFA, public S3 bucket, terminated employee still has access.

## Continuous Compliance
- Tests run continuously, not only at audit time.
- Failures are surfaced immediately with remediation guidance.
- Framework readiness score updates in real time.
- Evidence history provides the time-series view auditors need for Type II reports.

## Remediation SLA
- Each failed control has a target resolution time.
- Workflow engine escalates overdue items.
- Tickets can be created in Jira/ServiceNow automatically.
- Status updates flow back into the Trust Graph when the connector rescans.

## Audit Trail
- Every sync, test run, and manual action is logged.
- Logs include actor, timestamp, resource, and result.
- Immutable append-only storage for compliance evidence.
