import json
import os
from pathlib import Path

root = Path(os.getenv('COMPLIANCE_PROTOTYPE_ROOT', str(Path(__file__).resolve().parent.parent)))

tenant_id = '00000000-0000-0000-0000-000000000001'
org_id = '00000000-0000-0000-0000-000000000002'

frameworks = [
    {
        'id': '00000000-0000-0000-0000-000000000011',
        'code': 'SOC2',
        'name': 'SOC 2 Trust Services Criteria',
        'version': '2022',
        'sections': [
            {'code': 'CC1.0', 'title': 'Control Environment'},
            {'code': 'CC2.0', 'title': 'Communication and Information'},
            {'code': 'CC2.3', 'title': 'Internal Security Communication'},
            {'code': 'CC3.0', 'title': 'Risk Assessment'},
            {'code': 'CC4.0', 'title': 'Monitoring Activities'},
            {'code': 'CC5.0', 'title': 'Control Activities'},
            {'code': 'CC6.1', 'title': 'Logical Access Security'},
            {'code': 'CC6.2', 'title': 'Access Removal'},
            {'code': 'CC6.3', 'title': 'Access Review and Recertification'},
            {'code': 'CC6.7', 'title': 'Data Encryption'},
            {'code': 'CC7.1', 'title': 'Detection of Security Events'},
            {'code': 'CC7.2', 'title': 'Incident Detection'},
            {'code': 'CC7.3', 'title': 'Security Event Logging and Monitoring'},
            {'code': 'CC7.4', 'title': 'Incident Response Procedures'},
            {'code': 'CC7.5', 'title': 'Incident Response Testing and Improvement'},
            {'code': 'CC8.1', 'title': 'Change Management'},
            {'code': 'CC9.1', 'title': 'Vendor Risk Management'},
            {'code': 'CC9.2', 'title': 'Vendor Monitoring and Review'},
            {'code': 'A1.2', 'title': 'Availability and Backup Safeguards'}
        ]
    },
    {
        'id': '00000000-0000-0000-0000-000000000012',
        'code': 'ISO27001',
        'name': 'ISO 27001',
        'version': '2022',
        'sections': [
            {'code': 'A.5.1', 'title': 'Policies for information security'},
            {'code': 'A.7.2.2', 'title': 'Information security awareness'},
            {'code': 'A.8.1.1', 'title': 'Inventory of assets'},
            {'code': 'A.8.2.3', 'title': 'Handling of assets'},
            {'code': 'A.9.2.6', 'title': 'Removal or adjustment of access rights'},
            {'code': 'A.9.4.2', 'title': 'Secure log-on procedures'},
            {'code': 'A.10.1.1', 'title': 'Policy for use of cryptographic controls'},
            {'code': 'A.11.2.5', 'title': 'Removal of assets'},
            {'code': 'A.12.1.2', 'title': 'Change management'},
            {'code': 'A.12.4.1', 'title': 'Event logging'},
            {'code': 'A.15.1.1', 'title': 'Information security policy for supplier relationships'},
            {'code': 'A.16.1.1', 'title': 'Responsibilities and procedures'},
            {'code': 'A.12.6.1', 'title': 'Management of technical vulnerabilities'}
        ]
    },
    {
        'id': '00000000-0000-0000-0000-000000000013',
        'code': 'HIPAA',
        'name': 'HIPAA Security Rule',
        'version': '2013',
        'sections': [
            {'code': '164.308(a)(1)', 'title': 'Security Management Process'},
            {'code': '164.308(a)(3)(ii)(B)', 'title': 'Workforce clearance procedures'},
            {'code': '164.308(a)(5)', 'title': 'Security awareness and training'},
            {'code': '164.308(a)(6)', 'title': 'Security incident procedures'},
            {'code': '164.308(a)(8)', 'title': 'Evaluation'},
            {'code': '164.308(b)(1)', 'title': 'Business associate contracts and other arrangements'},
            {'code': '164.310(d)(1)', 'title': 'Device and media controls'},
            {'code': '164.310(d)(2)', 'title': 'Disposal and media reuse procedures'},
            {'code': '164.312(a)(1)', 'title': 'Access control'},
            {'code': '164.312(b)', 'title': 'Audit controls'},
            {'code': '164.312(d)', 'title': 'Person or entity authentication'},
            {'code': '164.312(e)(1)', 'title': 'Transmission security'}
        ]
    },
    {
        'id': '00000000-0000-0000-0000-000000000014',
        'code': 'GDPR',
        'name': 'General Data Protection Regulation',
        'version': '2016',
        'sections': [
            {'code': 'Art.5', 'title': 'Principles relating to processing'},
            {'code': 'Art.25', 'title': 'Data protection by design and by default'},
            {'code': 'Art.30', 'title': 'Records of processing activities'},
            {'code': 'Art.32', 'title': 'Security of processing'},
            {'code': 'Art.33', 'title': 'Notification of personal data breach'},
            {'code': 'Art.28', 'title': 'Processor'}
        ]
    },
    {
        'id': '00000000-0000-0000-0000-000000000015',
        'code': 'PCI DSS',
        'name': 'Payment Card Industry Data Security Standard',
        'version': '4.0',
        'sections': [
            {'code': '3.1', 'title': 'Data retention and disposal'},
            {'code': '3.4', 'title': 'PAN storage protection'},
            {'code': '4.1', 'title': 'Strong cryptography for transmission'},
            {'code': '6.3.2', 'title': 'Software security patches'},
            {'code': '6.5.4', 'title': 'Insecure direct object references'},
            {'code': '8.1.4', 'title': 'Remove inactive accounts'},
            {'code': '8.3', 'title': 'Multi-factor authentication'},
            {'code': '9.4.1', 'title': 'Physical access controls for devices'},
            {'code': '10.2', 'title': 'Audit trail entries'},
            {'code': '11.3.2', 'title': 'Vulnerability scanning'},
            {'code': '12.6.1', 'title': 'Security awareness education'},
            {'code': '12.8.1', 'title': 'Maintain inventory of service providers'},
            {'code': '12.10.1', 'title': 'Incident response plan'}
        ]
    },
    {
        'id': '00000000-0000-0000-0000-000000000016',
        'code': 'NIST CSF',
        'name': 'NIST Cybersecurity Framework',
        'version': '1.1',
        'sections': [
            {'code': 'PR.AC-1', 'title': 'Identities and credentials are managed for authorized devices and users'},
            {'code': 'PR.DS-1', 'title': 'Data-at-rest is protected'},
            {'code': 'PR.DS-2', 'title': 'Data-in-transit is protected'},
            {'code': 'PR.AC-4', 'title': 'Access permissions and authorizations are managed'},
            {'code': 'PR.IP-3', 'title': 'Configuration change control processes are in place'},
            {'code': 'PR.AT-1', 'title': 'All users are informed and trained'},
            {'code': 'DE.AE-3', 'title': 'Event data are collected and correlated from multiple sources'},
            {'code': 'DE.CM-8', 'title': 'Vulnerability scans are performed'},
            {'code': 'ID.SC-1', 'title': 'Supply chain risk management processes are identified'},
            {'code': 'ID.AM-1', 'title': 'Physical devices and systems are inventoried'},
            {'code': 'RS.RP-1', 'title': 'Response plan is executed during or after an incident'},
            {'code': 'PR.DS-3', 'title': 'Assets are formally managed throughout removal and transfers'}
        ]
    },
    {
        'id': '00000000-0000-0000-0000-000000000017',
        'code': 'CIS',
        'name': 'CIS Critical Security Controls',
        'version': '8.0',
        'sections': [
            {'code': '1.1', 'title': 'Establish and maintain detailed enterprise asset inventory'},
            {'code': '3.11', 'title': 'Encrypt sensitive data at rest'},
            {'code': '3.12', 'title': 'Encrypt sensitive data in transit'},
            {'code': '6.3', 'title': 'Require multifactor authentication'},
            {'code': '6.4', 'title': 'Manage access control and deprovisioning'},
            {'code': '7.3', 'title': 'Perform and maintain secure configuration process'},
            {'code': '7.4', 'title': 'Perform automated vulnerability management'},
            {'code': '8.2', 'title': 'Collect audit logs'},
            {'code': '14.1', 'title': 'Establish and maintain a security awareness program'},
            {'code': '15.1', 'title': 'Establish and maintain an inventory of service providers'},
            {'code': '17.1', 'title': 'Design and maintain an incident response process'}
        ]
    }
]

