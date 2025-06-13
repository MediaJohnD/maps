"""Data cleaning and feature engineering utilities."""

from typing import List

import pandas as pd
from sklearn.preprocessing import OneHotEncoder, LabelEncoder, RobustScaler, MinMaxScaler
import sklearn
from packaging import version


def normalize_numeric(df: pd.DataFrame, columns: List[str], method: str = "robust") -> pd.DataFrame:
    """Normalize numeric columns using the specified scaling method."""
    scaler = RobustScaler() if method == "robust" else MinMaxScaler()
    df[columns] = scaler.fit_transform(df[columns])
    return df


def encode_categorical_onehot(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """One-hot encode categorical columns, dropping the original columns."""
    if version.parse(sklearn.__version__) >= version.parse("1.2"):
        encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    else:
        encoder = OneHotEncoder(sparse=False, handle_unknown="ignore")
    encoded = encoder.fit_transform(df[columns])
    encoded_df = pd.DataFrame(encoded, columns=encoder.get_feature_names_out(columns), index=df.index)
    df = df.drop(columns=columns).join(encoded_df)
    return df


def encode_categorical_label(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """Label encode categorical columns."""
    for col in columns:
        le = LabelEncoder()
        df[col] = le.fit_transform(df[col].astype(str))
    return df


def encode_categoricals(df: pd.DataFrame, columns: List[str], method: str = "onehot") -> pd.DataFrame:
    """Encode categorical variables using one-hot or label encoding."""
    if method == "onehot":
        return encode_categorical_onehot(df, columns)
    return encode_categorical_label(df, columns)


def bucket_time(df: pd.DataFrame, date_col: str, freq: str = "M") -> pd.DataFrame:
    """Bucket dates into the specified temporal frequency."""
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df["period"] = df[date_col].dt.to_period(freq)
    return df
