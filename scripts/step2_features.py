"""
scripts/step2_features.py

Step 2 - Feature engineering.

Inputs:  data/processed/games_with_weather.csv  (from step1b; preferred)
         data/processed/raw_games.csv           (step1 fallback if no weather)
Outputs: data/processed/model_ready_data.csv
         data/processed/park_factors.csv

Weather columns (temperature/humidity/wind_speed/wind_dir/precip/wind_dir_cat)
ride straight through to model_ready_data.csv when step1b has been run;
step3 imputes any NA and ablation m3/m4/m7 then become meaningful.

Feature groups produced (ALL strictly pre-game, no t-leakage):
  - Elo: home_elo_pre / away_elo_pre / diff_elo  (K=4, HFA=24, MoV-adjusted)
  - Pythagenpat (30-game rolling): home_pythag_30g / away_pythag_30g / diff_pythag
  - rest_days (cap=5): home_rest_days / away_rest_days / diff_rest
  - Batter-state team-game rolling (30g): OPS, AVG, SLG, OBP, ISO, K%, BB%, HR/G, R/G
  - Stadium-specific OPS: team_at_stadium_OPS_30g (per team in this stadium)
  - Park Factor (multi-stadium, leave-one-out time-aware): pf_pre
  - Diff features: home minus away for OPS/HR/K%/runs_per_game

Usage:  python3 scripts/step2_features.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WEATHER_CSV = ROOT / "data/processed/games_with_weather.csv"
RAW_CSV = ROOT / "data/processed/raw_games.csv"
IN_CSV = WEATHER_CSV if WEATHER_CSV.exists() else RAW_CSV
OUT_CSV = ROOT / "data/processed/model_ready_data.csv"
PF_CSV = ROOT / "data/processed/park_factors.csv"

K_FACTOR = 4
HFA_ELO = 24
MOV_ALPHA = 0.6
MOV_BETA = 2.2
INIT_RATING = 1500.0
PYTHAG_WINDOW = 30
PYTHAG_EXPONENT = 1.83
REST_CAP = 5
ROLL_WINDOW = 30
MIN_PA_FOR_OPS = 50    # cutoff before OPS rolling becomes trustworthy


# ============================================================================
# 1. Load & basic columns
# ============================================================================
df = pd.read_csv(IN_CSV, parse_dates=["date"])
df = df.sort_values(["date", "game_id"]).reset_index(drop=True)
WEATHER_FEATURES = [c for c in ["temperature", "humidity", "wind_speed",
                                "precip", "is_indoor"] if c in df.columns]
print(f"loaded {len(df)} games from {IN_CSV.name}")
print(f"weather features present: {WEATHER_FEATURES or 'NONE (run step1b)'}")


# ============================================================================
# 2. Elo (HFA + MoV adjusted, K=4)
# ============================================================================
def compute_elo(df_in):
    ratings = {}
    home_pre, away_pre = [], []
    home_post, away_post = [], []
    for h, a, hs, az in zip(df_in["home_team"], df_in["away_team"],
                            df_in["home_score"], df_in["away_score"]):
        h_pre = ratings.get(h, INIT_RATING)
        a_pre = ratings.get(a, INIT_RATING)
        home_pre.append(h_pre); away_pre.append(a_pre)
        expected_home = 1 / (1 + 10 ** ((a_pre - (h_pre + HFA_ELO)) / 400))
        if hs == az:
            home_post.append(h_pre); away_post.append(a_pre); continue
        actual_home = int(hs > az)
        diff_abs = abs(hs - az)
        rating_diff_winner = (h_pre + HFA_ELO - a_pre) if actual_home else (a_pre - h_pre - HFA_ELO)
        mov_mult = np.log(diff_abs + 1) * (MOV_BETA / (rating_diff_winner * MOV_ALPHA + MOV_BETA))
        mov_mult = max(0.5, min(4.0, mov_mult))
        delta = K_FACTOR * mov_mult * (actual_home - expected_home)
        h_post = h_pre + delta
        a_post = a_pre - delta
        home_post.append(h_post); away_post.append(a_post)
        ratings[h], ratings[a] = h_post, a_post
    df_in["home_elo_pre"] = home_pre
    df_in["away_elo_pre"] = away_pre
    df_in["home_elo_post"] = home_post
    df_in["away_elo_post"] = away_post
    return df_in


df = compute_elo(df)
df["diff_elo"] = df["home_elo_pre"] - df["away_elo_pre"]


# ============================================================================
# 3. Pythagenpat 30-game rolling — per-team perspective
# ============================================================================
def rolling_pythag(df_in, window=30, expo=1.83):
    long = []
    for i, r in df_in.iterrows():
        long.append({"game_id": r["game_id"], "date": r["date"], "side": "home",
                     "team": r["home_team"], "rs": r["home_score"], "ra": r["away_score"]})
        long.append({"game_id": r["game_id"], "date": r["date"], "side": "away",
                     "team": r["away_team"], "rs": r["away_score"], "ra": r["home_score"]})
    L = pd.DataFrame(long).sort_values(["team", "date", "game_id"]).reset_index(drop=True)
    pythag = []
    for team, g in L.groupby("team"):
        for i in range(len(g)):
            start = max(0, i - window)
            prev = g.iloc[start:i]
            if len(prev) < 5:
                pythag.append((g.iloc[i]["game_id"], g.iloc[i]["side"], np.nan))
            else:
                rs, ra = prev["rs"].sum(), prev["ra"].sum()
                if rs + ra == 0:
                    pythag.append((g.iloc[i]["game_id"], g.iloc[i]["side"], 0.5))
                else:
                    val = (rs ** expo) / (rs ** expo + ra ** expo)
                    pythag.append((g.iloc[i]["game_id"], g.iloc[i]["side"], val))
    P = pd.DataFrame(pythag, columns=["game_id", "side", "pythag_pre"])
    wide = P.pivot(index="game_id", columns="side", values="pythag_pre").reset_index()
    wide = wide.rename(columns={"home": "home_pythag_30g", "away": "away_pythag_30g"})
    return df_in.merge(wide, on="game_id", how="left")


df = rolling_pythag(df, window=PYTHAG_WINDOW, expo=PYTHAG_EXPONENT)
df["diff_pythag"] = df["home_pythag_30g"] - df["away_pythag_30g"]


# ============================================================================
# 4. rest_days  (cap 5)
# ============================================================================
def rest_days(df_in, cap=5):
    long = []
    for _, r in df_in.iterrows():
        long.append({"game_id": r["game_id"], "date": r["date"], "side": "home", "team": r["home_team"]})
        long.append({"game_id": r["game_id"], "date": r["date"], "side": "away", "team": r["away_team"]})
    L = pd.DataFrame(long).sort_values(["team", "date", "game_id"]).reset_index(drop=True)
    L["prev_date"] = L.groupby("team")["date"].shift(1)
    L["rest_days"] = (L["date"] - L["prev_date"]).dt.days.clip(upper=cap)
    wide = L.pivot(index="game_id", columns="side", values="rest_days").reset_index()
    wide = wide.rename(columns={"home": "home_rest_days", "away": "away_rest_days"})
    return df_in.merge(wide, on="game_id", how="left")


df = rest_days(df, cap=REST_CAP)
df["diff_rest"] = df["home_rest_days"] - df["away_rest_days"]


# ============================================================================
# 5. Team-game rolling 30-game batter-state features
# ============================================================================
def rolling_team_batter_state(df_in, window=ROLL_WINDOW):
    # long-form per game per side
    rows = []
    for _, r in df_in.iterrows():
        for side in ("home", "away"):
            other = "away" if side == "home" else "home"
            rs = r[f"{side}_score"]
            ra = r[f"{other}_score"]
            rows.append({
                "game_id": r["game_id"], "date": r["date"], "side": side,
                "team": r[f"{side}_team"], "stadium": r["stadium"],
                "PA": r[f"{side}_PA"], "AB": r[f"{side}_AB"],
                "H":  r[f"{side}_H"],  "HR": r[f"{side}_HR"],
                "2B": r[f"{side}_2B"], "3B": r[f"{side}_3B"],
                "BB": r[f"{side}_BB"], "HBP": r[f"{side}_HBP"],
                "SF": r[f"{side}_SF"], "SO": r[f"{side}_SO"],
                "rs": rs, "ra": ra,
            })
    L = pd.DataFrame(rows).sort_values(["team", "date", "game_id"]).reset_index(drop=True)

    stat_cols = ["PA", "AB", "H", "HR", "2B", "3B", "BB", "HBP", "SF", "SO", "rs"]
    feat_rows = []
    for team, g in L.groupby("team"):
        g = g.reset_index(drop=True)
        for i in range(len(g)):
            start = max(0, i - window)
            prev = g.iloc[start:i]
            row = {"game_id": g.iloc[i]["game_id"], "side": g.iloc[i]["side"]}
            if len(prev) < 5:
                for c in ["AVG", "OBP", "SLG", "OPS", "ISO", "K_pct", "BB_pct",
                          "HR_per_g", "runs_per_g"]:
                    row[c] = np.nan
            else:
                S = prev[stat_cols].sum()
                S_1B = S["H"] - S["2B"] - S["3B"] - S["HR"]
                ab_den = S["AB"]
                pa_den = S["PA"]
                obp_den = S["AB"] + S["BB"] + S["HBP"] + S["SF"]
                avg = S["H"] / ab_den if ab_den else np.nan
                obp = (S["H"] + S["BB"] + S["HBP"]) / obp_den if obp_den else np.nan
                slg = (S_1B + 2 * S["2B"] + 3 * S["3B"] + 4 * S["HR"]) / ab_den if ab_den else np.nan
                row["AVG"] = avg
                row["OBP"] = obp
                row["SLG"] = slg
                row["OPS"] = (obp + slg) if (obp is not None and slg is not None) else np.nan
                row["ISO"] = (slg - avg) if (slg is not None and avg is not None) else np.nan
                row["K_pct"] = S["SO"] / pa_den if pa_den else np.nan
                row["BB_pct"] = S["BB"] / pa_den if pa_den else np.nan
                row["HR_per_g"] = S["HR"] / len(prev)
                row["runs_per_g"] = S["rs"] / len(prev)
            feat_rows.append(row)
    F = pd.DataFrame(feat_rows)
    # pivot wide
    out = df_in.copy()
    for col in ["AVG", "OBP", "SLG", "OPS", "ISO", "K_pct", "BB_pct", "HR_per_g", "runs_per_g"]:
        h = F[F["side"] == "home"][["game_id", col]].rename(columns={col: f"home_{col}_30g"})
        a = F[F["side"] == "away"][["game_id", col]].rename(columns={col: f"away_{col}_30g"})
        out = out.merge(h, on="game_id", how="left").merge(a, on="game_id", how="left")
        out[f"diff_{col}_30g"] = out[f"home_{col}_30g"] - out[f"away_{col}_30g"]
    return out


df = rolling_team_batter_state(df, window=ROLL_WINDOW)


# ============================================================================
# 6. team_at_stadium_OPS_30g — per (team, stadium) rolling
# ============================================================================
def team_at_stadium_rolling(df_in, window=ROLL_WINDOW):
    rows = []
    for _, r in df_in.iterrows():
        for side in ("home", "away"):
            other = "away" if side == "home" else "home"
            rows.append({
                "game_id": r["game_id"], "date": r["date"], "side": side,
                "team": r[f"{side}_team"], "stadium": r["stadium"],
                "PA": r[f"{side}_PA"], "AB": r[f"{side}_AB"],
                "H":  r[f"{side}_H"],  "HR": r[f"{side}_HR"],
                "2B": r[f"{side}_2B"], "3B": r[f"{side}_3B"],
                "BB": r[f"{side}_BB"], "HBP": r[f"{side}_HBP"],
                "SF": r[f"{side}_SF"],
            })
    L = pd.DataFrame(rows).sort_values(["team", "stadium", "date", "game_id"]).reset_index(drop=True)
    out_rows = []
    for (team, stad), g in L.groupby(["team", "stadium"]):
        g = g.reset_index(drop=True)
        for i in range(len(g)):
            prev = g.iloc[max(0, i - window):i]
            if len(prev) < 3:
                ops = np.nan
            else:
                S = prev[["AB", "H", "2B", "3B", "HR", "BB", "HBP", "SF"]].sum()
                S_1B = S["H"] - S["2B"] - S["3B"] - S["HR"]
                ab_den = S["AB"]
                obp_den = S["AB"] + S["BB"] + S["HBP"] + S["SF"]
                if not ab_den or not obp_den:
                    ops = np.nan
                else:
                    obp = (S["H"] + S["BB"] + S["HBP"]) / obp_den
                    slg = (S_1B + 2 * S["2B"] + 3 * S["3B"] + 4 * S["HR"]) / ab_den
                    ops = obp + slg
            out_rows.append({"game_id": g.iloc[i]["game_id"], "side": g.iloc[i]["side"], "ops_at_stad": ops})
    F = pd.DataFrame(out_rows)
    h = F[F["side"] == "home"][["game_id", "ops_at_stad"]].rename(
        columns={"ops_at_stad": "home_at_stadium_OPS_30g"})
    a = F[F["side"] == "away"][["game_id", "ops_at_stad"]].rename(
        columns={"ops_at_stad": "away_at_stadium_OPS_30g"})
    return df_in.merge(h, on="game_id", how="left").merge(a, on="game_id", how="left")


df = team_at_stadium_rolling(df, window=ROLL_WINDOW)
df["diff_at_stadium_OPS"] = df["home_at_stadium_OPS_30g"] - df["away_at_stadium_OPS_30g"]


# ============================================================================
# 7. Park Factor — time-aware, leave-one-out
# ============================================================================
def park_factor_time_aware(df_in):
    """For each game g at stadium s and date t:
       pf_pre = avg_total_score_at_s_before_t / avg_total_score_at_other_stadiums_before_t
       Falls back to 1.0 if < 5 prior games at this stadium.
    """
    df_in = df_in.copy()
    df_in["pf_pre"] = np.nan
    for i, r in df_in.iterrows():
        prev = df_in.iloc[:i]   # all games strictly before this row (date-sorted)
        same_stad = prev[prev["stadium"] == r["stadium"]]
        other_stad = prev[prev["stadium"] != r["stadium"]]
        if len(same_stad) < 5 or len(other_stad) < 5:
            df_in.at[i, "pf_pre"] = 1.0
        else:
            df_in.at[i, "pf_pre"] = (same_stad["total_score"].mean() /
                                      other_stad["total_score"].mean())
    return df_in


df = park_factor_time_aware(df)

# also produce a stadium summary table
pf_summary = (df.groupby("stadium")
                .agg(n=("game_id", "size"),
                     home_win_rate=("is_home_win", "mean"),
                     avg_total_score=("total_score", "mean"),
                     pf_end_of_season=("pf_pre", "last"))
                .round(3).sort_values("avg_total_score", ascending=False))
pf_summary.to_csv(PF_CSV)
print(f"\npark_factors:\n{pf_summary}")


# ============================================================================
# 8. Day-of-week / month niceties
# ============================================================================
df["dow"] = df["date"].dt.day_name()
df["month"] = df["date"].dt.month
df["is_weekend"] = df["date"].dt.day_name().isin(["Saturday", "Sunday"]).astype(int)


# ============================================================================
# 9. Final hygiene + output
# ============================================================================
# fill rest_days NA (first game of season for each team) with median
for col in ["home_rest_days", "away_rest_days"]:
    df[col] = df[col].fillna(df[col].median())
df["diff_rest"] = df["home_rest_days"] - df["away_rest_days"]

print(f"\nfinal shape: {df.shape}")
print(f"home_win rate: {df['is_home_win'].mean():.3f}")

# How many rows have all rolling features available (after warm-up)?
roll_cols = [c for c in df.columns if c.endswith("_30g")]
df["features_complete"] = (df[roll_cols].isna().sum(axis=1) == 0).astype(int)
print(f"features_complete (no NA in 30g rolling): {df['features_complete'].sum()} / {len(df)}")

df.to_csv(OUT_CSV, index=False, encoding="utf-8")
print(f"\nwritten: {OUT_CSV}")
print("columns added in step 2:")
new_cols = [c for c in df.columns if c.endswith(("_pre", "_30g", "_pythag", "_rest_days", "_rest", "_elo", "_OPS")) or c in ("dow", "month", "is_weekend", "pf_pre", "diff_elo", "diff_pythag", "features_complete")]
for c in sorted(new_cols):
    print(f"  {c}")
