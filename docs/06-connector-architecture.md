# Connector Architecture

## Connector Categories
| Category | Examples | Data Produced |
|---|---|---|
| Cloud Providers | AWS, Azure, GCP | accounts, storage buckets, compute instances, IAM policies, encryption settings, network configs |
| Identity Providers | Okta, Azure AD, Google Workspace | users, groups, roles, MFA status, app assignments, sign-in logs |
| MDM / Endpoint | Jamf, Intune, Kandji | computers, devices, disk encryption, OS version, agent status |
| Code Repos | GitHub, GitLab, Bitbucket | repos, branch protection, pull requests, committers, secrets scanning |
| Ticketing | Jira, ServiceNow | change tickets, incident tickets, SLA data |
| Communication | Slack, Teams | workspace membership, DLP settings (metadata only) |
| HRIS | Workday, BambooHR, HiBob | employees, start/end dates, departments |
| Vulnerability | CrowdStrike, SentinelOne, Orca | vulnerabilities, endpoints, patch status |
| Training | KnowBe4, SAI360 | training records, completion status |
| Custom | Private integrations | any resource type defined by customer |

## Connector Design

### Adapter Pattern
Each connector has:
- `connector.py` / `connector.ts`: source API client.
- `mapper`: source schema to canonical `resource_type`.
- `auth_handler`: OAuth, API token, IAM role, service account.
- `scheduler`: cadence and incremental sync.
- `normalizer`: identity resolution and deduplication.

### Auth Models
- OAuth 2.0 authorization code (public integrations).
- OAuth 2.0 client credentials / private key (private integrations, Okta, Google Workspace).
- Cross-account IAM role with external ID (AWS).
- API token or SSWS (legacy or restricted environments).
- GitHub App with scoped permissions.
- SCIM 2.0 for user provisioning.

### Vanta-Specific Patterns
- Read-only metadata collection; no write access to customer systems.
- Hourly automated tests after sync.
- External ID in trust policy prevents confused deputy.
- DPoP can be disabled for Okta private-key flows.
- Three API surfaces separate ingestion, management, and audit.

### Resource Types
Built-in resource types include:
- `UserAccount`
- `Computer`
- `Vulnerability`
- `TrainingRecord`
- `BackgroundCheck`
- `PolicyAcknowledgement`
- `Vendor`
- `AccessReview`
- Custom resource types through Build Integrations API.

### Sync Job Lifecycle
1. Authenticate and validate credentials.
2. Discover scopes (accounts, projects, orgs).
3. Pull incremental changes since last watermark.
4. Transform to canonical schema.
5. Write normalized resources to Trust Graph.
6. Trigger dependent tests and workflows.
7. Update sync status, watermark, and health metrics.

### Reliability
- Exponential backoff with jitter.
- Pagination support.
- Rate-limit handling per provider.
- Dead-letter queue for unprocessable records.
- Watermark-based delta sync to avoid full rescans.

## Example: AWS Connector
1. Customer creates `vanta-auditor` IAM role.
2. Trust policy allows Vanta scanner account with external ID.
3. Role grants `SecurityAudit` + `VantaAdditionalPermissions` read-only policies.
4. Vanta assumes role, lists accounts, scans services.
5. Resource records are normalized and mapped to controls.
