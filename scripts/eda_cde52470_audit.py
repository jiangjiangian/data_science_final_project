"""
scripts/eda_cde52470_audit.py
EDA audit on cde52470/data_science:data branch CSV mirror.
Outputs printable report; nothing committed via this script.
"""
import ast
import json
from pathlib import Path

import numpy as np
import pandas as pd

CSV = Path("data/raw/cde52470_mirror/cpbl_games_cleaned.csv")
JSON_FILE = Path("data/raw/cde52470_mirror/CPBL-2024-OpenData.json")

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


df = pd.read_csv(CSV)

section("1. Shape & dtypes")
print(f"shape = {df.shape}")
print(df.dtypes)

section("2. Missingness")
miss = df.isna().sum()
print(miss[miss > 0] if miss.sum() else "no NA in any column")

section("3. Target balance (home_win)")
print(df["home_win"].value_counts(normalize=True).rename("share"))
print(f"absolute counts: {df['home_win'].value_counts().to_dict()}")

section("4. Time range")
df["date"] = pd.to_datetime(df["date"])
print(f"min = {df['date'].min()}")
print(f"max = {df['date'].max()}")
print(f"unique dates = {df['date'].dt.date.nunique()}")
print(f"weekday distribution:")
print(df["date"].dt.day_name().value_counts())

section("5. Stadium roster")
print(df["stadium"].value_counts())
print(f"\ndistinct stadium names = {df['stadium'].nunique()}")

section("6. Team roster")
print("homeTeam:")
print(df["homeTeam"].value_counts())
print("\nawayTeam:")
print(df["awayTeam"].value_counts())
print(f"\nunion of teams ever appearing: {sorted(set(df['homeTeam']) | set(df['awayTeam']))}")

section("7. Home-team appearance by stadium (park-factor sanity)")
print(pd.crosstab(df["stadium"], df["homeTeam"]))

section("8. Score distributions")
print(df[["home_total_score", "away_total_score", "total_score"]].describe())
print(f"\nties (home==away): {(df['home_total_score']==df['away_total_score']).sum()}")

section("9. Home-win rate by stadium (raw park factor proxy)")
g = df.groupby("stadium").agg(
    n=("home_win", "size"),
    home_win_rate=("home_win", "mean"),
    avg_home_score=("home_total_score", "mean"),
    avg_away_score=("away_total_score", "mean"),
    avg_total=("total_score", "mean"),
).round(3).sort_values("home_win_rate", ascending=False)
print(g)

section("10. Home-win rate by home_team (team-strength proxy)")
print(
    df.groupby("homeTeam").agg(
        n=("home_win", "size"),
        home_win_rate=("home_win", "mean"),
    ).round(3).sort_values("home_win_rate", ascending=False)
)

section("11. Inning-score arrays parse + sanity")
df["awayScoresList"] = df["awayScores"].apply(ast.literal_eval)
df["homeScoresList"] = df["homeScores"].apply(ast.literal_eval)
df["away_innings_played"] = df["awayScoresList"].apply(len)
df["home_innings_played"] = df["homeScoresList"].apply(len)
print(df[["away_innings_played", "home_innings_played"]].describe())
print(f"\ngames with extra innings (>=10): {(df['home_innings_played'] >= 10).sum()}")
print(f"games with walk-off (away played more innings than home): "
      f"{(df['away_innings_played'] > df['home_innings_played']).sum()}")

# rebuild totals and cross-check
df["home_recomputed"] = df["homeScoresList"].apply(
    lambda lst: sum(int(s) for s in lst if str(s).lstrip("-").isdigit())
)
df["away_recomputed"] = df["awayScoresList"].apply(
    lambda lst: sum(int(s) for s in lst if str(s).lstrip("-").isdigit())
)
mismatch_home = (df["home_recomputed"] != df["home_total_score"]).sum()
mismatch_away = (df["away_recomputed"] != df["away_total_score"]).sum()
print(f"\ntotal mismatches home: {mismatch_home}, away: {mismatch_away}")

section("12. Team batting H/HR/etc — combined (home+away) sanity")
print(df[["H", "HR", "2B", "3B", "BB", "SO"]].describe())
print("\ncorrelation with total_score:")
print(df[["H", "HR", "2B", "3B", "BB", "SO", "total_score"]].corr()["total_score"].round(3))
print("\ncorrelation with home_win:")
print(df[["H", "HR", "2B", "3B", "BB", "SO", "home_win"]].corr()["home_win"].round(3))

section("13. Day-of-week effect on home win")
print(df.groupby(df["date"].dt.day_name())["home_win"].agg(["size", "mean"]).round(3))

section("14. Month-of-season trend")
print(df.groupby(df["date"].dt.month)["home_win"].agg(["size", "mean"]).round(3))

section("15. Game density timeline")
print(df.groupby(df["date"].dt.to_period("M")).size().rename("games_per_month"))

# --- Raw JSON structure peek ---
section("16. Raw JSON structure peek (first game)")
with open(JSON_FILE, encoding="utf-8") as f:
    raw = json.load(f)
print(f"raw is {type(raw).__name__}, length = {len(raw) if hasattr(raw, '__len__') else 'n/a'}")
first = raw[0] if isinstance(raw, list) else raw
print(f"top-level keys of game[0]: {list(first.keys())}")
if "homeBatterBox" in first and first["homeBatterBox"]:
    print(f"\nhomeBatterBox length: {len(first['homeBatterBox'])}")
    print(f"first batter keys: {list(first['homeBatterBox'][0].keys())}")
    print(f"\nfirst batter sample:")
    for k, v in list(first["homeBatterBox"][0].items())[:30]:
        print(f"  {k!r}: {v!r}")

# Count totals across raw JSON
section("17. Raw JSON game count vs cleaned CSV")
print(f"raw JSON games: {len(raw)}")
print(f"cleaned CSV games: {len(df)}")
print(f"dedup loss: {len(raw) - len(df)}")

print("\n--- audit complete ---")
