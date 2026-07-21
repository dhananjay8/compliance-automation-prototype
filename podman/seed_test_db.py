import json
import os
import uuid
import psycopg2
from pathlib import Path
from datetime import datetime, timezone

NS = uuid.UUID('00000000-0000-0000-0000-000000000000')


def uid(name):
    return str(uuid.uuid5(NS, name))


def load_json(path):
    with open(path) as f:
        return json.load(f)


def parse_time(s):
    if s is None:
        return None
    if isinstance(s, str):
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    return s


repo = Path('/repo')
if not repo.exists():
    repo = Path(__file__).resolve().parent.parent

conn = psycopg2.connect(
    host=os.getenv('PGHOST', 'localhost'),
    port=os.getenv('PGPORT', '5432'),
    dbname=os.getenv('PGDATABASE', 'compliance_test'),
    user=os.getenv('PGUSER', 'test'),
    password=os.getenv('PGPASSWORD', 'testpass')
)
cur = conn.cursor()

tenant = load_json(repo / 'data/sample-tenant.json')
tenant_id = tenant['id']
org_id = tenant['organization']['id']

cur.execute('INSERT INTO tenant (id, name, region) VALUES (%s, %s, %s)',
            (tenant_id, tenant['name'], tenant['region']))
cur.execute('INSERT INTO organization (id, tenant_id, name) VALUES (%s, %s, %s)',
            (org_id, tenant_id, tenant['organization']['name']))

user_map = {}
for u in tenant['users']:
    cur.execute('INSERT INTO "user" (id, tenant_id, organization_id, email, full_name, role) VALUES (%s, %s, %s, %s, %s, %s)',
                (u['id'], tenant_id, org_id, u['email'], u['full_name'], u['role']))
    user_map[u['email']] = u['id']

frameworks = load_json(repo / 'data/frameworks.json')
section_map = {}
framework_map = {}
for fw in frameworks:
    fw_id = fw['id']
    framework_map[fw['code']] = fw_id
    cur.execute('INSERT INTO framework (id, tenant_id, code, name, version) VALUES (%s, %s, %s, %s, %s)',
                (fw_id, tenant_id, fw['code'], fw['name'], fw.get('version')))
    for s in fw['sections']:
        sec_id = uid(f"{fw_id}:{s['code']}")
        section_map[(fw_id, s['code'])] = sec_id
        cur.execute('INSERT INTO section (id, framework_id, code, title, description) VALUES (%s, %s, %s, %s, %s)',
                    (sec_id, fw_id, s['code'], s['title'], s.get('description')))

common_controls = load_json(repo / 'data/common-controls.json')
control_map = {}
for cc in common_controls:
    owner_id = user_map.get(cc.get('owner')) if cc.get('owner') else None
    cur.execute('INSERT INTO common_control (id, tenant_id, code, domain, statement, owner_id, expected_evidence) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (cc['id'], tenant_id, cc['code'], cc['domain'], cc['statement'], owner_id, cc.get('expected_evidence')))
    control_map[cc['id']] = cc

mappings = load_json(repo / 'data/control-mappings.json')
for item in mappings:
    cc_id = item['common_control_id']
    cc = control_map.get(cc_id, {})
    for m in item['mappings']:
        fw_id = framework_map.get(m['framework_code'])
        if not fw_id:
            continue
        sec_id = section_map.get((fw_id, m['section_code']))
        cur.execute('INSERT INTO framework_control (id, tenant_id, framework_id, section_id, common_control_id, requirement_text) VALUES (%s, %s, %s, %s, %s, %s)',
                    (uid(f"{fw_id}:{m['section_code']}:{cc_id}"), tenant_id, fw_id, sec_id, cc_id, cc.get('statement', '')))

resource_types = load_json(repo / 'data/resource-types.json')
rt_map = {}
for rt in resource_types:
    rt_id = rt['id']
    rt_map[rt['name']] = rt_id
    cur.execute('INSERT INTO resource_type (id, tenant_id, name, schema) VALUES (%s, %s, %s, %s)',
                (rt_id, tenant_id, rt['name'], json.dumps(rt['schema'])))

resources = load_json(repo / 'data/sample-resources.json')
integration_map = {}
resource_id_map = {}
for r in resources:
    int_str = r['integration_id']
    if int_str not in integration_map:
        int_id = uid(int_str)
        integration_map[int_str] = int_id
        connector = int_str.split('-')[1] if '-' in int_str else 'unknown'
        name = f"{connector.title()} Test Integration"
        cur.execute('INSERT INTO integration (id, tenant_id, connector, name, config, credentials, status, last_sync_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                    (int_id, tenant_id, connector, name, '{}', '{}', 'connected', parse_time(r['collected_at'])))
    res_id = uid(r['id'])
    resource_id_map[r['id']] = res_id
    rt_id = rt_map.get(r['resource_type'])
    external_id = r.get('external_id', r['id'])
    cur.execute('INSERT INTO resource (id, tenant_id, integration_id, resource_type_id, external_id, data, collected_at, hash) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                (res_id, tenant_id, integration_map[int_str], rt_id, external_id, json.dumps(r['data']), parse_time(r['collected_at']), ''))

test_rules = {
    'test-mfa-001': {'resource_type': 'UserAccount', 'rule': {'field': 'mfa_enabled', 'operator': 'eq', 'value': True}},
    'test-encrypt-001': {'resource_type': 'Computer', 'rule': {'field': 'disk_encrypted', 'operator': 'eq', 'value': True}},
    'test-vuln-001': {'resource_type': 'Vulnerability', 'rule': {'field': 'status', 'operator': 'eq', 'value': 'resolved'}},
    'test-training-001': {'resource_type': 'TrainingRecord', 'rule': {'field': 'completed_at', 'operator': 'exists'}}
}

evidence = load_json(repo / 'data/sample-evidence.json')
test_run_map = {}
for ev in evidence:
    t_str = ev['test_id']
    t_id = uid(t_str)
    if t_id not in test_run_map:
        cfg = test_rules.get(t_str, {})
        rt_name = cfg.get('resource_type', 'UserAccount')
        rt_id = rt_map.get(rt_name)
        cur.execute('INSERT INTO test (id, tenant_id, name, resource_type, rule, schedule) VALUES (%s, %s, %s, %s, %s, %s)',
                    (t_id, tenant_id, t_str, rt_name, json.dumps(cfg.get('rule', {})), '0 * * * *'))
        run_id = uid(f"{t_str}:run1")
        test_run_map[t_id] = run_id
        cur.execute('INSERT INTO test_run (id, tenant_id, test_id, status, started_at, completed_at) VALUES (%s, %s, %s, %s, %s, %s)',
                    (run_id, tenant_id, t_id, 'completed', parse_time(ev['collected_at']), parse_time(ev['collected_at'])))
    res_id = resource_id_map.get(ev['resource_id'])
    tr_id = uid(f"{ev['id']}:result")
    cur.execute('INSERT INTO test_result (id, tenant_id, test_run_id, resource_id, status, reason, evaluated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (tr_id, tenant_id, test_run_map[t_id], res_id, ev['status'], ev['reason'], parse_time(ev['collected_at'])))
    cur.execute('INSERT INTO evidence (id, tenant_id, test_result_id, evidence_type, description, collected_at) VALUES (%s, %s, %s, %s, %s, %s)',
                (uid(ev['id']), tenant_id, tr_id, ev['evidence_type'], ev['description'], parse_time(ev['collected_at'])))

conn.commit()
cur.close()
conn.close()
print('Seed loaded successfully')
