"""Dash application for interactive exploration."""

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd
import plotly.graph_objects as go

from .visualization import choropleth_heatmap, scatter_plot


class ReportingDashboard:
    """Dash app providing interactive filters and visualizations."""

    def __init__(self, df: pd.DataFrame, geo, geo_key: str):
        self.df = df
        self.geo = geo
        self.geo_key = geo_key
        self.app = dash.Dash(__name__)
        self._setup_layout()
        self._register_callbacks()

    def _setup_layout(self):
        demographics = [c for c in self.df.columns if c.startswith("demo_")]
        options = (
            [{"label": d, "value": d} for d in demographics]
            if demographics
            else []
        )
        value = demographics[0] if demographics else None

        self.app.layout = html.Div(
            [
                dcc.Dropdown(id="demo-dropdown", options=options, value=value),
                dcc.Graph(id="choropleth"),
                dcc.Graph(id="scatter"),
            ]
        )

    def _register_callbacks(self):
        @self.app.callback(
            [Output("choropleth", "figure"), Output("scatter", "figure")],
            [Input("demo-dropdown", "value")],
        )
        def update_plots(demo_col):
            if not demo_col:
                return go.Figure(), go.Figure()

            fig_map = choropleth_heatmap(
                self.df, self.geo, demo_col, self.geo_key
            )
            fig_scatter = scatter_plot(self.df, "spend", demo_col)
            return fig_map, fig_scatter

    def run(self, **kwargs):
        self.app.run_server(**kwargs)