common_controls = [
    {
        'id': 'cc-mfa-001',
        'code': 'CC-MFA-001',
        'domain': 'Identity and Access Management',
        'statement': 'Enforce multi-factor authentication on all workforce accounts',
        'expected_evidence': 'Identity provider report showing MFA enabled per user',
        'owner': 'alice@example.com'
    },
    {
        'id': 'cc-encrypt-002',
        'code': 'CC-ENC-002',
        'domain': 'Data Protection',
        'statement': 'Encrypt data at rest and in transit',
        'expected_evidence': 'Cloud storage and volume encryption configuration screenshots',
        'owner': 'bob@example.com'
    },
    {
        'id': 'cc-offboard-003',
        'code': 'CC-OFFB-003',
        'domain': 'Identity and Access Management',
        'statement': 'Remove access for terminated employees within 24 hours',
        'expected_evidence': 'Access review and deprovisioning logs',
        'owner': 'carol@example.com'
    },
    {
        'id': 'cc-code-review-004',
        'code': 'CC-CR-004',
        'domain': 'Change Management',
        'statement': 'Require code review and approved pull requests before production changes',
        'expected_evidence': 'Repository branch protection and pull request screenshots',
        'owner': 'dave@example.com'
    },
    {
        'id': 'cc-training-005',
        'code': 'CC-TRAIN-005',
        'domain': 'Security Awareness',
        'statement': 'Deliver annual security awareness training and track completion',
        'expected_evidence': 'Training completion report',
        'owner': 'eve@example.com'
    },
    {
        'id': 'cc-logs-006',
        'code': 'CC-LOG-006',
        'domain': 'Monitoring',
        'statement': 'Collect and protect audit logs for critical systems',
        'expected_evidence': 'Logging configuration and retention policy',
        'owner': 'bob@example.com'
    },
    {
        'id': 'cc-vuln-007',
        'code': 'CC-VULN-007',
        'domain': 'Vulnerability Management',
        'statement': 'Patch critical vulnerabilities within 7 days',
        'expected_evidence': 'Vulnerability scan report and patch timeline',
        'owner': 'frank@example.com'
    },
    {
        'id': 'cc-vendor-008',
        'code': 'CC-VEND-008',
        'domain': 'Vendor Management',
        'statement': 'Assess and monitor security posture of third-party vendors',
        'expected_evidence': 'Vendor security questionnaire and review',
        'owner': 'grace@example.com'
    },
    {
        'id': 'cc-asset-009',
        'code': 'CC-ASSET-009',
        'domain': 'Asset Management',
        'statement': 'Maintain an inventory of endpoints and cloud assets',
        'expected_evidence': 'Asset inventory export',
        'owner': 'alice@example.com'
    },
    {
        'id': 'cc-incident-010',
        'code': 'CC-INC-010',
        'domain': 'Incident Response',
        'statement': 'Document and exercise an incident response plan annually',
        'expected_evidence': 'Incident response plan and tabletop exercise notes',
        'owner': 'heidi@example.com'
    },
    {
        'id': 'cc-access-review-011',
        'code': 'CC-AR-011',
        'domain': 'Identity and Access Management',
        'statement': 'Perform quarterly access reviews for all systems',
        'expected_evidence': 'Completed access review campaign records',
        'owner': 'carol@example.com'
    },
    {
        'id': 'cc-backup-012',
        'code': 'CC-BKP-012',
        'domain': 'Business Continuity',
        'statement': 'Back up critical data and test recovery procedures',
        'expected_evidence': 'Backup configuration and restore test logs',
        'owner': 'bob@example.com'
    }
]

