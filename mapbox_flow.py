"""Interactive Mapbox GL JS visualization of recovery data."""

import os
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List

import requests
import pandas as pd
import pgeocode


# -------------------------------------------------------------
# Download and extraction helpers
# -------------------------------------------------------------

def download_file(url: str, dest: Path) -> Path:
    """Download a file from HTTP(S) URL to the destination path."""
    resp = requests.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return dest


def extract_zip(zip_path: Path, out_dir: Path) -> List[Path]:
    """Extract all files from a zip archive and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)
    return [out_dir / n for n in zf.namelist()]


# -------------------------------------------------------------
# Data loading and aggregation
# -------------------------------------------------------------

def load_data_files(paths: List[Path]) -> List[pd.DataFrame]:
    """Load CSV and Excel files from a list of paths."""
    dataframes = []
    for p in paths:
        try:
            if p.suffix.lower() == ".csv":
                df = pd.read_csv(p)
                dataframes.append(df)
            elif p.suffix.lower() in {".xls", ".xlsx"}:
                df = pd.read_excel(p, engine="openpyxl")
                dataframes.append(df)
        except Exception:
            # Skip files that cannot be parsed
            continue
    return dataframes


def aggregate_metrics(dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """Aggregate spend/impressions/visits by ZIP and DMA."""
    frames: List[pd.DataFrame] = []
    for df in dfs:
        cols = {c.lower(): c for c in df.columns}
        zip_col = cols.get("destination_zip") or cols.get("zip") or cols.get("zipcode")
        dma_col = cols.get("destination_dma") or cols.get("dma")
        spend_col = cols.get("spend") or cols.get("amount")
        imp_col = cols.get("impressions")
        visit_col = cols.get("visits")
        match_col = cols.get("num_buying_hhld_indvs") or cols.get("matched_visitors")

        if not zip_col and not dma_col:
            continue

        gcols = [c for c in [zip_col, dma_col] if c]
        metrics = [c for c in [spend_col, imp_col, visit_col, match_col] if c]

        subset = df[gcols + metrics]
        subset = subset.dropna(subset=gcols, how="all")
        gcols_valid = [c for c in gcols if not subset[c].isna().all()]
        if not gcols_valid:
            continue
        agg = subset.groupby(gcols_valid).sum(numeric_only=True).reset_index()
        frames.append(agg)

    if not frames:
        raise ValueError("No usable data found in input files")

    merged = pd.concat(frames, axis=0, ignore_index=True)
    gcols = [c for c in ["destination_zip", "zip", "zipcode", "destination_dma", "dma"] if c in merged.columns]
    merged = merged.dropna(subset=gcols, how="all")
    gcols_valid = [c for c in gcols if not merged[c].isna().all()]
    out = merged.groupby(gcols_valid).sum(numeric_only=True).reset_index()

    # Standardize column names
    rename_map = {
        "destination_zip": "ZIP",
        "zip": "ZIP",
        "zipcode": "ZIP",
        "destination_dma": "DMA",
    }
    out = out.rename(columns={k: v for k, v in rename_map.items() if k in out.columns})
    return out


def add_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    """Add latitude and longitude columns for each ZIP code."""
    if "ZIP" not in df.columns:
        return df
    nomi = pgeocode.Nominatim("us")
    coords = nomi.query_postal_code(df["ZIP"].astype(str))[["latitude", "longitude"]]
    df = df.join(coords.reset_index(drop=True))
    return df


# -------------------------------------------------------------
# Flow pair preparation
# -------------------------------------------------------------

def prepare_flows(df: pd.DataFrame) -> List[Dict[str, float]]:
    """Create origin-destination pairs with coordinates for arcs."""
    if {"origin", "destination_zip"}.issubset(df.columns):
        nomi = pgeocode.Nominatim("us")
        orig_coords = nomi.query_postal_code(df["origin"].astype(str))[["latitude", "longitude"]]
        dest_coords = nomi.query_postal_code(df["destination_zip"].astype(str))[["latitude", "longitude"]]
        df = df.join(orig_coords.reset_index(drop=True).add_prefix("orig_"))
        df = df.join(dest_coords.reset_index(drop=True).add_prefix("dest_"))
        flows = (
            df[["orig_latitude", "orig_longitude", "dest_latitude", "dest_longitude", "spend"]]
            .dropna()
            .to_dict(orient="records")
        )
        return flows
    return []


# -------------------------------------------------------------
# Map rendering
# -------------------------------------------------------------

def create_html(points: List[Dict], flows: List[Dict], token: str, output: Path) -> None:
    """Generate standalone Mapbox GL JS HTML file."""

    template = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8' />
<title>Spend Flow Map</title>
<meta name='viewport' content='width=device-width, initial-scale=1' />
<script src='https://api.mapbox.com/mapbox-gl-js/v2.12.0/mapbox-gl.js'></script>
<link href='https://api.mapbox.com/mapbox-gl-js/v2.12.0/mapbox-gl.css' rel='stylesheet' />
<style>
  body {{ margin:0; padding:0; }}
  #map {{ position:absolute; top:0; bottom:0; width:100%; }}
</style>
</head>
<body>
<div id='map'></div>
<script>
mapboxgl.accessToken = '{token}';
const map = new mapboxgl.Map({{
  container: 'map',
  style: 'mapbox://styles/mapbox/light-v11',
  center: [-98, 39],
  zoom: 3
}});

const points = {json.dumps(points)};
const flows = {json.dumps(flows)};

map.on('load', () => {{
  map.addSource('points', {{ type: 'geojson', data: points }});
  map.addLayer({{
    id: 'heat',
    type: 'heatmap',
    source: 'points',
    maxzoom: 9,
    paint: {{
      'heatmap-weight': ['interpolate', ['linear'], ['get', 'spend'], 0, 0, 1, 1],
      'heatmap-intensity': 1,
      'heatmap-color': [
        'interpolate', ['linear'], ['heatmap-density'],
        0, 'rgba(33,102,172,0)',
        0.2, 'rgb(103,169,207)',
        0.4, 'rgb(209,229,240)',
        0.6, 'rgb(253,219,199)',
        0.8, 'rgb(239,138,98)',
        1, 'rgb(178,24,43)'
      ],
      'heatmap-radius': 15,
      'heatmap-opacity': 0.8
    }}
  }});

  flows.forEach((f, idx) => {{
    map.addSource('flow' + idx, {{
      type: 'geojson',
      data: {{
        'type': 'Feature',
        'geometry': {{
          'type': 'LineString',
          'coordinates': [ [f.orig_longitude, f.orig_latitude], [f.dest_longitude, f.dest_latitude] ]
        }},
        'properties': {{ 'spend': f.spend }}
      }}
    }});
    map.addLayer({{
      id: 'flow' + idx,
      type: 'line',
      source: 'flow' + idx,
      layout: {{ 'line-cap': 'round' }},
      paint: {{
        'line-color': 'rgba(0, 150, 255, 0.5)',
        'line-width': 2 + Math.log(f.spend)
      }}
    }});
  }});

  map.on('mousemove', 'heat', (e) => {{
    const props = e.features[0].properties;
    const html = `ZIP: ${'{'}props.ZIP{'}'}<br>Spend: $${'{'}props.spend{'}'}`;
    popup.setLngLat(e.lngLat).setHTML(html).addTo(map);
  }});

  const popup = new mapboxgl.Popup({{ closeButton: false, closeOnClick: false }});

  map.on('mouseleave', 'heat', () => popup.remove());
}});
</script>
</body>
</html>
"""
    output.write_text(template, encoding="utf-8")


