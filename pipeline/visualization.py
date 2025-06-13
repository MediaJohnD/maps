"""Visualization helpers for interactive dashboards."""

from typing import Optional

import pandas as pd
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go


def choropleth_heatmap(
    df: pd.DataFrame,
    geo: gpd.GeoDataFrame,
    value_col: str,
    geo_key: str,
    output_html: Optional[str] = None,
) -> go.Figure:
    """Create a Plotly choropleth heatmap by ZIP code or DMA."""
    merged = geo.merge(df[[geo_key, value_col]], left_on=geo_key, right_on=geo_key, how="left")
    fig = px.choropleth_mapbox(
        merged,
        geojson=merged.__geo_interface__,
        locations=merged.index,
        color=value_col,
        mapbox_style="carto-positron",
        zoom=3,
        center={"lat": merged.geometry.centroid.y.mean(), "lon": merged.geometry.centroid.x.mean()},
        opacity=0.6,
        hover_name=geo_key,
    )
    if output_html:
        fig.write_html(output_html)
    return fig


def scatter_plot(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    """Create a scatter plot using Plotly."""
    return px.scatter(df, x=x, y=y)


def bar_chart(df: pd.DataFrame, x: str, y: str) -> go.Figure:
    """Create a bar chart using Plotly."""
    return px.bar(df, x=x, y=y)


def flow_map(df: pd.DataFrame, origin: str, dest: str, value: str) -> go.Figure:
    """Visualize flows between geographies using great-circle arcs."""
    lons = df[[f"{origin}_lon", f"{dest}_lon"]].values
    lats = df[[f"{origin}_lat", f"{dest}_lat"]].values
    traces = []
    for i, row in df.iterrows():
        lon0, lon1 = row[f"{origin}_lon"], row[f"{dest}_lon"]
        lat0, lat1 = row[f"{origin}_lat"], row[f"{dest}_lat"]
        traces.append(
            go.Scattermapbox(
                lon=[lon0, lon1],
                lat=[lat0, lat1],
                mode="lines",
                line=dict(width=2, color="blue"),
                opacity=min(1.0, row[value] / df[value].max()),
            )
        )
    return go.Figure(data=traces)
