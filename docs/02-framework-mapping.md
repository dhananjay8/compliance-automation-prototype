# Framework Mapping

## Purpose
Map a single common control to requirements across SOC 2, ISO 27001, HIPAA, GDPR, CIS, NIST CSF, and PCI DSS. Vanta uses a common control framework to reduce duplicate evidence collection.

## Control Domains
1. Access Control
2. Asset Management
3. Encryption
4. Logging & Monitoring
5. Incident Response
6. Vendor Management
7. Security Awareness & Training
8. Change Management
9. Identity & Access Management
10. Data Protection & Privacy

## Cross-Framework Mapping Table

| Domain | Common Control | SOC 2 | ISO 27001 | HIPAA | GDPR | PCI DSS | CIS | NIST CSF |
|---|---|---|---|---|---|---|---|---|
| Access Control | Enforce MFA for all user accounts | CC6.1, CC6.2 | A.9.4.2 | 164.312(d) | Art. 32 | 8.3 | 6.3 | PR.AC-1 |
| Access Control | Review and revoke terminated employee access | CC6.2, CC6.3 | A.9.2.6 | 164.308(a)(3)(ii)(B) | Art. 5(1)(f), 32 | 8.1.4, 8.1.6 | 6.4 | PR.AC-4 |
| Asset Management | Maintain inventory of endpoints and cloud assets | CC6.1 | A.8.1.1 | 164.310(d)(1) | Art. 30 | 9.4.1, 11.3.2 | 1.1, 1.2 | ID.AM-1 |
| Encryption | Encrypt data at rest and in transit | CC6.1, CC6.7 | A.10.1.1, A.10.1.2 | 164.312(a)(1), 164.312(e)(1) | Art. 32 | 3.4, 4.1, 8.2.1 | 3.11, 3.12 | PR.DS-1, PR.DS-2 |
| Logging & Monitoring | Collect and protect audit logs | CC7.2, CC7.3 | A.12.4.1, A.12.4.2 | 164.312(b) | Art. 5(1)(f), 32 | 10.2, 10.3 | 8.2, 8.5 | DE.AE-3 |
| Incident Response | Document and exercise incident response plan | CC7.4, CC7.5 | A.16.1.1 | 164.308(a)(6) | Art. 33 | 12.10.1 | 17.1, 17.2 | RS.RP-1 |
| Vendor Management | Assess and monitor third-party vendors | CC9.1, CC9.2 | A.15.1.1, A.15.2.1 | 164.308(b)(1) | Art. 28 | 12.8.1, 12.9 | 15.1, 15.2 | ID.SC-1 |
| Training | Deliver security awareness training and track completion | CC2.3, CC7.1 | A.7.2.2 | 164.308(a)(5) | Art. 32 | 12.6.1, 12.6.2 | 14.1, 14.2 | PR.AT-1 |
| Change Management | Enforce code review and approved change tickets | CC8.1 | A.12.1.2 | 164.308(a)(8) | Art. 5(1)(d), 32 | 6.3.2, 6.5.4 | 4.6, 7.3 | PR.IP-3 |
| Data Protection | Retain and dispose of data per policy | A1.2 | A.8.2.3, A.11.2.5 | 164.310(d)(2) | Art. 5(1)(e), 17 | 3.1, 3.2 | 3.12 | PR.DS-3 |
| Vulnerability | Patch critical vulnerabilities within SLA | CC7.1, CC8.1 | A.12.6.1 | 164.308(a)(8) | Art. 32 | 6.3.2, 11.3.2 | 7.3, 7.4 | DE.CM-8, RS.MA-2 |

## Automation Model per Framework
- SOC 2: continuous monitoring of trust services criteria with evidence over a review period.
- ISO 27001: evidence collection per Annex A control for surveillance audits.
- HIPAA: mapping to administrative, physical, and technical safeguards with workforce training and access logs.
- GDPR: data processing records, lawful basis, retention, breach notification, and data-subject rights.
- PCI DSS: scoped assets, access controls, encryption, vulnerability scanning, and segmentation evidence.
- CIS: configuration benchmarks for cloud, endpoints, and SaaS.
- NIST CSF: identify, protect, detect, respond, recover functions tied to controls.

## Cross-Mapping Algorithm
1. Parse each framework into requirement statements.
2. Normalize statements into common control intents.
3. Use keyword, semantic, and manual expert curation to link a common control to one or more framework requirements.
4. Store mappings in a versioned many-to-many table.
5. When evidence passes for a common control, propagate pass/fail to every linked framework control.
