# Control Framework Normalization

## Goal
One piece of evidence should satisfy every framework requirement it covers. Vanta's common control framework centralizes controls and maps them to multiple frameworks.

## Common Control Framework
A common control is a neutral, actionable statement such as `Enforce MFA on all workforce accounts`. It carries:
- domain
- statement
- owner
- expected evidence
- linked tests
- mapping to framework requirements

## Evidence Reuse Example

| Evidence | Common Control | Satisfies |
|---|---|---|
| Okta MFA test result | Enforce MFA | SOC 2 CC6.1, ISO 27001 A.9.4.2, HIPAA 164.312(d), PCI DSS 8.3, NIST PR.AC-1, CIS 6.3 |
| GitHub branch protection screenshot | Enforce code review | SOC 2 CC8.1, ISO 27001 A.12.1.2, PCI DSS 6.5.4, NIST PR.IP-3, CIS 7.3 |
| AWS EBS encryption config | Encrypt data at rest | SOC 2 CC6.7, ISO 27001 A.10.1.1, HIPAA 164.312(a)(1), PCI DSS 3.4, NIST PR.DS-1 |
| Terminated user access review | Manage offboarding access | SOC 2 CC6.3, ISO 27001 A.9.2.6, HIPAA 164.308(a)(3)(ii)(B), PCI DSS 8.1.4, NIST PR.AC-4 |

## Mapping Mechanics
- `common_control` has many `framework_control` mappings.
- `control_test` links a control to one or more tests.
- `evidence` is attached to `test_result`.
- A pass on a test propagates to every linked `common_control` and `framework_control`.

## Cross-Mapping Process
1. Decompose each framework into requirement statements.
2. Group requirements by intent (identity, encryption, logging, etc.).
3. Author common controls that express the intent.
4. Map common controls to framework requirements using a `framework_control_mapping` table.
5. Periodically re-evaluate mappings as frameworks update.
6. Use AI/semantic matching to suggest new mappings; require GRC expert approval.

## Versioning
- Controls and mappings are versioned.
- A new framework version can reuse existing common controls or add new mappings.
- Audit history records who changed a mapping and why.
