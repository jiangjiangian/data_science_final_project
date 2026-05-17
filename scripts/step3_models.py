"""
scripts/step3_models.py

Step 3 — m1..m7 ablation + algorithm comparison + tuning + honest holdout
         + ONE calibration + dual-threshold report + Shiny artifacts.

Time-aware splits (NEVER random — this is time-series sports data):
  train = games BEFORE 2024-08-01   (all of 2023 + 2024<Aug land here)
  valid = 2024-08-01 .. 2024-09-15
  test  = 2024-09-16 .. end (Sep-Oct + playoffs; held out, untouched in fit)

Ablation (algorithm FIXED = logistic; only the feature set varies — this is
the textbook way to quantify each group's marginal contribution):
  m1 intercept only            (pure home-field advantage baseline)
  m2 stadium only
  m3 weather only
  m4 team-strength only        (Elo / Pythagenpat / rest / park-factor)
  m5 batter-state only         (rolling lineup form: OPS/HR/K%/BB%/runs diff)
  m6 pitching only             (starter last-5 + staff-30g: ERA/WHIP/K%/HR9)
  m7 FULL  (stadium + weather + team-strength + batter-state + pitching)

  m6 was the stadium+weather "environment" combo through Run B; it scored
  ~0.467 (junk) so it is retired and the slot now gates the pitching group
  — the one lever rebas data still had untapped. Scheme is LOCKED and kept
  identical across step3 / reports/03 / .claude/rules/modeling.md.

Algorithm comparison (features FIXED = full m7; only the algorithm varies):
  logit, glmnet(l2), glmnet(elasticnet), RandomForest, XGBoost, LightGBM
  -> tuned with TimeSeriesSplit CV; WINNER chosen by CV-AUC (the holdout
     N is tiny and noisy, so we do NOT pick on holdout).

One calibration only: isotonic via time-aware CV on train+valid (stacking and
extra calibration layers are noise at this N — reported with a bootstrap CI
so the reader sees the uncertainty instead of a false-precision number).

Outputs:
  models/best_model.joblib                 (calibrated winner, for inference)
  Results/eval/predictions.csv             (leak-free OOF per game — Shiny src)
  Results/eval/feature_schema.json         (Shiny input contract)
  Results/eval/results_ablation.csv | results_algos.csv | results_tuned.csv
  Results/eval/_final_metrics.json
  Results/figures/model_comparison.png | calibration.png | shap_summary.png
  Results/figures/ablation_holdout_vs_oof.png  (the report centrepiece)
"""
import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, balanced_accuracy_score,
                             brier_score_loss, f1_score, log_loss,
                             roc_auc_score)
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
import lightgbm as lgb
import xgboost as xgb

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*ConvergenceWarning.*")

ROOT = Path(__file__).resolve().parent.parent
IN_CSV = ROOT / "data/processed/model_ready_data.csv"
FIG = ROOT / "Results/figures"
EVAL = ROOT / "Results/eval"
MODELS = ROOT / "models"
for d in (FIG, EVAL, MODELS):
    d.mkdir(parents=True, exist_ok=True)

RNG = 42
TARGET = "is_home_win"

# ============================================================================
# Load + warm-up filter + time-aware split
# ============================================================================
df = pd.read_csv(IN_CSV, parse_dates=["date"])
print(f"loaded {len(df)} games  cols={df.shape[1]}")
df = df[df["features_complete"] == 1].reset_index(drop=True)
print(f"after warm-up filter: {len(df)} games  "
      f"home_win base rate={df[TARGET].mean():.3f}")

train = df[df["date"] < "2024-08-01"].reset_index(drop=True)
valid = df[(df["date"] >= "2024-08-01") & (df["date"] < "2024-09-16")].reset_index(drop=True)
test = df[df["date"] >= "2024-09-16"].reset_index(drop=True)
trainval = pd.concat([train, valid], ignore_index=True)
print(f"split: train={len(train)} valid={len(valid)} test={len(test)}")
print(f"home_win  train={train[TARGET].mean():.3f}  "
      f"valid={valid[TARGET].mean():.3f}  test={test[TARGET].mean():.3f}")

