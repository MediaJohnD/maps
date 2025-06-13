"""Generate an interactive ZIP code choropleth from zipped data sources."""

import argparse
import os
import zipfile
import tempfile
from urllib.parse import urlparse

import pandas as pd
import geopandas as gpd
import folium
import requests


def read_zipped_shapefile(zip_path: str) -> gpd.GeoDataFrame:
    """Extract and read the first shapefile found in a zip archive."""
    with zipfile.ZipFile(zip_path, 'r') as zf, tempfile.TemporaryDirectory() as tmpdir:
        zf.extractall(tmpdir)
        shp_files = []
        for root, _, files in os.walk(tmpdir):
            for f in files:
                if f.endswith('.shp'):
                    shp_files.append(os.path.join(root, f))
        if not shp_files:
            raise FileNotFoundError('No .shp file found in geometry zip')
        return gpd.read_file(shp_files[0])


def read_zipped_csv(zip_path: str) -> pd.DataFrame:
    """Read the first CSV file found in a zip archive."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        csv_files = [f for f in zf.namelist() if f.endswith('.csv')]
        if not csv_files:
            raise FileNotFoundError('No .csv file found in data zip')
        with zf.open(csv_files[0]) as f:
            return pd.read_csv(f)


def download_if_url(path: str) -> str:
    """Download the file if `path` is an HTTP(S) URL and return the local path."""
    if path.startswith("http://") or path.startswith("https://"):
        response = requests.get(path, stream=True)
        response.raise_for_status()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(urlparse(path).path)[1])
        for chunk in response.iter_content(chunk_size=8192):
            tmp.write(chunk)
        tmp.close()
        return tmp.name
    return path


def main():
    parser = argparse.ArgumentParser(description="Create ZIP code choropleth by spend.")
    parser.add_argument('geometry_zip', help='Zip file containing zip code shapefile')
    parser.add_argument('data_zip', help='Zip file containing spending data CSV')
    parser.add_argument('output_html', help='Path to output html file')
    parser.add_argument('--geometry-zip-field', default='ZCTA5CE10',
                        help='Zip code field in the geometry shapefile (default: ZCTA5CE10)')
    parser.add_argument('--data-zip-field', default='zip',
                        help='Zip code field in the spending CSV (default: zip)')
    parser.add_argument('--spend-field', default='spend',
                        help='Spending field in the CSV (default: spend)')
    parser.add_argument('--states', help='Optional shapefile of state boundaries to overlay')
    args = parser.parse_args()

    geometry_zip_path = download_if_url(args.geometry_zip)
    data_zip_path = download_if_url(args.data_zip)

    gdf = read_zipped_shapefile(geometry_zip_path)
    df = read_zipped_csv(data_zip_path)

    gdf[args.geometry_zip_field] = gdf[args.geometry_zip_field].astype(str)
    df[args.data_zip_field] = df[args.data_zip_field].astype(str)

    merged = gdf.merge(df, left_on=args.geometry_zip_field,
                       right_on=args.data_zip_field, how='left')

    m = folium.Map(location=[merged.geometry.centroid.y.mean(),
                             merged.geometry.centroid.x.mean()], zoom_start=5)

    choropleth = folium.Choropleth(
        geo_data=merged,
        data=merged,
        columns=[args.geometry_zip_field, args.spend_field],
        key_on=f'feature.properties.{args.geometry_zip_field}',
        fill_color='YlOrRd',
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name='Total Spend ($)',
        nan_fill_color='lightgray',
        nan_fill_opacity=0.4
    ).add_to(m)

    if args.states:
        states = gpd.read_file(args.states)
        folium.GeoJson(
            states,
            name="States",
            style_function=lambda x: {
                'color': 'black',
                'weight': 1,
                'fillOpacity': 0
            }
        ).add_to(m)

    m.save(args.output_html)
    print(f"Saved choropleth map to {args.output_html}")

    if geometry_zip_path != args.geometry_zip:
        os.unlink(geometry_zip_path)
    if data_zip_path != args.data_zip:
        os.unlink(data_zip_path)


if __name__ == '__main__':
    main()
