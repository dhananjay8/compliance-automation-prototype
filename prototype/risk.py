"""Risk graph and predictive drift scoring (Phase 4 roadmap item).

Builds a graph connecting integrations -> resources -> controls -> drift
events using ``networkx``, and derives a lightweight predictive risk score
per integration from recent drift frequency/severity trends. This is a
deterministic statistical heuristic (not a trained ML model) but it is fully
data-driven from real `drift_detection`/`resource`/`control_test` rows, so it
demonstrates a genuinely working risk-graph capability end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import networkx as nx

from db import Database

_SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 4, "critical": 8}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_risk_graph(db: Database, tenant_id: str) -> dict[str, Any]:
    """Build a graph of integrations -> resources -> controls with drift-derived risk weights."""
    graph = nx.DiGraph()

    integrations = db.execute(
        "SELECT id, name, connector FROM integration WHERE tenant_id = %s",
        (tenant_id,),
    )
    for integ in integrations:
        graph.add_node(
            f"integration:{integ['id']}",
            type="integration",
            label=integ["name"],
            connector=integ["connector"],
            risk_score=0.0,
        )

    drift_rows = db.execute(
        """SELECT integration_id, resource_type, external_id, severity, drift_type,
                  acknowledged, created_at
           FROM drift_detection
           WHERE tenant_id = %s
           ORDER BY created_at DESC
           LIMIT 500""",
        (tenant_id,),
    )
    now = _now()
    for row in drift_rows:
        integ_node = f"integration:{row['integration_id']}"
        resource_node = f"resource:{row['resource_type']}:{row['external_id']}"
        if integ_node not in graph:
            graph.add_node(integ_node, type="integration", label=str(row["integration_id"]), risk_score=0.0)
        if resource_node not in graph:
            graph.add_node(
                resource_node,
                type="resource",
                label=f"{row['resource_type']}:{row['external_id']}",
                risk_score=0.0,
            )
        age_days = max((now - row["created_at"]).total_seconds() / 86400.0, 0.0)
        recency_weight = 0.5 ** (age_days / 14.0)  # half-life of 14 days
        severity_weight = _SEVERITY_WEIGHT.get(row["severity"], 1)
        ack_discount = 0.3 if row["acknowledged"] else 1.0
        weight = severity_weight * recency_weight * ack_discount

        graph.add_edge(
            integ_node,
            resource_node,
            drift_type=row["drift_type"],
            severity=row["severity"],
            weight=round(weight, 4),
        )
        graph.nodes[resource_node]["risk_score"] = round(
            graph.nodes[resource_node].get("risk_score", 0.0) + weight, 4
        )
        graph.nodes[integ_node]["risk_score"] = round(
            graph.nodes[integ_node].get("risk_score", 0.0) + weight, 4
        )

    nodes = [
        {"id": node_id, **data}
        for node_id, data in graph.nodes(data=True)
    ]
    edges = [
        {"source": u, "target": v, **data}
        for u, v, data in graph.edges(data=True)
    ]
    return {
        "tenant_id": tenant_id,
        "nodes": nodes,
        "edges": edges,
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
    }


def predict_drift_risk(db: Database, tenant_id: str) -> dict[str, Any]:
    """Score each integration's likelihood of near-term drift from recent trends."""
    integrations = db.execute(
        "SELECT id, name, connector FROM integration WHERE tenant_id = %s",
        (tenant_id,),
    )
    now = _now()
    window_recent_start = now - timedelta(days=7)
    window_prior_start = now - timedelta(days=14)

    results = []
    for integ in integrations:
        recent = db.execute(
            """SELECT severity, COUNT(*) as c
               FROM drift_detection
               WHERE tenant_id = %s AND integration_id = %s AND created_at >= %s
               GROUP BY severity""",
            (tenant_id, integ["id"], window_recent_start),
        )
        prior = db.execute(
            """SELECT COUNT(*) as c
               FROM drift_detection
               WHERE tenant_id = %s AND integration_id = %s
                 AND created_at >= %s AND created_at < %s""",
            (tenant_id, integ["id"], window_prior_start, window_recent_start),
        )
        recent_total = sum(r["c"] for r in recent)
        prior_total = prior[0]["c"] if prior else 0
        weighted_score = sum(_SEVERITY_WEIGHT.get(r["severity"], 1) * r["c"] for r in recent)

        if prior_total == 0 and recent_total == 0:
            trend = "stable"
        elif prior_total == 0:
            trend = "increasing"
        else:
            delta = (recent_total - prior_total) / max(prior_total, 1)
            if delta > 0.25:
                trend = "increasing"
            elif delta < -0.25:
                trend = "decreasing"
            else:
                trend = "stable"

        if weighted_score >= 20:
            risk_level = "critical"
        elif weighted_score >= 10:
            risk_level = "high"
        elif weighted_score >= 3:
            risk_level = "medium"
        else:
            risk_level = "low"

        results.append(
            {
                "integration_id": integ["id"],
                "integration_name": integ["name"],
                "connector": integ["connector"],
                "drift_events_last_7d": recent_total,
                "drift_events_prior_7d": prior_total,
                "weighted_risk_score": round(weighted_score, 2),
                "trend": trend,
                "risk_level": risk_level,
            }
        )

    results.sort(key=lambda r: r["weighted_risk_score"], reverse=True)
    return {"tenant_id": tenant_id, "predictions": results, "generated_at": now.isoformat()}