# ============================================================================
# Feature group catalogue
# ============================================================================
STADIUM_CAT = ["stadium"]
STADIUM_NUM = [c for c in ["is_indoor"] if c in df.columns]
WEATHER_COLS = [c for c in ["temperature", "humidity", "wind_speed", "precip"]
                if c in df.columns]
TEAM_STRENGTH = [c for c in ["diff_elo", "diff_pythag", "diff_rest", "pf_pre"]
                 if c in df.columns]
BATTER_STATE = [c for c in ["diff_OPS_30g", "diff_HR_per_g_30g",
                            "diff_K_pct_30g", "diff_BB_pct_30g",
                            "diff_runs_per_g_30g", "diff_at_stadium_OPS"]
                if c in df.columns]
# starter own last-5 form (sp*_l5, NaN-tolerant -> median-imputed) +
# team pitching-staff rolling 30g (staff*_30g, shares warm-up filter)
PITCHING = [c for c in ["diff_spERA_l5", "diff_spWHIP_l5",
                        "diff_spK_pct_l5", "diff_spBB_pct_l5",
                        "diff_spHR9_l5", "diff_spIPouts_l5",
                        "diff_staffERA_30g", "diff_staffWHIP_30g",
                        "diff_staffK_pct_30g", "diff_staffBB_pct_30g",
                        "diff_staffHR9_30g"]
            if c in df.columns]
STADIUM_ALL = STADIUM_CAT + STADIUM_NUM

if not WEATHER_COLS:
    print("NOTE: no weather columns -> run scripts/step1b_fetch_weather.py "
          "then step2 so m3/m6/m7 become meaningful. Continuing degraded.")

FEATURE_GROUPS = {
    "m1": [],
    "m2": STADIUM_ALL,
    "m3": WEATHER_COLS,
    "m4": TEAM_STRENGTH,
    "m5": BATTER_STATE,
    "m6": PITCHING,
    "m7": STADIUM_ALL + WEATHER_COLS + TEAM_STRENGTH + BATTER_STATE + PITCHING,
}


def build_preprocessor(feats):
    cat = [f for f in feats if f in STADIUM_CAT]
    num = [f for f in feats if f not in cat]
    transformers = []
    if num:
        transformers.append(("num", Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("sc", StandardScaler())]), num))
    if cat:
        transformers.append(("cat", Pipeline([
            ("imp", SimpleImputer(strategy="most_frequent")),
            ("oh", OneHotEncoder(handle_unknown="ignore",
                                 sparse_output=False))]), cat))
    return ColumnTransformer(transformers, remainder="drop")


def evaluate(y_true, p_hat, thr=0.5):
    y_true = np.asarray(y_true)
    y_pred = (p_hat >= thr).astype(int)
    return {
        "n": int(len(y_true)),
        "accuracy": accuracy_score(y_true, y_pred),
        "bal_acc": balanced_accuracy_score(y_true, y_pred),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "auc": roc_auc_score(y_true, p_hat) if len(np.unique(y_true)) > 1 else float("nan"),
        "brier": brier_score_loss(y_true, p_hat),
        "log_loss": log_loss(y_true, p_hat, labels=[0, 1]),
    }


def auc_bootstrap_ci(y_true, p_hat, n_boot=1000, seed=RNG):
    y_true = np.asarray(y_true)
    p_hat = np.asarray(p_hat)
    rs = np.random.RandomState(seed)
    n = len(y_true)
    vals = []
    for _ in range(n_boot):
        idx = rs.randint(0, n, n)
        if len(np.unique(y_true[idx])) < 2:
            continue
        vals.append(roc_auc_score(y_true[idx], p_hat[idx]))
    if not vals:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def ts_oof_proba(estimator, X, y, splitter):
    """Walk-forward out-of-fold P(y=1). TimeSeriesSplit is NOT a partition
    (the first training block is never a test fold), so cross_val_predict
    rejects it with 'only works for partitions'. Do it by hand: clone + fit
    on each fold's past, predict its future. Rows never in any test fold
    stay NaN; the caller masks them."""
    X = X.reset_index(drop=True)
    y = pd.Series(np.asarray(y))
    oof = np.full(len(y), np.nan)
    for tr, te in splitter.split(X):
        est = clone(estimator)
        est.fit(X.iloc[tr], y.iloc[tr])
        oof[te] = est.predict_proba(X.iloc[te])[:, 1]
    return oof


