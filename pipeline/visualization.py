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