mappings = [
    {'common_control_id': 'cc-mfa-001', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC6.1'},
        {'framework_code': 'SOC2', 'section_code': 'CC6.2'},
        {'framework_code': 'ISO27001', 'section_code': 'A.9.4.2'},
        {'framework_code': 'HIPAA', 'section_code': '164.312(d)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.32'},
        {'framework_code': 'PCI DSS', 'section_code': '8.3'},
        {'framework_code': 'NIST CSF', 'section_code': 'PR.AC-1'},
        {'framework_code': 'CIS', 'section_code': '6.3'}
    ]},
    {'common_control_id': 'cc-encrypt-002', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC6.1'},
        {'framework_code': 'SOC2', 'section_code': 'CC6.7'},
        {'framework_code': 'ISO27001', 'section_code': 'A.10.1.1'},
        {'framework_code': 'HIPAA', 'section_code': '164.312(a)(1)'},
        {'framework_code': 'HIPAA', 'section_code': '164.312(e)(1)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.32'},
        {'framework_code': 'PCI DSS', 'section_code': '3.4'},
        {'framework_code': 'PCI DSS', 'section_code': '4.1'},
        {'framework_code': 'NIST CSF', 'section_code': 'PR.DS-1'},
        {'framework_code': 'NIST CSF', 'section_code': 'PR.DS-2'},
        {'framework_code': 'CIS', 'section_code': '3.11'}
    ]},
    {'common_control_id': 'cc-offboard-003', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC6.2'},
        {'framework_code': 'SOC2', 'section_code': 'CC6.3'},
        {'framework_code': 'ISO27001', 'section_code': 'A.9.2.6'},
        {'framework_code': 'HIPAA', 'section_code': '164.308(a)(3)(ii)(B)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.5'},
        {'framework_code': 'PCI DSS', 'section_code': '8.1.4'},
        {'framework_code': 'NIST CSF', 'section_code': 'PR.AC-4'},
        {'framework_code': 'CIS', 'section_code': '6.4'}
    ]},
    {'common_control_id': 'cc-code-review-004', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC8.1'},
        {'framework_code': 'ISO27001', 'section_code': 'A.12.1.2'},
        {'framework_code': 'HIPAA', 'section_code': '164.308(a)(8)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.32'},
        {'framework_code': 'PCI DSS', 'section_code': '6.3.2'},
        {'framework_code': 'PCI DSS', 'section_code': '6.5.4'},
        {'framework_code': 'NIST CSF', 'section_code': 'PR.IP-3'},
        {'framework_code': 'CIS', 'section_code': '7.3'}
    ]},
    {'common_control_id': 'cc-training-005', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC2.3'},
        {'framework_code': 'SOC2', 'section_code': 'CC7.1'},
        {'framework_code': 'ISO27001', 'section_code': 'A.7.2.2'},
        {'framework_code': 'HIPAA', 'section_code': '164.308(a)(5)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.32'},
        {'framework_code': 'PCI DSS', 'section_code': '12.6.1'},
        {'framework_code': 'NIST CSF', 'section_code': 'PR.AT-1'},
        {'framework_code': 'CIS', 'section_code': '14.1'}
    ]},
    {'common_control_id': 'cc-logs-006', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC7.2'},
        {'framework_code': 'SOC2', 'section_code': 'CC7.3'},
        {'framework_code': 'ISO27001', 'section_code': 'A.12.4.1'},
        {'framework_code': 'HIPAA', 'section_code': '164.312(b)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.32'},
        {'framework_code': 'PCI DSS', 'section_code': '10.2'},
        {'framework_code': 'NIST CSF', 'section_code': 'DE.AE-3'},
        {'framework_code': 'CIS', 'section_code': '8.2'}
    ]},
    {'common_control_id': 'cc-vuln-007', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC7.1'},
        {'framework_code': 'SOC2', 'section_code': 'CC8.1'},
        {'framework_code': 'ISO27001', 'section_code': 'A.12.6.1'},
        {'framework_code': 'HIPAA', 'section_code': '164.308(a)(8)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.32'},
        {'framework_code': 'PCI DSS', 'section_code': '6.3.2'},
        {'framework_code': 'PCI DSS', 'section_code': '11.3.2'},
        {'framework_code': 'NIST CSF', 'section_code': 'DE.CM-8'},
        {'framework_code': 'CIS', 'section_code': '7.4'}
    ]},
    {'common_control_id': 'cc-vendor-008', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC9.1'},
        {'framework_code': 'SOC2', 'section_code': 'CC9.2'},
        {'framework_code': 'ISO27001', 'section_code': 'A.15.1.1'},
        {'framework_code': 'HIPAA', 'section_code': '164.308(b)(1)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.28'},
        {'framework_code': 'PCI DSS', 'section_code': '12.8.1'},
        {'framework_code': 'NIST CSF', 'section_code': 'ID.SC-1'},
        {'framework_code': 'CIS', 'section_code': '15.1'}
    ]},
    {'common_control_id': 'cc-asset-009', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC6.1'},
        {'framework_code': 'ISO27001', 'section_code': 'A.8.1.1'},
        {'framework_code': 'HIPAA', 'section_code': '164.310(d)(1)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.30'},
        {'framework_code': 'PCI DSS', 'section_code': '9.4.1'},
        {'framework_code': 'NIST CSF', 'section_code': 'ID.AM-1'},
        {'framework_code': 'CIS', 'section_code': '1.1'}
    ]},
    {'common_control_id': 'cc-incident-010', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC7.4'},
        {'framework_code': 'SOC2', 'section_code': 'CC7.5'},
        {'framework_code': 'ISO27001', 'section_code': 'A.16.1.1'},
        {'framework_code': 'HIPAA', 'section_code': '164.308(a)(6)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.33'},
        {'framework_code': 'PCI DSS', 'section_code': '12.10.1'},
        {'framework_code': 'NIST CSF', 'section_code': 'RS.RP-1'},
        {'framework_code': 'CIS', 'section_code': '17.1'}
    ]},
    {'common_control_id': 'cc-access-review-011', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'CC6.2'},
        {'framework_code': 'SOC2', 'section_code': 'CC6.3'},
        {'framework_code': 'ISO27001', 'section_code': 'A.9.2.6'},
        {'framework_code': 'HIPAA', 'section_code': '164.308(a)(3)(ii)(B)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.32'},
        {'framework_code': 'PCI DSS', 'section_code': '8.1.4'},
        {'framework_code': 'NIST CSF', 'section_code': 'PR.AC-4'},
        {'framework_code': 'CIS', 'section_code': '6.4'}
    ]},
    {'common_control_id': 'cc-backup-012', 'mappings': [
        {'framework_code': 'SOC2', 'section_code': 'A1.2'},
        {'framework_code': 'ISO27001', 'section_code': 'A.8.2.3'},
        {'framework_code': 'ISO27001', 'section_code': 'A.11.2.5'},
        {'framework_code': 'HIPAA', 'section_code': '164.310(d)(2)'},
        {'framework_code': 'GDPR', 'section_code': 'Art.32'},
        {'framework_code': 'PCI DSS', 'section_code': '3.1'},
        {'framework_code': 'NIST CSF', 'section_code': 'PR.DS-3'},
        {'framework_code': 'CIS', 'section_code': '3.12'}
    ]}
]