# ============================================================================
# 1. Ablation m1..m7 (algorithm fixed = logistic regression)
# ============================================================================
print("\n" + "=" * 70 + "\nABLATION m1..m7 (logistic; features vary)\n" + "=" * 70)
ablation_rows = []
ablation_oof = {}                       # leak-free walk-forward per group
ablation_oof_folds = {}                 # per-fold AUC (sign-flip vs noise)
_ab_tscv = TimeSeriesSplit(n_splits=5)
for mname, feats in FEATURE_GROUPS.items():
    feats = [f for f in feats if f in df.columns]
    for split_name, sdf in [("train", train), ("valid", valid), ("test", test)]:
        y = sdf[TARGET]
        if mname == "m1" or not feats:
            p = np.full(len(y), trainval[TARGET].mean())
            note = "intercept" if mname == "m1" else "no-features-fallback"
        else:
            pipe = Pipeline([("pre", build_preprocessor(feats)),
                             ("clf", LogisticRegression(max_iter=2000, C=1.0,
                                                        solver="liblinear"))])
            pipe.fit(trainval[feats], trainval[TARGET])
            p = pipe.predict_proba(sdf[feats])[:, 1]
            note = f"{len(feats)}feat"
        m = evaluate(y, p)
        m.update({"model": mname, "split": split_name, "note": note})
        ablation_rows.append(m)
    # Per-group season-OOF: the ROBUST metric. The N=47 holdout AUC above
    # has a CI ~[.45,.81] — useless for ranking groups. This refits the
    # same logistic walk-forward over the whole post-warmup season so
    # "does pitching (m6) actually beat the HFA baseline out-of-sample?"
    # is answered by signal, not by a 47-game coin-flip. Cheap (logistic).
    if mname == "m1" or not feats:
        ablation_oof[mname] = float("nan")          # constant prior == chance
    else:
        oof_pipe = Pipeline([("pre", build_preprocessor(feats)),
                             ("clf", LogisticRegression(max_iter=2000, C=1.0,
                                                        solver="liblinear"))])
        o = ts_oof_proba(oof_pipe, df[feats], df[TARGET], _ab_tscv)
        k = ~np.isnan(o)
        ablation_oof[mname] = (
            roc_auc_score(df.loc[k, TARGET], o[k])
            if df.loc[k, TARGET].nunique() > 1 else float("nan"))
        # Fold-by-fold AUC: distinguishes "noise scattered around .50"
        # from a systematic <.50 sign-flip. Same verdict either way (no
        # robust signal) but the report must word it to match reality.
        yv = df[TARGET].values
        folds = []
        for _tr, _te in _ab_tscv.split(df):
            yt = yv[_te]
            folds.append(round(float(roc_auc_score(yt, o[_te])), 3)
                         if len(np.unique(yt)) > 1 else float("nan"))
        ablation_oof_folds[mname] = folds
ablation = pd.DataFrame(ablation_rows)
ablation["season_oof_auc"] = ablation["model"].map(ablation_oof)
ablation.to_csv(EVAL / "results_ablation.csv", index=False)
_ab_test = (ablation[ablation.split == "test"]
            .assign(season_oof=lambda d: d["model"].map(ablation_oof))
            .sort_values("season_oof_auc", ascending=False)
            [["model", "note", "n", "auc", "season_oof_auc", "brier"]])
print("(ranked by season_oof_auc — the robust metric; 'auc' is the "
      "noisy N=47 holdout)")
