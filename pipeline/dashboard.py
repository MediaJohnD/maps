"""Dash application for interactive exploration."""

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import pandas as pd
import plotly.graph_objects as go

from .visualization import choropleth_heatmap, scatter_plot, bar_chart, flow_map


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
        states = sorted(self.df["STATE"].dropna().unique()) if "STATE" in self.df.columns else []
        periods = sorted(self.df["period"].dropna().astype(str).unique()) if "period" in self.df.columns else []

        self.app.layout = html.Div([
            html.Div([
                dcc.Dropdown(id="state-dropdown", options=[{"label": s, "value": s} for s in states], placeholder="Select state"),
                dcc.Dropdown(id="period-dropdown", options=[{"label": p, "value": p} for p in periods], placeholder="Select period"),
                dcc.Dropdown(id="demo-dropdown", options=[{"label": d, "value": d} for d in demographics], value=demographics[0]),
            ], style={"display": "flex", "gap": "1rem"}),
            dcc.Graph(id="choropleth"),
            dcc.Graph(id="scatter"),
        ])

    def _register_callbacks(self):
        @self.app.callback(
            [Output("choropleth", "figure"), Output("scatter", "figure")],
            [Input("demo-dropdown", "value"), Input("state-dropdown", "value"), Input("period-dropdown", "value")],
        )
        def update_plots(demo_col, state, period):
            df = self.df
            if state:
                df = df[df["STATE"] == state]
            if period:
                df = df[df["period"].astype(str) == period]
            fig_map = choropleth_heatmap(df, self.geo, demo_col, self.geo_key)
            fig_scatter = scatter_plot(df, "spend", demo_col)
            return fig_map, fig_scatter

    def run(self, **kwargs):
        self.app.run_server(**kwargs)