resource_types = [
    {
        'id': 'rt-user-account',
        'name': 'UserAccount',
        'schema': {
            'email': 'string',
            'active': 'boolean',
            'mfa_enabled': 'boolean',
            'groups': 'array<string>',
            'department': 'string',
            'employment_status': 'string',
            'last_sign_in': 'timestamp'
        }
    },
    {
        'id': 'rt-computer',
        'name': 'Computer',
        'schema': {
            'serial': 'string',
            'os': 'string',
            'os_version': 'string',
            'disk_encrypted': 'boolean',
            'owner_email': 'string',
            'last_seen': 'timestamp',
            'agent_version': 'string'
        }
    },
    {
        'id': 'rt-vulnerability',
        'name': 'Vulnerability',
        'schema': {
            'cve_id': 'string',
            'severity': 'string',
            'asset_id': 'string',
            'status': 'string',
            'first_seen': 'timestamp',
            'resolved_at': 'timestamp'
        }
    },
    {
        'id': 'rt-training-record',
        'name': 'TrainingRecord',
        'schema': {
            'user_email': 'string',
            'course_name': 'string',
            'completed_at': 'timestamp',
            'score': 'number',
            'valid_until': 'timestamp'
        }
    }
]

resources = [
    {
        'id': 'res-user-001',
        'integration_id': 'int-okta-001',
        'resource_type': 'UserAccount',
        'external_id': 'alice@example.com',
        'data': {
            'email': 'alice@example.com',
            'active': True,
            'mfa_enabled': True,
            'groups': ['engineering', 'admins'],
            'department': 'engineering',
            'employment_status': 'active',
            'last_sign_in': '2024-06-15T08:30:00Z'
        },
        'collected_at': '2024-06-20T12:00:00Z'
    },
    {
        'id': 'res-user-002',
        'integration_id': 'int-okta-001',
        'resource_type': 'UserAccount',
        'external_id': 'bob@example.com',
        'data': {
            'email': 'bob@example.com',
            'active': True,
            'mfa_enabled': False,
            'groups': ['finance'],
            'department': 'finance',
            'employment_status': 'active',
            'last_sign_in': '2024-06-18T09:00:00Z'
        },
        'collected_at': '2024-06-20T12:00:00Z'
    },
    {
        'id': 'res-comp-001',
        'integration_id': 'int-jamf-001',
        'resource_type': 'Computer',
        'external_id': 'C02X1234',
        'data': {
            'serial': 'C02X1234',
            'os': 'macOS',
            'os_version': '14.5',
            'disk_encrypted': True,
            'owner_email': 'alice@example.com',
            'last_seen': '2024-06-20T11:00:00Z',
            'agent_version': '10.5.0'
        },
        'collected_at': '2024-06-20T12:00:00Z'
    },
    {
        'id': 'res-vuln-001',
        'integration_id': 'int-crowdstrike-001',
        'resource_type': 'Vulnerability',
        'external_id': 'CVE-2024-1234',
        'data': {
            'cve_id': 'CVE-2024-1234',
            'severity': 'critical',
            'asset_id': 'i-0abcd1234',
            'status': 'open',
            'first_seen': '2024-06-01T00:00:00Z',
            'resolved_at': None
        },
        'collected_at': '2024-06-20T12:00:00Z'
    },
    {
        'id': 'res-train-001',
        'integration_id': 'int-knowbe4-001',
        'resource_type': 'TrainingRecord',
        'external_id': 'alice-security-2024',
        'data': {
            'user_email': 'alice@example.com',
            'course_name': 'Security Awareness 2024',
            'completed_at': '2024-01-15T10:00:00Z',
            'score': 92,
            'valid_until': '2025-01-15T00:00:00Z'
        },
        'collected_at': '2024-06-20T12:00:00Z'
    }
]

