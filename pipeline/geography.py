"""Geographic utilities for mapping ZIP codes to DMAs and states."""

import pandas as pd


def load_zip_dma_mapping(path: str) -> pd.DataFrame:
    """Load a ZIP-to-DMA mapping dataset."""
    mapping = pd.read_csv(path, dtype={"ZIP": str, "DMA": str, "STATE": str})
    return mapping


def map_zip_to_dma(df: pd.DataFrame, zip_col: str, mapping: pd.DataFrame) -> pd.DataFrame:
    """Merge DMA and state information based on ZIP codes."""
    df[zip_col] = df[zip_col].astype(str)
    merged = df.merge(mapping, left_on=zip_col, right_on="ZIP", how="left")
    return merged