# -------------------------------------------------------------
# Main entry point
# -------------------------------------------------------------

def main() -> None:
    urls = [
        "https://raw.githubusercontent.com/MediaJohnD/maps/882266c266d0ca3fa73c5e167b02ec3e054c3b3c/Recovery_Results.zip",
        "https://raw.githubusercontent.com/MediaJohnD/maps/882266c266d0ca3fa73c5e167b02ec3e054c3b3c/updated%20sheets%20and%20numbers%20May%2019.zip",
    ]

    token = os.environ.get("MAPBOX_TOKEN")
    if not token:
        raise EnvironmentError("Set MAPBOX_TOKEN environment variable")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        all_frames = []
        flows = []
        for url in urls:
            zip_path = download_file(url, tmpdir / Path(url).name)
            extracted = extract_zip(zip_path, tmpdir / Path(url).stem)
            frames = load_data_files(extracted)
            if frames:
                try:
                    agg = aggregate_metrics(frames)
                except ValueError:
                    agg = pd.DataFrame()
                if not agg.empty:
                    all_frames.append(agg)
                for df in frames:
                    flows.extend(prepare_flows(df))
        master = pd.concat(all_frames, axis=0, ignore_index=True)
        master = add_coordinates(master)
        # Prepare GeoJSON features
        features = []
        for _, row in master.dropna(subset=["latitude", "longitude"]).iterrows():
            props = row.to_dict()
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]],
                },
                "properties": props,
            })
        geojson = {"type": "FeatureCollection", "features": features}
        output = Path("spend_flow_map.html")
        create_html(geojson, flows, token, output)
        print(f"Map saved to {output}")


if __name__ == "__main__":
    main()