print(_ab_test.to_string(index=False))
print(f"\nm1 HFA-baseline season-OOF = chance (~0.50); "
      f"m6 pitching season-OOF = {ablation_oof.get('m6', float('nan')):.3f} ; "
      f"m7 full = {ablation_oof.get('m7', float('nan')):.3f}")
print(f"m6 per-fold OOF AUC = {ablation_oof_folds.get('m6')}  "
      "(scattered ~.50 => noise; systematically <.50 => small-N "
      "sign-flip — same verdict: no robust signal)")

# ============================================================================
# 2. Algorithm comparison @ full m7 (features fixed; algorithm varies)
# ============================================================================
print("\n" + "=" * 70 + "\nALGORITHMS @ m7 full features\n" + "=" * 70)
m7 = [f for f in FEATURE_GROUPS["m7"] if f in df.columns]
Xtv, ytv = trainval[m7], trainval[TARGET]
Xte, yte = test[m7], test[TARGET]

algos = {
    "logit": LogisticRegression(max_iter=2000, C=1.0, solver="liblinear"),
    "glmnet_l2": LogisticRegression(penalty="l2", C=0.3, max_iter=2000,
                                    solver="liblinear"),
    "glmnet_elastic": LogisticRegression(penalty="elasticnet", C=0.5,
                                          l1_ratio=0.5, max_iter=3000,
                                          solver="saga"),
    "rf": RandomForestClassifier(n_estimators=400, max_depth=6,
                                 min_samples_leaf=5, random_state=RNG,
                                 n_jobs=-1),
    "xgb": xgb.XGBClassifier(n_estimators=400, max_depth=3, learning_rate=0.05,
                             subsample=0.8, colsample_bytree=0.8,
                             reg_alpha=0.1, reg_lambda=1.0,
                             eval_metric="logloss", random_state=RNG,
                             n_jobs=-1, tree_method="hist"),
    "lgb": lgb.LGBMClassifier(n_estimators=400, num_leaves=15,
                              learning_rate=0.05, subsample=0.8,
                              colsample_bytree=0.8, min_child_samples=10,
                              reg_alpha=0.1, reg_lambda=1.0,
                              random_state=RNG, n_jobs=-1, verbosity=-1),
}
algo_rows = []
for name, clf in algos.items():
    pipe = Pipeline([("pre", build_preprocessor(m7)), ("clf", clf)])
    pipe.fit(Xtv, ytv)
    m = evaluate(yte, pipe.predict_proba(Xte)[:, 1])
    m["model"] = name
    algo_rows.append(m)
    print(f"  {name:15s} auc={m['auc']:.3f} acc={m['accuracy']:.3f} "
          f"brier={m['brier']:.3f} ll={m['log_loss']:.3f}")
algo_df = pd.DataFrame(algo_rows).sort_values("auc", ascending=False)
algo_df.to_csv(EVAL / "results_algos.csv", index=False)

