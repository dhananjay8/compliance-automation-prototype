# Security Model

## Multi-Tenancy
- Row-level tenant isolation on every table.
- Tenant-scoped connection pools and request context.
- Optional dedicated database per tenant for enterprise or Gov deployments.
- Organizations within a tenant support scoping by business unit, geography, or product.

## Authentication
- SSO via SAML 2.0 and OIDC.
- SCIM 2.0 user provisioning.
- MFA enforced for administrators and compliance owners.
- API keys and OAuth tokens with restricted scopes.

## Authorization
- Role-based access control: admin, compliance manager, control owner, auditor, read-only, external auditor.
- Fine-grained authorization platform supports resource-level delegation.
- Cross-functional collaboration without overprovisioning.
- Every API request resolves actor, resource, and permission.

## Audit Logging
- Immutable logs of all reads and writes.
- Evidence review, control changes, and mapping changes logged.
- AI call tracing: prompt, response, tool invocation, and latency.
- Retention policies per framework and customer requirements.

## Encryption
- TLS 1.3 in transit.
- AES-256 at rest for databases, object storage, and backups.
- Field-level encryption for credentials and secrets.
- KMS-backed key rotation.

## Secrets Management
- Credentials stored in HashiCorp Vault or cloud KMS.
- Short-lived tokens where possible.
- OAuth refresh tokens encrypted.
- IAM role assumption with external ID.
- No plaintext secrets in logs or dumps.

## Data Privacy
- GDPR data processing agreements and retention controls.
- Data residency options (US, EU, AU, Gov).
- Right to erasure and data portability workflows.
- Metadata-only scanning; customer content is not read.

## Compliance
Vanta's own program covers SOC 2, ISO 27001, HIPAA, GDPR, and PCI DSS. Controls include:
- Access reviews and least privilege.
- Vulnerability management.
- Change management.
- Incident response.
- Vendor risk management.
- Security awareness training.
