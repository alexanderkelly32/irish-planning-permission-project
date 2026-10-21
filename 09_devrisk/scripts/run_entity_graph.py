"""Runner: entity-graph data layer (nodes + edges).

Nodes: applications, developers (groups), SPVs, consultants, authorities,
parcels. Edges: applied-for, same-parcel-preceded, same-developer,
same-consultant, developer-consultant pair, same-authority. Writes
graph_nodes.csv + graph_edges.csv (networkx-ready) + graph_stats.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from devrisk import settings  # noqa: E402

if __name__ == "__main__":
    nodes = []
    edges = []

    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    pool = set(labels["case_key"].astype(str))
    apps = register[register["case_key"].astype(str).isin(pool)].drop_duplicates("case_key")
    entities = pd.read_csv(settings.SILVER_DIR / "applicant_entities.csv")
    groups = pd.read_csv(settings.SILVER_DIR / "developer_groups.csv")
    consultants = pd.read_csv(settings.SILVER_DIR / "consultant_mentions.csv")

    # Applications
    for _, row in apps.iterrows():
        nodes.append({"node_id": f"app:{row['case_key']}", "type": "application",
                      "authority": str(row.get("PlanningAuthority") or ""),
                      "units": pd.to_numeric(pd.Series([row.get("NumResidentialUnits")]), errors="coerce").iloc[0]})

    # Authorities
    for authority in apps["PlanningAuthority"].dropna().unique():
        nodes.append({"node_id": f"authority:{authority}", "type": "authority", "authority": str(authority)})

    # Developers (groups) + SPVs
    pool_entities = entities[entities["case_key"].astype(str).isin(pool)]
    for entity in pool_entities["entity_key"].dropna().unique():
        nodes.append({"node_id": f"dev:{entity}", "type": "developer"})
    for spv in pool_entities["case_key"].astype(str).unique():
        nodes.append({"node_id": f"spv:{spv}", "type": "spv"})

    # Consultants
    mentions_pool = consultants[consultants["appno"].astype(str).isin(apps["ApplicationNumber"].astype(str))]
    for entity in mentions_pool["name"].dropna().unique():
        nodes.append({"node_id": f"consultant:{entity}", "type": "consultant"})

    # Parcels (from site lineage)
    lineage = pd.read_csv(settings.SILVER_DIR / "site_lineage_features.csv")
    for _, row in lineage.iterrows():
        nodes.append({"node_id": f"parcel:{row['case_key']}", "type": "parcel"})

    # Edges
    for _, row in apps.iterrows():
        case_key = str(row["case_key"])
        authority = str(row.get("PlanningAuthority") or "")
        edges.append({"source": f"app:{case_key}", "target": f"authority:{authority}", "type": "located_in"})
        edges.append({"source": f"app:{case_key}", "target": f"parcel:{case_key}", "type": "on_parcel"})
        entity_row = pool_entities[pool_entities["case_key"] == case_key]
        if len(entity_row) and pd.notna(entity_row.iloc[0]["entity_key"]):
            edges.append({"source": f"dev:{entity_row.iloc[0]['entity_key']}", "target": f"app:{case_key}", "type": "applied_for"})
            edges.append({"source": f"spv:{case_key}", "target": f"dev:{entity_row.iloc[0]['entity_key']}", "type": "belongs_to"})

    # Same-parcel predecessors (lineage)
    for _, row in lineage.iterrows():
        if row.get("n_prior_same_parcel", 0) > 0:
            edges.append({"source": f"parcel:{row['case_key']}", "target": f"app:{row['case_key']}", "type": "has_prior_applications"})

    # Consultant mentions -> application + developer-consultant pairs
    for _, row in mentions_pool.iterrows():
        app_case = apps[apps["ApplicationNumber"].astype(str) == str(row["appno"])]
        if len(app_case):
            app_id = f"app:{app_case.iloc[0]['case_key']}"
            edges.append({"source": f"consultant:{row['name']}", "target": app_id, "type": "advised"})
            entity_row = pool_entities[pool_entities["case_key"] == str(app_case.iloc[0]["case_key"])]
            if len(entity_row) and pd.notna(entity_row.iloc[0]["entity_key"]):
                edges.append({"source": f"dev:{entity_row.iloc[0]['entity_key']}", "target": f"consultant:{row['name']}", "type": "worked_with"})

    # Same-developer edges between applications (chronological pairs)
    app_entity = pool_entities.dropna(subset=["entity_key"])
    for entity, group in app_entity.groupby("entity_key"):
        ordered = sorted(group["case_key"].astype(str))
        for i in range(len(ordered) - 1):
            edges.append({"source": f"app:{ordered[i]}", "target": f"app:{ordered[i+1]}", "type": "same_developer_next"})

    nodes_df = pd.DataFrame(nodes).drop_duplicates("node_id")
    edges_df = pd.DataFrame(edges).drop_duplicates(["source", "target", "type"])
    nodes_df.to_csv(settings.SILVER_DIR / "graph_nodes.csv", index=False)
    edges_df.to_csv(settings.SILVER_DIR / "graph_edges.csv", index=False)
    stats = {
        "nodes": int(len(nodes_df)),
        "edges": int(len(edges_df)),
        "nodes_by_type": nodes_df["type"].value_counts().to_dict(),
        "edges_by_type": edges_df["type"].value_counts().to_dict(),
    }
    (settings.SILVER_DIR / "graph_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))