evidence = [
    {
        'id': 'ev-mfa-001',
        'test_id': 'test-mfa-001',
        'resource_id': 'res-user-001',
        'status': 'OK',
        'reason': 'MFA is enabled',
        'evidence_type': 'api_response',
        'description': 'Okta user report showing MFA enabled for alice@example.com',
        'collected_at': '2024-06-20T12:00:00Z'
    },
    {
        'id': 'ev-mfa-002',
        'test_id': 'test-mfa-001',
        'resource_id': 'res-user-002',
        'status': 'NEEDS_ATTENTION',
        'reason': 'MFA is not enabled',
        'evidence_type': 'api_response',
        'description': 'Okta user report showing MFA disabled for bob@example.com',
        'collected_at': '2024-06-20T12:00:00Z'
    },
    {
        'id': 'ev-encrypt-001',
        'test_id': 'test-encrypt-001',
        'resource_id': 'res-comp-001',
        'status': 'OK',
        'reason': 'Disk encryption is enabled',
        'evidence_type': 'snapshot',
        'description': 'Jamf device record shows FileVault enabled',
        'collected_at': '2024-06-20T12:00:00Z'
    },
    {
        'id': 'ev-vuln-001',
        'test_id': 'test-vuln-001',
        'resource_id': 'res-vuln-001',
        'status': 'NEEDS_ATTENTION',
        'reason': 'Critical vulnerability open beyond SLA',
        'evidence_type': 'api_response',
        'description': 'CrowdStrike vulnerability scan shows CVE-2024-1234 open 19 days',
        'collected_at': '2024-06-20T12:00:00Z'
    },
    {
        'id': 'ev-train-001',
        'test_id': 'test-training-001',
        'resource_id': 'res-train-001',
        'status': 'OK',
        'reason': 'Training completed within validity window',
        'evidence_type': 'api_response',
        'description': 'KnowBe4 training record for alice@example.com',
        'collected_at': '2024-06-20T12:00:00Z'
    }
]