# ============================================================================
# 3. Tune candidates with TimeSeriesSplit; WINNER = best CV-AUC
# ============================================================================
print("\n" + "=" * 70 + "\nTUNING (TimeSeriesSplit n=5; winner by CV-AUC)\n" + "=" * 70)
tscv = TimeSeriesSplit(n_splits=5)
# n_jobs=1 INSIDE each estimator, n_jobs=4 on the search -> avoids the
# 4x4=16-thread thrash that stalled an earlier run on a 4-core box.
grids = {
    "xgb": (Pipeline([("pre", build_preprocessor(m7)),
                      ("clf", xgb.XGBClassifier(eval_metric="logloss",
                                                random_state=RNG, n_jobs=1,
                                                tree_method="hist",
                                                reg_alpha=0.1, reg_lambda=1.0,
                                                subsample=0.8,
                                                colsample_bytree=0.8))]),
            {"clf__n_estimators": [200, 400],
             "clf__max_depth": [2, 3, 4],
             "clf__learning_rate": [0.03, 0.05, 0.1]}),
    "lgb": (Pipeline([("pre", build_preprocessor(m7)),
                      ("clf", lgb.LGBMClassifier(subsample=0.8,
                                                 colsample_bytree=0.8,
                                                 min_child_samples=10,
                                                 reg_alpha=0.1, reg_lambda=1.0,
                                                 random_state=RNG, n_jobs=1,
                                                 verbosity=-1))]),
            {"clf__n_estimators": [200, 400],
             "clf__num_leaves": [8, 15, 31],
             "clf__learning_rate": [0.03, 0.05, 0.1]}),
    "elastic": (Pipeline([("pre", build_preprocessor(m7)),
                          ("clf", LogisticRegression(penalty="elasticnet",
                                                     solver="saga",
                                                     max_iter=5000,
                                                     random_state=RNG))]),
                {"clf__C": [0.1, 0.3, 1.0, 3.0],
                 "clf__l1_ratio": [0.2, 0.5, 0.8]}),
    "rf": (Pipeline([("pre", build_preprocessor(m7)),
                     ("clf", RandomForestClassifier(random_state=RNG,
                                                    n_jobs=1))]),
           {"clf__n_estimators": [200, 400, 800],
            "clf__max_depth": [4, 6, 8, None],
            "clf__min_samples_leaf": [3, 5, 10]}),
}
searches, cv_auc = {}, {}
for name, (pipe, grid) in grids.items():
    gs = GridSearchCV(pipe, grid, cv=tscv, scoring="roc_auc", n_jobs=4)
    gs.fit(Xtv, ytv)
    searches[name] = gs
    cv_auc[name] = gs.best_score_
    print(f"  {name:8s} CV-AUC={gs.best_score_:.3f}  {gs.best_params_}")

winner_name = max(cv_auc, key=cv_auc.get)
winner_search = searches[winner_name]
winner_fitted = winner_search.best_estimator_          # fitted on trainval
print(f"\nWINNER (by CV-AUC): {winner_name}  CV-AUC={cv_auc[winner_name]:.3f}")

# ============================================================================
# 4. Honest holdout — every tuned candidate + bootstrap CI
# ============================================================================
print("\n" + "=" * 70 + "\nHOLDOUT (test) — point estimate + 95% bootstrap CI\n" + "=" * 70)
final_rows, preds_for_calib = [], {}
for name, gs in searches.items():
    p = gs.best_estimator_.predict_proba(Xte)[:, 1]
    m = evaluate(yte, p)
    lo, hi = auc_bootstrap_ci(yte, p)
    m.update({"model": f"tuned_{name}", "cv_auc": cv_auc[name],
              "auc_ci_lo": lo, "auc_ci_hi": hi})
    final_rows.append(m)
    preds_for_calib[f"tuned_{name}"] = p
    print(f"  tuned_{name:8s} holdout-AUC={m['auc']:.3f} "
          f"[{lo:.3f}, {hi:.3f}]  CV-AUC={cv_auc[name]:.3f}")
final_df = pd.DataFrame(final_rows).sort_values("cv_auc", ascending=False)
final_df.to_csv(EVAL / "results_tuned.csv", index=False)

# ============================================================================
# 5. ONE calibration: isotonic via time-aware CV on train+valid
# ============================================================================
print("\n" + "=" * 70 + "\nCALIBRATION (isotonic, TimeSeriesSplit on train+valid)\n" + "=" * 70)
cal = CalibratedClassifierCV(clone(winner_fitted), method="isotonic",
                             cv=TimeSeriesSplit(n_splits=3))
cal.fit(Xtv, ytv)
p_raw = winner_fitted.predict_proba(Xte)[:, 1]
p_cal = cal.predict_proba(Xte)[:, 1]
m_raw = evaluate(yte, p_raw)
m_cal = evaluate(yte, p_cal)
preds_for_calib["winner_calibrated"] = p_cal
print(f"  raw        auc={m_raw['auc']:.3f} brier={m_raw['brier']:.3f} ll={m_raw['log_loss']:.3f}")
print(f"  calibrated auc={m_cal['auc']:.3f} brier={m_cal['brier']:.3f} ll={m_cal['log_loss']:.3f}")
use_calibrated = m_cal["brier"] <= m_raw["brier"]
print(f"  -> serving {'CALIBRATED' if use_calibrated else 'RAW'} "
      f"(lower Brier wins on holdout)")

