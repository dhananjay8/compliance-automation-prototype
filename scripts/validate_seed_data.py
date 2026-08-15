import argparse
import json
from pathlib import Path
from typing import Any


VALID_EVIDENCE_STATUSES = {
    "OK",
    "NEEDS_ATTENTION",
    "INVALID",
    "NOT_APPLICABLE",
    "DEACTIVATED",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run validation for compliance prototype seed data"
    )
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Repository root path (default: inferred from script location)",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Fail on warnings as well as errors",
    )
    args = parser.parse_args()

    root = Path(args.root)
    data_dir = root / "data"

    required_files = [
        "frameworks.json",
        "common-controls.json",
        "control-mappings.json",
        "control-test-links.json",
        "resource-types.json",
        "sample-resources.json",
        "sample-evidence.json",
        "sample-tenant.json",
        "integration-catalog.json",
    ]

    errors: list[str] = []
    warnings: list[str] = []

    for filename in required_files:
        if not (data_dir / filename).exists():
            errors.append(f"Missing required file: data/{filename}")

    if errors:
        print("Seed data validation failed:")
        for issue in errors:
            print(f"  ERROR: {issue}")
        return 1

    frameworks = load_json(data_dir / "frameworks.json")
    controls = load_json(data_dir / "common-controls.json")
    mappings = load_json(data_dir / "control-mappings.json")
    control_test_links = load_json(data_dir / "control-test-links.json")
    resource_types = load_json(data_dir / "resource-types.json")
    resources = load_json(data_dir / "sample-resources.json")
    evidence = load_json(data_dir / "sample-evidence.json")
    tenant = load_json(data_dir / "sample-tenant.json")

    framework_codes: dict[str, set[str]] = {}
    seen_framework_codes: set[str] = set()
    for fw in frameworks:
        code = fw.get("code")
        if not code:
            errors.append("Framework missing code")
            continue
        if code in seen_framework_codes:
            errors.append(f"Duplicate framework code: {code}")
        seen_framework_codes.add(code)

        section_codes: set[str] = set()
        for section in fw.get("sections", []):
            sec_code = section.get("code")
            if not sec_code:
                errors.append(f"Framework {code} has section without code")
                continue
            if sec_code in section_codes:
                errors.append(f"Framework {code} has duplicate section code: {sec_code}")
            section_codes.add(sec_code)
        framework_codes[code] = section_codes

    control_ids: set[str] = set()
    for control in controls:
        cid = control.get("id")
        if not cid:
            errors.append("Common control missing id")
            continue
        if cid in control_ids:
            errors.append(f"Duplicate common control id: {cid}")
        control_ids.add(cid)

    user_emails = {u.get("email") for u in tenant.get("users", []) if u.get("email")}
    for control in controls:
        owner = control.get("owner")
        if owner and owner not in user_emails:
            errors.append(
                f"Control {control.get('id')} owner {owner} not found in tenant users"
            )

    for entry in mappings:
        cc_id = entry.get("common_control_id")
        if cc_id not in control_ids:
            errors.append(f"Mapping references unknown common_control_id: {cc_id}")
        for mapping in entry.get("mappings", []):
            fw_code = mapping.get("framework_code")
            sec_code = mapping.get("section_code")
            if fw_code not in framework_codes:
                errors.append(
                    f"Mapping {cc_id} references unknown framework_code: {fw_code}"
                )
                continue
            if sec_code not in framework_codes[fw_code]:
                errors.append(
                    f"Mapping {cc_id} references missing section {fw_code}:{sec_code}"
                )

    resource_type_names = {r.get("name") for r in resource_types if r.get("name")}
    resource_ids = set()
    for resource in resources:
        rid = resource.get("id")
        rtype = resource.get("resource_type")
        if not rid:
            errors.append("Resource missing id")
            continue
        if rid in resource_ids:
            errors.append(f"Duplicate resource id: {rid}")
        resource_ids.add(rid)

        if rtype not in resource_type_names:
            errors.append(f"Resource {rid} uses unknown resource_type: {rtype}")

    for item in evidence:
        evid = item.get("id")
        resource_id = item.get("resource_id")
        status = item.get("status")

        if resource_id not in resource_ids:
            errors.append(
                f"Evidence {evid} references unknown resource_id: {resource_id}"
            )

        if status not in VALID_EVIDENCE_STATUSES:
            errors.append(f"Evidence {evid} has invalid status: {status}")

    test_ids = set()
    for item in evidence:
        test_id = item.get("test_id")
        if test_id:
            test_ids.add(test_id)

    for link in control_test_links:
        cc_id = link.get("common_control_id")
        test_id = link.get("test_id")
        if cc_id not in control_ids:
            errors.append(f"Control-test link references unknown common control: {cc_id}")
        if test_id not in test_ids:
            errors.append(f"Control-test link references unknown test: {test_id}")

    if len(resource_type_names) < 3:
        warnings.append("Very few resource types present; demo coverage may be limited")

    if len(resources) < 3:
        warnings.append("Very few sample resources present; test depth may be limited")

    if errors:
        print("Seed data validation failed:")
        for issue in errors:
            print(f"  ERROR: {issue}")
        if warnings:
            print("Warnings:")
            for issue in warnings:
                print(f"  WARN: {issue}")
        return 1

    print("Seed data validation passed")
    print(f"  Frameworks: {len(frameworks)}")
    print(f"  Common controls: {len(controls)}")
    print(f"  Control mappings: {len(mappings)}")
    print(f"  Resource types: {len(resource_types)}")
    print(f"  Resources: {len(resources)}")
    print(f"  Evidence records: {len(evidence)}")
    print(f"  Control-test links: {len(control_test_links)}")

    if warnings:
        print("Warnings:")
        for issue in warnings:
            print(f"  WARN: {issue}")
        if args.strict_warnings:
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
