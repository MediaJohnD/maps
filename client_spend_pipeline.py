"""Full geospatial pipeline and Mapbox visualization for client data."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import requests


###############################
# File download and extraction
###############################

def download_file(url_or_path: str) -> Path:
    """Download a file if `url_or_path` is a URL, otherwise return Path."""
    path = Path(url_or_path)
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        resp = requests.get(url_or_path, stream=True, timeout=30)
        resp.raise_for_status()
        fd, tmp_path = tempfile.mkstemp(suffix=path.suffix)
        with os.fdopen(fd, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return Path(tmp_path)
    return path


def extract_zip(zip_path: Path) -> List[Path]:
    """Extract a zip archive and return a list of extracted file paths."""
    out_dir = Path(tempfile.mkdtemp())
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)
    files: List[Path] = []
    for root, _, fnames in os.walk(out_dir):
        for fname in fnames:
            files.append(Path(root) / fname)
    return files


#######################################
# Data loading and basic preprocessing
#######################################

def load_spreadsheets(files: Iterable[Path]) -> Dict[str, pd.DataFrame]:
    """Load CSV/Excel files from a list of paths."""
    datasets: Dict[str, pd.DataFrame] = {}
    for f in files:
        name = f.stem
        try:
            if f.suffix.lower() == ".csv":
                df = pd.read_csv(f)
            elif f.suffix.lower() in {".xlsx", ".xls"}:
                # Many Excel files include descriptive header rows. Attempt to
                # find the first row containing column names.
                df_try = pd.read_excel(f, nrows=0)
                header = list(df_try.columns)
                if header[0] is None or "Unnamed" in str(header[0]):
                    df = pd.read_excel(f, skiprows=6)
                else:
                    df = pd.read_excel(f)
            else:
                continue
            datasets[name] = df
        except Exception:
            # Skip unreadable files but continue
            continue
    return datasets


def normalize_numeric(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """Apply min-max scaling to specified numeric columns."""
    for col in columns:
        if col in df.columns:
            min_val = df[col].min()
            max_val = df[col].max()
            if pd.notna(min_val) and pd.notna(max_val) and max_val != min_val:
                df[col] = (df[col] - min_val) / (max_val - min_val)
            else:
                df[col] = 0
    return df


def expand_zip_list(zip_field: str, df: pd.DataFrame) -> pd.DataFrame:
    """Expand rows where `zip_field` contains comma-separated ZIP codes."""
    if zip_field not in df.columns:
        return df
    rows = []
    for _, row in df.iterrows():
        zips = re.split(r"[;,\s]+", str(row[zip_field]))
        for z in zips:
            z = z.strip()
            if not z:
                continue
            new_row = row.copy()
            new_row[zip_field] = z
            rows.append(new_row)
    return pd.DataFrame(rows)


def aggregate_by_geo(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate numeric metrics by ZIP and DMA."""
    df = df.copy()
    # Normalize column names
    df.columns = [c.lower() for c in df.columns]
    zip_col = None
    for c in df.columns:
        if "zip" in c:
            zip_col = c
            break
    dma_col = None
    for c in df.columns:
        if "dma" in c and not c.startswith("exclude"):
            dma_col = c
            break
    if zip_col is None:
        return pd.DataFrame()

    df = expand_zip_list(zip_col, df)

    numeric_cols = [c for c in df.columns if df[c].dtype.kind in "if"]
    df = normalize_numeric(df, numeric_cols)

    group_cols = [zip_col]
    if dma_col:
        group_cols.append(dma_col)
    aggregated = df.groupby(group_cols)[numeric_cols].sum().reset_index()
    aggregated.rename(columns={zip_col: "ZIP", dma_col or "dma": "DMA"}, inplace=True)
    return aggregated