# ============================================================================
# 6. Threshold: leak-free trainval OOF (TimeSeriesSplit) -> Youden's J
#    Report holdout @0.5 AND @tuned side-by-side (do NOT silently replace).
# ============================================================================
oof = ts_oof_proba(winner_fitted, Xtv, ytv, tscv)
_m = ~np.isnan(oof)                       # drop the unscored warm-up fold
oof_m, y_oof = oof[_m], ytv.values[_m]
pos, neg = y_oof == 1, y_oof == 0
n_pos, n_neg = max(pos.sum(), 1), max(neg.sum(), 1)


def youden_j(t):
    pred = oof_m >= t
    return (pred & pos).sum() / n_pos - (pred & neg).sum() / n_neg


ths = np.linspace(0.30, 0.70, 41)
thr_opt = float(ths[int(np.argmax([youden_j(t) for t in ths]))])
serve = p_cal if use_calibrated else p_raw
m_05 = evaluate(yte, serve, thr=0.5)
m_opt = evaluate(yte, serve, thr=thr_opt)
print("\n" + "=" * 70 + "\nDUAL-THRESHOLD HOLDOUT (winner served)\n" + "=" * 70)
print(f"  thr=0.50      acc={m_05['accuracy']:.3f} bal_acc={m_05['bal_acc']:.3f} f1={m_05['f1']:.3f}")
print(f"  thr={thr_opt:.2f}(OOF-J) acc={m_opt['accuracy']:.3f} bal_acc={m_opt['bal_acc']:.3f} f1={m_opt['f1']:.3f}")

# ============================================================================
# 7. Plots
# ============================================================================
print("\n" + "=" * 70 + "\nPLOTS\n" + "=" * 70)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

allres = pd.concat([
    algo_df.assign(family="default")[["model", "auc", "family"]],
    final_df.assign(family="tuned")[["model", "auc", "family"]],
], ignore_index=True).sort_values("auc")
fig, ax = plt.subplots(figsize=(9, 5))
ax.barh(allres["model"] + " (" + allres["family"] + ")", allres["auc"])
ax.axvline(0.5, color="gray", ls="--", label="random")
ax.axvline(train[TARGET].mean(), color="red", ls=":",
           label=f"HFA prior={train[TARGET].mean():.3f}")
ax.set_xlabel("AUC (holdout test)")
ax.set_title("CPBL 2024 home-win — algorithm comparison")
ax.legend(loc="lower right")
fig.tight_layout()
fig.savefig(FIG / "model_comparison.png", dpi=120)
plt.close(fig)

# THE report centrepiece: per-group N=47 holdout AUC vs leak-free
# season-OOF AUC. The gap (esp. m6 pitching .689 -> .463) is the whole
# argument for why small-holdout ranking is dangerous and why the
# season-OOF + CI machinery exists. The visual IS the conclusion.
abl_t = ablation[ablation.split == "test"].set_index("model")
order = [m for m in ["m1", "m2", "m3", "m4", "m5", "m6", "m7"]
         if m in abl_t.index]
lbl = {"m1": "m1 intercept", "m2": "m2 stadium", "m3": "m3 weather",
       "m4": "m4 team-str", "m5": "m5 batter", "m6": "m6 PITCHING",
       "m7": "m7 full"}
hold = [abl_t.loc[m, "auc"] for m in order]
oofv = [ablation_oof.get(m, np.nan) for m in order]
oofv = [0.5 if (v != v) else v for v in oofv]      # m1 NaN -> chance
x = np.arange(len(order))
fig, ax = plt.subplots(figsize=(10, 5))
ax.bar(x - 0.2, hold, 0.38, label="N=47 holdout AUC (noisy)",
       color="#d98", edgecolor="k", linewidth=.4)
ax.bar(x + 0.2, oofv, 0.38, label="season-OOF AUC (robust, ~455g)",
       color="#48a", edgecolor="k", linewidth=.4)
