"""Machine learning models for anomaly detection and prediction."""

from typing import Dict, List, Tuple

import pandas as pd
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.cluster import DBSCAN
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.metrics import classification_report
from tensorflow import keras
from tensorflow.keras import layers
import xgboost as xgb
import lightgbm as lgb
import catboost as cb


# ---------------------------------------------------------------------------
# Unsupervised models
# ---------------------------------------------------------------------------

def build_autoencoder(input_dim: int) -> keras.Model:
    """Create a simple dense autoencoder."""
    input_layer = keras.Input(shape=(input_dim,))
    encoded = layers.Dense(input_dim // 2, activation="relu")(input_layer)
    encoded = layers.Dense(input_dim // 4, activation="relu")(encoded)
    decoded = layers.Dense(input_dim // 2, activation="relu")(encoded)
    decoded = layers.Dense(input_dim, activation="linear")(decoded)
    autoencoder = keras.Model(inputs=input_layer, outputs=decoded)
    autoencoder.compile(optimizer="adam", loss="mse")
    return autoencoder


def detect_anomalies_autoencoder(df: pd.DataFrame, feature_cols: List[str]) -> pd.Series:
    """Fit an autoencoder and return anomaly scores."""
    X = df[feature_cols].values
    model = build_autoencoder(X.shape[1])
    model.fit(X, X, epochs=20, batch_size=256, verbose=0)
    recon = model.predict(X)
    mse = ((X - recon) ** 2).mean(axis=1)
    return pd.Series(mse, index=df.index, name="autoencoder_mse")


def detect_anomalies_iforest(df: pd.DataFrame, feature_cols: List[str]) -> pd.Series:
    """Isolation Forest anomaly scores."""
    model = IsolationForest(contamination=0.01, random_state=42)
    model.fit(df[feature_cols])
    scores = -model.score_samples(df[feature_cols])
    return pd.Series(scores, index=df.index, name="iforest_score")


def detect_anomalies_dbscan(df: pd.DataFrame, feature_cols: List[str]) -> pd.Series:
    """DBSCAN labels where -1 indicates anomalies."""
    model = DBSCAN(eps=0.5, min_samples=5)
    labels = model.fit_predict(df[feature_cols])
    return pd.Series(labels == -1, index=df.index, name="dbscan_anomaly")


# ---------------------------------------------------------------------------
# Supervised models
# ---------------------------------------------------------------------------

def train_xgboost(X: pd.DataFrame, y: pd.Series) -> xgb.XGBClassifier:
    """Train an XGBoost classifier with simple hyperparameter tuning."""
    params = {
        "max_depth": [3, 5, 7],
        "n_estimators": [100, 200],
        "learning_rate": [0.05, 0.1]
    }
    clf = xgb.XGBClassifier(objective="binary:logistic", eval_metric="logloss")
    grid = GridSearchCV(clf, params, cv=3, n_jobs=-1)
    grid.fit(X, y)
    return grid.best_estimator_


def train_lightgbm(X: pd.DataFrame, y: pd.Series) -> lgb.LGBMClassifier:
    """Train a LightGBM classifier with basic hyperparameter tuning."""
    params = {
        "num_leaves": [31, 63],
        "n_estimators": [100, 200],
        "learning_rate": [0.05, 0.1]
    }
    clf = lgb.LGBMClassifier()
    grid = GridSearchCV(clf, params, cv=3, n_jobs=-1)
    grid.fit(X, y)
    return grid.best_estimator_


def train_catboost(X: pd.DataFrame, y: pd.Series) -> cb.CatBoostClassifier:
    """Train a CatBoost classifier with automatic categorical handling."""
    clf = cb.CatBoostClassifier(verbose=0)
    clf.fit(X, y)
    return clf


def evaluate_classifier(model, X_test: pd.DataFrame, y_test: pd.Series) -> str:
    """Return a classification report string."""
    preds = model.predict(X_test)
    return classification_report(y_test, preds)
