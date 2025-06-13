"""Utilities to merge multiple datasets into a master table."""

from typing import List

import pandas as pd


def merge_on_keys(dfs: List[pd.DataFrame], keys: List[str]) -> pd.DataFrame:
    """Iteratively merge dataframes on the specified keys."""
    if not dfs:
        raise ValueError("No dataframes provided for merging")
    merged = dfs[0]
    for df in dfs[1:]:
        merged = merged.merge(df, on=keys, how="outer")
    return merged