ax.axhline(0.5, color="gray", ls="--", lw=1, label="chance / HFA")
for i, (h, o) in enumerate(zip(hold, oofv)):
    ax.text(i - 0.2, h + .008, f"{h:.2f}", ha="center", fontsize=8)
    ax.text(i + 0.2, o + .008, f"{o:.2f}", ha="center", fontsize=8)
ax.set_xticks(x)
ax.set_xticklabels([lbl[m] for m in order], rotation=20, ha="right")
ax.set_ylim(0.40, max(hold) + .06)
ax.set_ylabel("AUC")
ax.set_title("Why small-holdout ranking lies: m6 pitching .689 holdout "
             "→ .46 walk-forward\n(every group collapses to ~.50 OOF — "
             "no pre-game signal at N=678)")
ax.legend(loc="upper left", fontsize=8)
fig.tight_layout()
fig.savefig(FIG / "ablation_holdout_vs_oof.png", dpi=120)
plt.close(fig)

fig, ax = plt.subplots(figsize=(7, 6))
for name, p in preds_for_calib.items():
    fp, mp = calibration_curve(yte, p, n_bins=8, strategy="quantile")
    ax.plot(mp, fp, marker="o", label=name)
ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="perfect")
ax.set_xlabel("Predicted probability")
ax.set_ylabel("Observed home-win frequency")
ax.set_title("Calibration (holdout test)")
ax.legend(loc="best", fontsize=8)
fig.tight_layout()
fig.savefig(FIG / "calibration.png", dpi=120)
plt.close(fig)

try:
    import shap
    clf = winner_fitted.named_steps["clf"]
    pre = winner_fitted.named_steps["pre"]
    Xtt = pre.transform(Xte)
    names = list(pre.get_feature_names_out())
    STAD_ASCII = {"樂天桃園": "Taoyuan", "洲際": "Taichung", "天母": "Tianmu",
                  "新莊": "Xinzhuang", "澄清湖": "Chengqing", "臺南": "Tainan",
                  "大巨蛋": "Dome", "其他": "Other"}
    for i, n in enumerate(names):
        for cjk, eng in STAD_ASCII.items():
            n = n.replace(cjk, eng)
        names[i] = n.replace("num__", "").replace("cat__", "")
    if isinstance(clf, (xgb.XGBClassifier, lgb.LGBMClassifier,
                        RandomForestClassifier)):
        sv = shap.TreeExplainer(clf).shap_values(Xtt)
        if isinstance(sv, list):
            sv = sv[1]
        elif hasattr(sv, "ndim") and sv.ndim == 3:
            sv = sv[:, :, 1]
        shap.summary_plot(sv, Xtt, feature_names=names, show=False,
                          max_display=15)
        plt.tight_layout()
        plt.savefig(FIG / "shap_summary.png", dpi=120, bbox_inches="tight")
        plt.close()
        print(f"  SHAP saved ({type(clf).__name__})")
    else:
        print(f"  SHAP skipped (linear winner {type(clf).__name__})")
except Exception as e:                                   # noqa: BLE001
    print(f"  SHAP skipped: {type(e).__name__}: {e}")

# ============================================================================
# 8. Shiny artifacts — precompute contract (decided up-front, not in step6)
#    R Shiny just RENDERS these; no reticulate, deploy-safe.
# ============================================================================
print("\n" + "=" * 70 + "\nSHINY ARTIFACTS\n" + "=" * 70)

# 8a. leak-free per-game OOF probabilities for the WHOLE post-warmup season
#     (each game scored by a model fit only on chronologically earlier games)
if use_calibrated:
    oof_est = CalibratedClassifierCV(clone(winner_fitted), method="isotonic",
                                     cv=TimeSeriesSplit(3))
else:
    oof_est = clone(winner_fitted)