def build_flow_records(df: pd.DataFrame, zip_latlon: pd.DataFrame) -> List[Dict]:
    """Create flow features from origin/destination columns if available."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    if "origin" not in df.columns:
        return []
    origin_col = "origin"
    dest_col = None
    for c in df.columns:
        if "destination" in c and "zip" in c:
            dest_col = c
            break
    if not dest_col:
        return []
    df = expand_zip_list(dest_col, df)

    flows = []
    for _, row in df.iterrows():
        ozip = str(row[origin_col]).zfill(5)
        dzip = str(row[dest_col]).zfill(5)
        orec = zip_latlon[zip_latlon["ZIP"] == ozip]
        drec = zip_latlon[zip_latlon["ZIP"] == dzip]
        if orec.empty or drec.empty:
            continue
        flow = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [float(orec.iloc[0]["longitude"]), float(orec.iloc[0]["latitude"])],
                    [float(drec.iloc[0]["longitude"]), float(drec.iloc[0]["latitude"])],
                ],
            },
            "properties": {
                "origin_zip": ozip,
                "dest_zip": dzip,
            },
        }
        # Attach magnitude if present
        for field in ("spend", "visits", "impressions"):
            if field in df.columns:
                flow["properties"][field] = row[field]
                flow["properties"]["magnitude"] = row[field]
                break
        flows.append(flow)
    return flows


def create_heatmap_features(df: pd.DataFrame, zip_latlon: pd.DataFrame) -> List[Dict]:
    """Convert aggregated ZIP data to GeoJSON point features."""
    features = []
    for _, row in df.iterrows():
        zip_code = str(row["ZIP"]).zfill(5)
        rec = zip_latlon[zip_latlon["ZIP"] == zip_code]
        if rec.empty:
            continue
        props = row.to_dict()
        feat = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(rec.iloc[0]["longitude"]), float(rec.iloc[0]["latitude"])],
            },
            "properties": props,
        }
        if "spend" in props:
            feat["properties"]["value"] = props["spend"]
        features.append(feat)
    return features


#########################
# HTML map creation
#########################

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8'/>
<title>Client Spend Map</title>
<meta name='viewport' content='initial-scale=1,maximum-scale=1,user-scalable=no'/>
<link href='https://api.tiles.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.css' rel='stylesheet'/>
<script src='https://api.tiles.mapbox.com/mapbox-gl-js/v2.15.0/mapbox-gl.js'></script>
<style>
  body { margin:0; padding:0; }
  #map { position:absolute; top:0; bottom:0; width:100%; }
</style>
</head>
<body>
<div id='map'></div>
<script>
mapboxgl.accessToken = '{token}';
const map = new mapboxgl.Map({
  container: 'map',
  style: 'mapbox://styles/mapbox/light-v10',
  center: [-98, 38],
  zoom: 3
});

map.on('load', () => {
  map.addSource('zip_heat', { type: 'geojson', data: 'zip_heatmap.json' });
  map.addLayer({
    id: 'zip-heat',
    type: 'heatmap',
    source: 'zip_heat',
    maxzoom: 9,
    paint: {
      'heatmap-weight': ['get', 'value'],
      'heatmap-radius': 20,
      'heatmap-opacity': 0.8
    }
  });

  map.addSource('flows', { type: 'geojson', data: 'flows.json' });
  map.addLayer({
    id: 'flow-lines',
    type: 'line',
    source: 'flows',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: {
      'line-width': [ 'interpolate', ['linear'], ['get', 'magnitude'], 0, 1, 1, 6 ],
      'line-color': '#FF5733',
      'line-opacity': 0.6
    }
  });

  map.on('mousemove', 'zip-heat', (e) => {
    const features = map.queryRenderedFeatures(e.point, { layers: ['zip-heat'] });
    if (!features.length) return;
    const f = features[0];
    const p = f.properties;
    const popup = new mapboxgl.Popup({ closeButton: false })
      .setLngLat(e.lngLat)
      .setHTML(
        `<strong>ZIP:</strong> ${p.ZIP}<br>` +
        `<strong>Spend:</strong> ${p.spend || 'N/A'}<br>` +
        `<strong>Impressions:</strong> ${p.impressions || 'N/A'}<br>` +
        `<strong>Visits:</strong> ${p.visits || 'N/A'}`
      )
      .addTo(map);
    map.getCanvas().addEventListener('mouseleave', () => popup.remove(), { once: true });
  });
});
</script>
</body>
</html>"""


#########################
# Main CLI
#########################

def main() -> None:
    parser = argparse.ArgumentParser(description="Process client data and create Mapbox visualization")
    parser.add_argument("zip1", help="First zip file URL or local path")
    parser.add_argument("zip2", help="Second zip file URL or local path")
    parser.add_argument("zip_latlon", help="CSV mapping ZIP to latitude/longitude")
    parser.add_argument("output_html", help="Output HTML file")
    args = parser.parse_args()

    token = os.getenv("MAPBOX_TOKEN")
    if not token:
        raise RuntimeError("MAPBOX_TOKEN environment variable not set")

    zip1 = download_file(args.zip1)
    zip2 = download_file(args.zip2)

    files1 = extract_zip(zip1)
    files2 = extract_zip(zip2)
    datasets = load_spreadsheets(files1 + files2)

    aggregated_parts = []
    flows_parts = []

    zip_latlon = pd.read_csv(args.zip_latlon)
    zip_latlon["ZIP"] = zip_latlon[zip_latlon.columns[0]].astype(str).str.zfill(5)
    if "latitude" not in zip_latlon.columns or "longitude" not in zip_latlon.columns:
        # Some datasets use LAT and LNG column names
        if {"LAT", "LNG"}.issubset(zip_latlon.columns):
            zip_latlon.rename(columns={"LAT": "latitude", "LNG": "longitude"}, inplace=True)

    for df in datasets.values():
        agg = aggregate_by_geo(df)
        if not agg.empty:
            aggregated_parts.append(agg)
        flows = build_flow_records(df, zip_latlon)
        flows_parts.extend(flows)

    if not aggregated_parts:
        raise RuntimeError("No ZIP-level data found in provided files")

    aggregated = pd.concat(aggregated_parts, ignore_index=True)
    aggregated = aggregated.groupby(["ZIP", "DMA"], as_index=False).sum()

    heat_features = create_heatmap_features(aggregated, zip_latlon)
    heat_json = {"type": "FeatureCollection", "features": heat_features}
    with open("zip_heatmap.json", "w", encoding="utf-8") as f:
        json.dump(heat_json, f)

    flow_json = {"type": "FeatureCollection", "features": flows_parts}
    with open("flows.json", "w", encoding="utf-8") as f:
        json.dump(flow_json, f)

    html = HTML_TEMPLATE.format(token=token)
    Path(args.output_html).write_text(html, encoding="utf-8")
    print(f"Saved visualization to {args.output_html}")


if __name__ == "__main__":
    main()