control_test_links = [
    {'common_control_id': 'cc-mfa-001', 'test_id': 'test-mfa-001'},
    {'common_control_id': 'cc-encrypt-002', 'test_id': 'test-encrypt-001'},
    {'common_control_id': 'cc-vuln-007', 'test_id': 'test-vuln-001'},
    {'common_control_id': 'cc-training-005', 'test_id': 'test-training-001'},
]

tenant = {
    'id': tenant_id,
    'name': 'Acme Demo Tenant',
    'region': 'us',
    'organization': {
        'id': org_id,
        'name': 'Acme Corporation'
    },
    'users': [
        {'id': 'usr-001', 'email': 'alice@example.com', 'full_name': 'Alice Admin', 'role': 'admin'},
        {'id': 'usr-002', 'email': 'bob@example.com', 'full_name': 'Bob Builder', 'role': 'compliance_manager'},
        {'id': 'usr-003', 'email': 'carol@example.com', 'full_name': 'Carol Compliance', 'role': 'control_owner'},
        {'id': 'usr-004', 'email': 'dave@example.com', 'full_name': 'Dave Dev', 'role': 'control_owner'},
        {'id': 'usr-005', 'email': 'eve@example.com', 'full_name': 'Eve Engineer', 'role': 'read_only'},
        {'id': 'usr-006', 'email': 'frank@example.com', 'full_name': 'Frank Fixer', 'role': 'control_owner'},
        {'id': 'usr-007', 'email': 'grace@example.com', 'full_name': 'Grace Governance', 'role': 'control_owner'},
        {'id': 'usr-008', 'email': 'heidi@example.com', 'full_name': 'Heidi Incident', 'role': 'auditor'}
    ]
}

