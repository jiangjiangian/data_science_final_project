"""
scripts/step3_models.py

Step 3 — Train m1..m7 ablation + 5-algorithm comparison + tuning + holdout.

Time-aware splits:
  train = games BEFORE 2024-08-01     (~ first 200 games warm-up + early season)
  valid = 2024-08-01  to  2024-09-15   (~mid-to-late season, CV-window-like)
  test  = 2024-09-16  through end      (Sep-Oct + playoffs; held out)

Models trained:
  - m1: intercept only (HFA baseline)
  - m2..m7: progressive ablation (stadium, weather, team-strength, batter-state)
    NB: weather features not available in sandbox -> m3/m5/m6/m7 currently use
        a "no_weather" variant. R production version (step3 mirror) reads
        weather merged in via R/fetch_cwa.R output.

Algorithms compared on full feature set (m7+):
  logit, glmnet (ElasticNet), RandomForest, XGBoost, LightGBM

Outputs:
  Results/figures/model_comparison.png
  Results/figures/calibration.png
  Results/figures/shap_summary.png
  Results/eval/results_ablation.csv
  Results/eval/results_algos.csv
  Results/eval/_final_metrics.json
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import (
    roc_auc_score, accuracy_score, brier_score_loss, log_loss,
    confusion_matrix, classification_report
)
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
import xgboost as xgb
import lightgbm as lgb

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*ConvergenceWarning.*")

ROOT = Path(__file__).resolve().parent.parent
IN_CSV = ROOT / "data/processed/model_ready_data.csv"
FIG = ROOT / "Results/figures"
EVAL = ROOT / "Results/eval"
FIG.mkdir(parents=True, exist_ok=True)
EVAL.mkdir(parents=True, exist_ok=True)

RNG = 42

# ============================================================================
# Load
# ============================================================================
df = pd.read_csv(IN_CSV, parse_dates=["date"])
print(f"loaded {len(df)} games  cols={df.shape[1]}")

# Use only rows with complete rolling features (post warm-up)
df = df[df["features_complete"] == 1].reset_index(drop=True)
print(f"after warm-up filter: {len(df)} games")
print(f"home_win base rate: {df['is_home_win'].mean():.3f}")

# ============================================================================
# Time-aware split
# ============================================================================
train = df[df["date"] < "2024-08-01"].reset_index(drop=True)
valid = df[(df["date"] >= "2024-08-01") & (df["date"] < "2024-09-16")].reset_index(drop=True)
test  = df[df["date"] >= "2024-09-16"].reset_index(drop=True)
print(f"\nsplit: train={len(train)}  valid={len(valid)}  test={len(test)}")
print(f"home_win  train={train['is_home_win'].mean():.3f}  "
      f"valid={valid['is_home_win'].mean():.3f}  "
      f"test={test['is_home_win'].mean():.3f}")

# ============================================================================
# Feature group catalogue
# ============================================================================
WEATHER_COLS = []  # placeholder; will populate when CWA-merged data exists

STADIUM_COL = ["stadium"]
BATTER_STATE_DIFF = [
    "diff_OPS_30g", "diff_HR_per_g_30g", "diff_K_pct_30g",
    "diff_BB_pct_30g", "diff_runs_per_g_30g", "diff_at_stadium_OPS",
]
TEAM_STRENGTH = ["diff_elo", "diff_pythag", "diff_rest", "pf_pre"]
SPLIT_HOME_AWAY_OPS = ["home_OPS_30g", "away_OPS_30g"]   # for richer non-linear models

FEATURE_GROUPS = {
    "m1": [],                                   # intercept only -> handled specially
    "m2": STADIUM_COL,                          # stadium only
    "m3": WEATHER_COLS,                         # weather only (placeholder)
    "m4": STADIUM_COL + WEATHER_COLS,           # stadium + weather
    "m5": STADIUM_COL + TEAM_STRENGTH,          # stadium + team strength
    "m6": STADIUM_COL + TEAM_STRENGTH + BATTER_STATE_DIFF,
    "m7": STADIUM_COL + WEATHER_COLS + TEAM_STRENGTH + BATTER_STATE_DIFF,
}

TARGET = "is_home_win"


def build_preprocessor(numeric_cols, categorical_cols):
    transformers = []
    if numeric_cols:
        transformers.append(("num", Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("sc",  StandardScaler())
        ]), numeric_cols))
    if categorical_cols:
        transformers.append(("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("oh",  OneHotEncoder(handle_unknown="ignore", sparse_output=False))
        ]), categorical_cols))
    return ColumnTransformer(transformers, remainder="drop")


def evaluate(y_true, p_hat):
    y_pred = (p_hat >= 0.5).astype(int)
    return {
        "n": len(y_true),
        "accuracy": accuracy_score(y_true, y_pred),
        "auc": roc_auc_score(y_true, p_hat) if y_true.nunique() > 1 else float("nan"),
        "brier": brier_score_loss(y_true, p_hat),
        "log_loss": log_loss(y_true, p_hat, labels=[0, 1]),
    }


# ============================================================================
# Ablation m1..m7 with logistic regression
# ============================================================================
print("\n" + "=" * 70)
print("ABLATION: m1..m7 (logistic regression)")
print("=" * 70)

ablation_rows = []
trainval = pd.concat([train, valid], ignore_index=True)

for mname, feats in FEATURE_GROUPS.items():
    if mname == "m1":
        # intercept-only baseline = mean of trainval target
        p_const = trainval[TARGET].mean()
        for split_name, split_df in [("train", train), ("valid", valid), ("test", test)]:
            y = split_df[TARGET]
            p = np.full(len(y), p_const)
            metrics = evaluate(y, p)
            metrics.update({"model": mname, "split": split_name})
            ablation_rows.append(metrics)
        continue

    feats_used = [f for f in feats if f in df.columns]
    cat = [f for f in feats_used if f in STADIUM_COL]
    num = [f for f in feats_used if f not in cat]
    if not feats_used:
        # m3 with no weather data -> skip cleanly
        for split_name, split_df in [("train", train), ("valid", valid), ("test", test)]:
            y = split_df[TARGET]
            p = np.full(len(y), trainval[TARGET].mean())
            metrics = evaluate(y, p)
            metrics.update({"model": mname, "split": split_name, "note": "no-weather-fallback"})
            ablation_rows.append(metrics)
        continue

    pre = build_preprocessor(num, cat)
    pipe = Pipeline([
        ("pre", pre),
        ("clf", LogisticRegression(max_iter=2000, C=1.0, solver="liblinear"))
    ])
    X_tv = trainval[feats_used]
    y_tv = trainval[TARGET]
    pipe.fit(X_tv, y_tv)

    for split_name, split_df in [("train", train), ("valid", valid), ("test", test)]:
        y = split_df[TARGET]
        p = pipe.predict_proba(split_df[feats_used])[:, 1]
        metrics = evaluate(y, p)
        metrics.update({"model": mname, "split": split_name, "n_feats": len(feats_used)})
        ablation_rows.append(metrics)

ablation = pd.DataFrame(ablation_rows)
ablation.to_csv(EVAL / "results_ablation.csv", index=False)
print(ablation[ablation["split"] == "test"].sort_values("auc", ascending=False).to_string(index=False))


# ============================================================================
# Algorithm comparison on m7 full feature set
# ============================================================================
print("\n" + "=" * 70)
print("ALGORITHMS @ m7 full features (no weather in this sandbox run)")
print("=" * 70)

m7_feats = [f for f in FEATURE_GROUPS["m7"] if f in df.columns]
m7_cat = [f for f in m7_feats if f in STADIUM_COL]
m7_num = [f for f in m7_feats if f not in m7_cat]

X_train = trainval[m7_feats]
y_train = trainval[TARGET]
X_test  = test[m7_feats]
y_test  = test[TARGET]

models = {
    "logit": LogisticRegression(max_iter=2000, C=1.0, solver="liblinear"),
    "glmnet_l2":   LogisticRegression(penalty="l2", C=0.3, max_iter=2000, solver="liblinear"),
    "glmnet_elastic": LogisticRegression(penalty="elasticnet", C=0.5, l1_ratio=0.5,
                                         max_iter=2000, solver="saga"),
    "rf": RandomForestClassifier(n_estimators=400, max_depth=6, min_samples_leaf=5,
                                 random_state=RNG, n_jobs=-1),
    "xgb": xgb.XGBClassifier(
        n_estimators=400, max_depth=3, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=1.0,
        eval_metric="logloss", random_state=RNG, n_jobs=-1, tree_method="hist",
    ),
    "lgb": lgb.LGBMClassifier(
        n_estimators=400, max_depth=-1, num_leaves=15, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_samples=10,
        reg_alpha=0.1, reg_lambda=1.0, random_state=RNG, n_jobs=-1, verbosity=-1,
    ),
}

algo_rows = []
for name, clf in models.items():
    pre = build_preprocessor(m7_num, m7_cat)
    pipe = Pipeline([("pre", pre), ("clf", clf)])
    pipe.fit(X_train, y_train)
    p = pipe.predict_proba(X_test)[:, 1]
    metrics = evaluate(y_test, p)
    metrics["model"] = name
    algo_rows.append(metrics)
    print(f"  {name:18s} auc={metrics['auc']:.3f}  acc={metrics['accuracy']:.3f}  brier={metrics['brier']:.3f}  ll={metrics['log_loss']:.3f}")

algo_df = pd.DataFrame(algo_rows).sort_values("auc", ascending=False)
algo_df.to_csv(EVAL / "results_algos.csv", index=False)


# ============================================================================
# Tune top-2 algorithms with TimeSeriesSplit CV
# ============================================================================
print("\n" + "=" * 70)
print("TUNING top-2 algorithms (TimeSeriesSplit n=5)")
print("=" * 70)

tscv = TimeSeriesSplit(n_splits=5)

# lean grids — sandbox-friendly. n_jobs=1 INSIDE each fit to avoid nested-
# parallelism thrashing (4 outer workers × 4 inner threads = 16 on 4 cores).
xgb_grid = {
    "clf__n_estimators": [200, 400],
    "clf__max_depth": [2, 3, 4],
    "clf__learning_rate": [0.03, 0.05, 0.1],
}
xgb_pipe = Pipeline([
    ("pre", build_preprocessor(m7_num, m7_cat)),
    ("clf", xgb.XGBClassifier(
        eval_metric="logloss", random_state=RNG, n_jobs=1,
        tree_method="hist", reg_alpha=0.1, reg_lambda=1.0,
        subsample=0.8, colsample_bytree=0.8,
    )),
])
xgb_search = GridSearchCV(xgb_pipe, xgb_grid, cv=tscv, scoring="roc_auc", n_jobs=4)
xgb_search.fit(X_train, y_train)
print(f"  best xgb: AUC={xgb_search.best_score_:.3f}  params={xgb_search.best_params_}")

lgb_grid = {
    "clf__n_estimators": [200, 400],
    "clf__num_leaves": [8, 15, 31],
    "clf__learning_rate": [0.03, 0.05, 0.1],
}
lgb_pipe = Pipeline([
    ("pre", build_preprocessor(m7_num, m7_cat)),
    ("clf", lgb.LGBMClassifier(
        subsample=0.8, colsample_bytree=0.8, min_child_samples=10,
        reg_alpha=0.1, reg_lambda=1.0,
        random_state=RNG, n_jobs=1, verbosity=-1,
    )),
])
lgb_search = GridSearchCV(lgb_pipe, lgb_grid, cv=tscv, scoring="roc_auc", n_jobs=4)
lgb_search.fit(X_train, y_train)
print(f"  best lgb: AUC={lgb_search.best_score_:.3f}  params={lgb_search.best_params_}")

elastic_grid = {
    "clf__C": [0.1, 0.3, 1.0, 3.0],
    "clf__l1_ratio": [0.2, 0.5, 0.8],
}
elastic_pipe = Pipeline([
    ("pre", build_preprocessor(m7_num, m7_cat)),
    ("clf", LogisticRegression(penalty="elasticnet", solver="saga", max_iter=5000,
                               random_state=RNG)),
])
elastic_search = GridSearchCV(elastic_pipe, elastic_grid, cv=tscv, scoring="roc_auc", n_jobs=4)
elastic_search.fit(X_train, y_train)
print(f"  best elastic: AUC={elastic_search.best_score_:.3f}  params={elastic_search.best_params_}")

# Also tune RandomForest (best default-AUC algorithm)
rf_grid = {
    "clf__n_estimators": [200, 400, 800],
    "clf__max_depth": [4, 6, 8, None],
    "clf__min_samples_leaf": [3, 5, 10],
}
rf_pipe = Pipeline([
    ("pre", build_preprocessor(m7_num, m7_cat)),
    ("clf", RandomForestClassifier(random_state=RNG, n_jobs=1)),
])
rf_search = GridSearchCV(rf_pipe, rf_grid, cv=tscv, scoring="roc_auc", n_jobs=4)
rf_search.fit(X_train, y_train)
print(f"  best rf: AUC={rf_search.best_score_:.3f}  params={rf_search.best_params_}")


# ============================================================================
# Final eval on holdout test set
# ============================================================================
print("\n" + "=" * 70)
print("HOLDOUT TEST EVAL")
print("=" * 70)

candidates = {
    "tuned_xgb":     xgb_search.best_estimator_,
    "tuned_lgb":     lgb_search.best_estimator_,
    "tuned_elastic": elastic_search.best_estimator_,
    "tuned_rf":      rf_search.best_estimator_,
}
final_rows = []
preds_for_calib = {}
for name, est in candidates.items():
    p = est.predict_proba(X_test)[:, 1]
    metrics = evaluate(y_test, p)
    metrics["model"] = name
    final_rows.append(metrics)
    preds_for_calib[name] = p
    print(f"  {name:15s} auc={metrics['auc']:.3f}  acc={metrics['accuracy']:.3f}  "
          f"brier={metrics['brier']:.3f}  log_loss={metrics['log_loss']:.3f}")

final_df = pd.DataFrame(final_rows).sort_values("auc", ascending=False)
final_df.to_csv(EVAL / "results_tuned.csv", index=False)
best_name = final_df.iloc[0]["model"]
best_est  = candidates[best_name]
print(f"\nWINNER: {best_name}  AUC={final_df.iloc[0]['auc']:.3f}")


# ============================================================================
# Calibration (Platt + Isotonic) on the winner
# ============================================================================
print("\n" + "=" * 70)
print("CALIBRATION on winner")
print("=" * 70)

from sklearn.base import clone
from sklearn.frozen import FrozenEstimator
best_est_train = clone(best_est)
best_est_train.fit(train[m7_feats], train[TARGET])
cal_sigmoid = CalibratedClassifierCV(FrozenEstimator(best_est_train), method="sigmoid")
cal_sigmoid.fit(valid[m7_feats], valid[TARGET])
p_cal = cal_sigmoid.predict_proba(X_test)[:, 1]
m_cal = evaluate(y_test, p_cal)
print(f"  calibrated (sigmoid): auc={m_cal['auc']:.3f}  brier={m_cal['brier']:.3f}  ll={m_cal['log_loss']:.3f}")
preds_for_calib["winner_calibrated"] = p_cal


# ============================================================================
# Plots
# ============================================================================
print("\n" + "=" * 70)
print("PLOTS")
print("=" * 70)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 1. AUC bar comparison
fig, ax = plt.subplots(figsize=(9, 5))
allres = pd.concat([
    algo_df.assign(family="default"),
    final_df.assign(family="tuned"),
], ignore_index=True)
allres = allres.sort_values("auc", ascending=True)
ax.barh(allres["model"] + " (" + allres["family"] + ")", allres["auc"])
ax.axvline(0.5, color="gray", linestyle="--", label="random")
ax.axvline(train[TARGET].mean(), color="red", linestyle=":", label=f"HFA prior={train[TARGET].mean():.3f}")
ax.set_xlabel("AUC (holdout test)")
ax.set_title("Algorithm comparison — CPBL 2024 home-win prediction")
ax.legend(loc="lower right")
fig.tight_layout()
fig.savefig(FIG / "model_comparison.png", dpi=120)
plt.close(fig)

# 2. Calibration curve
fig, ax = plt.subplots(figsize=(7, 6))
for name, p in preds_for_calib.items():
    frac_pos, mean_pred = calibration_curve(y_test, p, n_bins=8, strategy="quantile")
    ax.plot(mean_pred, frac_pos, marker="o", label=name)
ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="perfect")
ax.set_xlabel("Predicted probability")
ax.set_ylabel("Observed home-win frequency")
ax.set_title("Calibration curve (holdout test)")
ax.legend(loc="best", fontsize=8)
fig.tight_layout()
fig.savefig(FIG / "calibration.png", dpi=120)
plt.close(fig)

# 3. SHAP summary — supports any tree ensemble (RF, XGB, LGB)
try:
    import shap
    clf_in_pipe = best_est.named_steps["clf"]
    pre_in_pipe = best_est.named_steps["pre"]
    X_test_trans = pre_in_pipe.transform(X_test)
    feat_names = pre_in_pipe.get_feature_names_out()
    is_tree = isinstance(clf_in_pipe,
                          (xgb.XGBClassifier, lgb.LGBMClassifier, RandomForestClassifier))
    if is_tree:
        # Rename CJK stadium tokens to ASCII for plot legibility
        STAD_ASCII = {
            "樂天桃園": "Taoyuan", "洲際": "Taichung", "天母": "Tianmu",
            "新莊": "Xinzhuang", "澄清湖": "Chengqing", "臺南": "Tainan",
            "大巨蛋": "Dome", "其他": "Other",
        }
        feat_names = list(feat_names)
        for i, n in enumerate(feat_names):
            for cjk, eng in STAD_ASCII.items():
                n = n.replace(cjk, eng)
            n = n.replace("num__", "").replace("cat__", "")
            feat_names[i] = n
        explainer = shap.TreeExplainer(clf_in_pipe)
        sv = explainer.shap_values(X_test_trans)
        if isinstance(sv, list):
            sv_pos = sv[1]
        elif hasattr(sv, "ndim") and sv.ndim == 3:
            sv_pos = sv[:, :, 1]
        else:
            sv_pos = sv
        shap.summary_plot(sv_pos, X_test_trans, feature_names=feat_names,
                          show=False, max_display=15)
        plt.tight_layout()
        plt.savefig(FIG / "shap_summary.png", dpi=120, bbox_inches="tight")
        plt.close()
        print(f"  SHAP summary saved for {type(clf_in_pipe).__name__}")
except Exception as e:
    print(f"  SHAP skipped: {type(e).__name__}: {e}")

# ============================================================================
# Save final metrics JSON
# ============================================================================
final_metrics = {
    "n_train": len(train), "n_valid": len(valid), "n_test": len(test),
    "home_win_base_rate_train": float(train[TARGET].mean()),
    "winner": best_name,
    "winner_holdout": final_df.iloc[0].to_dict(),
    "calibrated_holdout": m_cal,
    "best_params": {
        "xgb": xgb_search.best_params_,
        "lgb": lgb_search.best_params_,
        "elastic": elastic_search.best_params_,
        "rf": rf_search.best_params_,
    },
}
(EVAL / "_final_metrics.json").write_text(
    json.dumps(final_metrics, indent=2, default=str), encoding="utf-8"
)
print(f"\nfinal_metrics: {EVAL / '_final_metrics.json'}")
print("DONE.")
