"""Entry point for the data pipeline and visualization suite."""

from pathlib import Path
from typing import List

from sklearn.model_selection import train_test_split

import pandas as pd

from .data_ingestion import load_sources
from .preprocessing import (
    normalize_numeric,
    encode_categoricals,
    bucket_time,
    fill_missing_values,
)
from .geography import load_zip_dma_mapping, map_zip_to_dma, load_shapefile
from .merging import merge_on_keys
from .modeling import (
    detect_anomalies_autoencoder,
    detect_anomalies_iforest,
    detect_anomalies_dbscan,
    train_xgboost,
    train_lightgbm,
    train_catboost,
    evaluate_classifier,
)
from .visualization import choropleth_heatmap
from .dashboard import ReportingDashboard

import argparse


def run_pipeline(
    data_sources: List[str],
    zip_dma_mapping: str,
    geo_shapefile: str,
) -> None:
    """Execute the full pipeline from ingestion to dashboard."""
    datasets = load_sources(data_sources)

    # Example ingestion: assume spend.csv contains spend metrics with ZIP codes
    spend_df = datasets.get("spend", pd.DataFrame())
    visit_df = datasets.get("visits", pd.DataFrame())

    # Replace missing data to simplify downstream processing
    spend_df = fill_missing_values(spend_df)
    visit_df = fill_missing_values(visit_df)

    # Normalize numeric fields
    numeric_cols = [c for c in spend_df.columns if spend_df[c].dtype != object]
    spend_df = normalize_numeric(spend_df, numeric_cols)

    # Encode categorical features
    cat_cols = [c for c in spend_df.columns if spend_df[c].dtype == object and c != "ZIP"]
    spend_df = encode_categoricals(spend_df, cat_cols)

    # Bucket time monthly
    if "date" in spend_df.columns:
        spend_df = bucket_time(spend_df, "date")

    # Map ZIP to DMA
    mapping = load_zip_dma_mapping(zip_dma_mapping)
    spend_df = map_zip_to_dma(spend_df, "ZIP", mapping)

    # Merge datasets on geography and period
    # Collect datasets that share geography/time keys
    dfs = [spend_df]
    if not visit_df.empty:
        if "date" in visit_df.columns:
            visit_df = bucket_time(visit_df, "date")
        visit_df = map_zip_to_dma(visit_df, "ZIP", mapping)
        dfs.append(visit_df)
    master = merge_on_keys(dfs, ["ZIP", "DMA", "STATE", "period"])

    # Train unsupervised models to flag unusual behavior
    feature_cols = [c for c in master.columns if c not in {"ZIP", "DMA", "STATE", "period"}]
    master["ae_mse"] = detect_anomalies_autoencoder(master, feature_cols)
    master["iforest"] = detect_anomalies_iforest(master, feature_cols)
    master["dbscan"] = detect_anomalies_dbscan(master, feature_cols)

    # Example supervised model training if target available
    if "target" in master.columns:
        X = master[feature_cols]
        y = master["target"]
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model = train_xgboost(X_train, y_train)
        print(evaluate_classifier(model, X_test, y_test))

    # Visualization and dashboard
    geo = load_shapefile(geo_shapefile)
    choropleth_heatmap(master, geo, "spend", "ZIP", output_html="spend_map.html")

    app = ReportingDashboard(master, geo, "ZIP")
    app.run(debug=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data pipeline")
    parser.add_argument(
        "--data-sources",
        nargs="+",
        help="List of CSV or Excel files to ingest",
        required=True,
    )
    parser.add_argument("--zip-dma-mapping", required=True, help="ZIP to DMA CSV")
    parser.add_argument("--geo-shapefile", required=True, help="Geographic shapefile")
    args = parser.parse_args()

    run_pipeline(args.data_sources, args.zip_dma_mapping, args.geo_shapefile)