catalog = [
    {'id': 'conn-aws', 'name': 'AWS', 'category': 'Cloud Provider', 'auth_types': ['cross_account_role', 'access_key'], 'resource_types': ['UserAccount', 'Computer', 'StorageBucket', 'ComputeInstance']},
    {'id': 'conn-azure', 'name': 'Azure', 'category': 'Cloud Provider', 'auth_types': ['service_principal'], 'resource_types': ['UserAccount', 'StorageAccount', 'VirtualMachine']},
    {'id': 'conn-gcp', 'name': 'GCP', 'category': 'Cloud Provider', 'auth_types': ['service_account'], 'resource_types': ['UserAccount', 'Bucket', 'ComputeInstance']},
    {'id': 'conn-okta', 'name': 'Okta', 'category': 'Identity Provider', 'auth_types': ['oauth_private_key', 'api_token'], 'resource_types': ['UserAccount', 'Group', 'Application']},
    {'id': 'conn-google-workspace', 'name': 'Google Workspace', 'category': 'Identity Provider', 'auth_types': ['service_account'], 'resource_types': ['UserAccount', 'Group', 'Device']},
    {'id': 'conn-azure-ad', 'name': 'Azure AD', 'category': 'Identity Provider', 'auth_types': ['service_principal'], 'resource_types': ['UserAccount', 'Group']},
    {'id': 'conn-github', 'name': 'GitHub', 'category': 'Code Repository', 'auth_types': ['github_app', 'oauth'], 'resource_types': ['Repository', 'PullRequest', 'OrganizationMember']},
    {'id': 'conn-gitlab', 'name': 'GitLab', 'category': 'Code Repository', 'auth_types': ['oauth', 'personal_token'], 'resource_types': ['Repository', 'MergeRequest']},
    {'id': 'conn-jira', 'name': 'Jira', 'category': 'Ticketing', 'auth_types': ['api_token', 'oauth'], 'resource_types': ['Ticket', 'Project']},
    {'id': 'conn-servicenow', 'name': 'ServiceNow', 'category': 'Ticketing', 'auth_types': ['oauth', 'basic'], 'resource_types': ['Ticket', 'ChangeRequest']},
    {'id': 'conn-slack', 'name': 'Slack', 'category': 'Communication', 'auth_types': ['oauth'], 'resource_types': ['WorkspaceUser', 'Channel']},
    {'id': 'conn-jamf', 'name': 'Jamf', 'category': 'MDM', 'auth_types': ['api_token'], 'resource_types': ['Computer', 'MobileDevice']},
    {'id': 'conn-intune', 'name': 'Intune', 'category': 'MDM', 'auth_types': ['service_principal'], 'resource_types': ['Computer', 'MobileDevice']},
    {'id': 'conn-crowdstrike', 'name': 'CrowdStrike', 'category': 'Endpoint Security', 'auth_types': ['api_token'], 'resource_types': ['Computer', 'Vulnerability']},
    {'id': 'conn-sentinelone', 'name': 'SentinelOne', 'category': 'Endpoint Security', 'auth_types': ['api_token'], 'resource_types': ['Computer', 'Vulnerability']},
    {'id': 'conn-orca', 'name': 'Orca Security', 'category': 'Vulnerability Management', 'auth_types': ['api_token'], 'resource_types': ['Vulnerability', 'CloudAsset']},
    {'id': 'conn-knowbe4', 'name': 'KnowBe4', 'category': 'Training', 'auth_types': ['api_token'], 'resource_types': ['TrainingRecord']},
    {'id': 'conn-workday', 'name': 'Workday', 'category': 'HRIS', 'auth_types': ['oauth'], 'resource_types': ['Employee', 'Department']},
    {'id': 'conn-bamboohr', 'name': 'BambooHR', 'category': 'HRIS', 'auth_types': ['api_token'], 'resource_types': ['Employee']},
    {'id': 'conn-custom', 'name': 'Custom Integration', 'category': 'Custom', 'auth_types': ['oauth', 'api_token', 'webhook'], 'resource_types': ['CustomResource']}
]

for name, data in [
    ('data/frameworks.json', frameworks),
    ('data/common-controls.json', common_controls),
    ('data/control-mappings.json', mappings),
    ('data/control-test-links.json', control_test_links),
    ('data/resource-types.json', resource_types),
    ('data/sample-resources.json', resources),
    ('data/sample-evidence.json', evidence),
    ('data/sample-tenant.json', tenant),
    ('data/integration-catalog.json', catalog)
]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')

print('Seed data written to data/')