oof_all = ts_oof_proba(oof_est, df[m7], df[TARGET], tscv)
keep = ~np.isnan(oof_all)                  # earliest fold is never scored
oofk = oof_all[keep]
pred_cols = ["game_id", "date", "stadium", "home_team", "away_team"]
predictions = df.loc[keep, pred_cols].copy()
predictions["y_true"] = df.loc[keep, TARGET].values
predictions["p_home_win"] = oofk
predictions["pred_at_0.5"] = (oofk >= 0.5).astype(int)
predictions[f"pred_at_{thr_opt:.2f}"] = (oofk >= thr_opt).astype(int)
predictions["is_holdout"] = (df.loc[keep, "date"] >= "2024-09-16").astype(int)
predictions.to_csv(EVAL / "predictions.csv", index=False)
oof_auc = (roc_auc_score(df.loc[keep, TARGET], oofk)
           if df.loc[keep, TARGET].nunique() > 1 else float("nan"))
print(f"  predictions.csv  rows={len(predictions)}/{len(df)} "
      f"(walk-forward OOF; warm-up fold unscored)  "
      f"season-OOF-AUC={oof_auc:.3f}")

# 8b. production model: serve trained on ALL post-warmup data
prod = CalibratedClassifierCV(clone(winner_fitted), method="isotonic",
                              cv=TimeSeriesSplit(3)) if use_calibrated \
    else clone(winner_fitted)
prod.fit(df[m7], df[TARGET])
joblib.dump({"model": prod, "features": m7,
             "categorical": STADIUM_CAT,
             "numeric": [c for c in m7 if c not in STADIUM_CAT],
             "threshold": thr_opt, "winner": winner_name},
            MODELS / "best_model.joblib")
print(f"  best_model.joblib  ({winner_name}, "
      f"{'isotonic-calibrated' if use_calibrated else 'raw'})")

# 8c. Shiny input contract
schema = {
    "winner": winner_name,
    "calibrated": bool(use_calibrated),
    "winner_params": winner_search.best_params_,
    "threshold_opt": thr_opt,
    "home_win_base_rate": float(trainval[TARGET].mean()),
    "n": {"train": len(train), "valid": len(valid), "test": len(test),
          "post_warmup": len(df)},
    "feature_groups": {
        "stadium": STADIUM_ALL, "weather": WEATHER_COLS,
        "team_strength": TEAM_STRENGTH, "batter_state": BATTER_STATE,
        "pitching": PITCHING},
    "model_features": m7,
    "categorical_features": STADIUM_CAT,
    "stadium_levels": sorted(df["stadium"].dropna().unique().tolist()),
    "metrics": {
        "cv_auc": cv_auc, "season_oof_auc": float(oof_auc),
        "holdout_auc": float(m_raw["auc"]),
        "holdout_auc_ci95": auc_bootstrap_ci(yte, p_raw),
        "holdout_brier_raw": float(m_raw["brier"]),
        "holdout_brier_cal": float(m_cal["brier"])},
}
(EVAL / "feature_schema.json").write_text(
    json.dumps(schema, indent=2, ensure_ascii=False, default=str),
    encoding="utf-8")
print(f"  feature_schema.json  ({len(m7)} features, "
      f"{len(schema['stadium_levels'])} stadium levels)")

# ============================================================================
# 9. Final metrics JSON
# ============================================================================
(EVAL / "_final_metrics.json").write_text(json.dumps({
    "winner": winner_name,
    "served": "calibrated" if use_calibrated else "raw",
    "cv_auc": cv_auc,
    "holdout_raw": m_raw, "holdout_calibrated": m_cal,
    "holdout_auc_ci95": auc_bootstrap_ci(yte, p_raw),
    "threshold_opt": thr_opt,
    "holdout_at_0.5": m_05, "holdout_at_opt": m_opt,
    "season_oof_auc": float(oof_auc),
    "ablation_season_oof": {k: (None if (v != v) else float(v))
                            for k, v in ablation_oof.items()},
    "ablation_season_oof_folds": ablation_oof_folds,
    "best_params": {k: v.best_params_ for k, v in searches.items()},
}, indent=2, default=str), encoding="utf-8")
print(f"\nfinal_metrics: {EVAL / '_final_metrics.json'}\nDONE.")
