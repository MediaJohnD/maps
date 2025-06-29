import sys
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
from sklearn.preprocessing import RobustScaler, OneHotEncoder, LabelEncoder

sys.path.append(str(Path(__file__).resolve().parents[1]))

from pipeline.preprocessing import normalize_numeric, encode_categoricals
from pipeline.merging import merge_on_keys


def test_normalize_numeric_robust():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [10, 20, 30]})
    result = normalize_numeric(df.copy(), ["a", "b"], method="robust")

    scaler = RobustScaler()
    expected_values = scaler.fit_transform(df[["a", "b"]])
    expected = pd.DataFrame(expected_values, columns=["a", "b"], index=df.index)

    assert_frame_equal(result, expected)


def test_encode_categoricals_onehot():
    df = pd.DataFrame({"color": ["red", "blue", "red"], "size": ["S", "M", "S"], "val": [1, 2, 3]})
    result = encode_categoricals(df.copy(), ["color", "size"], method="onehot")

    encoder = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    encoded = encoder.fit_transform(df[["color", "size"]])
    encoded_df = pd.DataFrame(
        encoded, columns=encoder.get_feature_names_out(["color", "size"]), index=df.index
    )
    expected = df.drop(columns=["color", "size"]).join(encoded_df)

    assert_frame_equal(result, expected)


def test_merge_on_keys():
    df1 = pd.DataFrame({"id": [1, 2], "a": [10, 20]})
    df2 = pd.DataFrame({"id": [2, 3], "b": [30, 40]})
    df3 = pd.DataFrame({"id": [3, 4], "c": [50, 60]})

    result = merge_on_keys([df1, df2, df3], ["id"]).sort_values("id").reset_index(drop=True)

    expected = (
        df1.merge(df2, on="id", how="outer")
        .merge(df3, on="id", how="outer")
        .sort_values("id")
        .reset_index(drop=True)
    )

    assert_frame_equal(result, expected)
