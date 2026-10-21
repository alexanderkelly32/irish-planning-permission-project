"""Runner: graph model - learned graph features for the pool.

Builds the entity graph from graph_nodes/edges CSVs, computes graph
features per application node (degree, pagerank, developer-hub score,
consultant-degree, parcel cluster size, two-hop developer neighbours),
and ablates them on commencement + FI + sale vs the frozen protocols.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import networkx as nx  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import GradientBoostingRegressor  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from devrisk import settings  # noqa: E402

RNG = np.random.default_rng(7)


if __name__ == "__main__":
    nodes = pd.read_csv(settings.SILVER_DIR / "graph_nodes.csv")
    edges = pd.read_csv(settings.SILVER_DIR / "graph_edges.csv")
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes["node_id"])
    graph.add_edges_from(zip(edges["source"], edges["target"], strict=False))

    pagerank = nx.pagerank(graph, alpha=0.85)
    app_nodes = [n for n in graph.nodes if n.startswith("app:")]
    rows = []
    for node in app_nodes:
        case_key = node[4:]
        in_deg = graph.in_degree(node)
        out_deg = graph.out_degree(node)
        dev_neighbours = [n for n in graph.predecessors(node) if n.startswith("dev:")]
        consultant_neighbours = [n for n in graph.predecessors(node) if n.startswith("consultant:")]
        dev_twohop = set()
        for dev in dev_neighbours:
            dev_twohop.update(n for n in graph.successors(dev) if n.startswith("app:") and n != node)
        rows.append({
            "case_key": case_key,
            "graph_in_degree": in_deg,
            "graph_out_degree": out_deg,
            "graph_pagerank": pagerank.get(node, 0.0),
            "graph_developer_count": len(dev_neighbours),
            "graph_consultant_count": len(consultant_neighbours),
            "graph_dev_siblings": len(dev_twohop),
            "graph_dev_neighbour_pagerank": float(np.mean([pagerank.get(d, 0.0) for d in dev_neighbours])) if dev_neighbours else 0.0,
        })
    graph_features = pd.DataFrame(rows)
    graph_features.to_csv(settings.SILVER_DIR / "graph_model_features.csv", index=False)

    # ---- Ablations ----
    labels = pd.read_csv(settings.SILVER_DIR / "pain_labels_pool.csv").rename(columns={"scheme_id": "case_key"})
    register = pd.read_parquet(settings.BRONZE_DIR / "npad_register_bronze.parquet")
    reg = register[["case_key", "GrantDate", "NumResidentialUnits", "DevelopmentDescription", "ReceivedDate"]].drop_duplicates("case_key")
    base = labels.merge(reg, on="case_key", how="inner").merge(graph_features, on="case_key", how="left")
    base["grant_dt"] = pd.to_datetime(base["GrantDate"], utc=True, errors="coerce")
    base["grant_year"] = base["grant_dt"].dt.year
    base["received_dt"] = pd.to_datetime(base["ReceivedDate"], utc=True, errors="coerce")
    base["received_year"] = base["received_dt"].dt.year
    base["activation"] = pd.to_numeric(base["activation_days"], errors="coerce").clip(lower=0)
    base["log_units"] = np.log1p(pd.to_numeric(base["NumResidentialUnits"], errors="coerce").fillna(0))
    base["type_apartment"] = base["DevelopmentDescription"].fillna("").str.contains("apartment|duplex", case=False, regex=True).astype(int)

    G_FEATS = [c for c in graph_features.columns if c != "case_key"]
    report: dict = {}

    # Commencement (frozen protocol: train<2022, test 2022+)
    comm = base[base["activation_linked"].astype(str).str.lower() == "true"].dropna(subset=["activation", "grant_dt"])
    train = comm[comm["grant_dt"] < pd.Timestamp("2022-01-01", tz="UTC")]
    test = comm[comm["grant_dt"] >= pd.Timestamp("2022-01-01", tz="UTC")]
    CBASE = ["log_units", "type_apartment", "grant_year"]

    def comm_run(cols):
        model = GradientBoostingRegressor(loss="quantile", alpha=0.5, n_estimators=250, max_depth=3,
                                          learning_rate=0.05, min_samples_leaf=15, random_state=7)
        model.fit(train[cols].fillna(0.0), train["activation"])
        pred = np.maximum(model.predict(test[cols].fillna(0.0)), 1.0)
        return pred

    p_base = comm_run(CBASE)
    p_graph = comm_run(CBASE + G_FEATS)
    y = test["activation"].to_numpy()
    mae_b = float(np.mean(np.abs(y - p_base)))
    mae_g = float(np.mean(np.abs(y - p_graph)))
    boot = []
    for _ in range(400):
        idx = RNG.integers(0, len(y), len(y))
        boot.append(float(np.mean(np.abs(y[idx] - p_graph[idx]))))
    report["commencement"] = {
        "n_train": int(len(train)), "n_test": int(len(test)),
        "base_mae": round(mae_b, 0), "graph_mae": round(mae_g, 0),
        "delta": round(mae_g - mae_b, 0),
        "graph_mae_ci95": [round(float(np.percentile(boot, 2.5)), 0), round(float(np.percentile(boot, 97.5)), 0)],
    }

    # FI
    fi = base.dropna(subset=["fi_requested"]).copy()
    fi["fi_flag"] = fi["fi_requested"].astype(int)
    fi_train = fi[fi["received_year"] < 2021]
    fi_test = fi[fi["received_year"] >= 2021]
    FBASE = ["log_units", "type_apartment", "received_year"]
    if fi_test["fi_flag"].nunique() == 2:
        def fi_run(cols):
            clf = LogisticRegression(C=0.5, max_iter=2000)
            clf.fit(fi_train[cols].fillna(0.0), fi_train["fi_flag"])
            return clf.predict_proba(fi_test[cols].fillna(0.0))[:, 1]
        report["fi"] = {
            "base_auc": round(float(roc_auc_score(fi_test["fi_flag"], fi_run(FBASE))), 3),
            "graph_auc": round(float(roc_auc_score(fi_test["fi_flag"], fi_run(FBASE + G_FEATS))), 3),
        }

    out = settings.SILVER_DIR / "graph_model_ablation.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
