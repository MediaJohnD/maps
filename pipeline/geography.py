"""Geographic utilities for mapping ZIP codes to DMAs and states."""

from pathlib import Path
import geopandas as gpd
import pandas as pd


def load_zip_dma_mapping(path: str) -> pd.DataFrame:
    """Load a ZIP-to-DMA mapping dataset."""
    mapping = pd.read_csv(path, dtype={"ZIP": str, "DMA": str, "STATE": str})
    return mapping


def load_shapefile(path: str) -> gpd.GeoDataFrame:
    """Load geographic boundaries as a GeoDataFrame."""
    return gpd.read_file(path)


def standardize_zip(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Zero-pad ZIP codes to five digits."""
    df[column] = df[column].astype(str).str.zfill(5)
    return df


def map_zip_to_dma(df: pd.DataFrame, zip_col: str, mapping: pd.DataFrame) -> pd.DataFrame:
    """Merge DMA and state information based on ZIP codes."""
    df = standardize_zip(df, zip_col)
    merged = df.merge(mapping, left_on=zip_col, right_on="ZIP", how="left")
    return merged
