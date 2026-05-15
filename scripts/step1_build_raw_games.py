"""
scripts/step1_build_raw_games.py

Step 1.2-1.3:
  - Auto-discover EVERY rebas OpenData JSON under data/raw/ (any season).
    Drop in v0.1.0-2023.0 / v0.1.0-2023.1 / v0.1.0-2024 zips and this script
    picks them all up with no code change -> bigger N is the #1 accuracy
    lever (rebas has 2023.0 + 2023.1 + 2024; NO 2022 release exists).
  - Re-aggregate batterBox SEPARATELY for home and away (fixes the
    home+away combined bug found in cde52470 cleaned CSV)
  - Tag game_type (regular / challenge / series) from filename
  - Stadium normalize -> grouped levels (minor venues -> 其他)
  - Output canonical raw_games.csv

Usage:  python3 scripts/step1_build_raw_games.py
"""
import json
import hashlib
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_ROOT = ROOT / "data/raw"
OUT = ROOT / "data/processed"
OUT.mkdir(parents=True, exist_ok=True)
PROV = ROOT / "data/raw/_provenance"
PROV.mkdir(parents=True, exist_ok=True)


def discover_sources(raw_root: Path):
    """Find every CPBL-*OpenData*.json under data/raw/ and tag its game_type
    and season from the filename. Returns list[(game_type, season, path)]
    sorted by (season, type-rank) so the time-ordered build is stable."""
    type_rank = {"regular": 0, "challenge": 1, "series": 2}
    found = []
    for p in sorted(raw_root.rglob("CPBL-*OpenData*.json")):
        name = p.name
        if "Challenge" in name:
            gtype = "challenge"
        elif "TaiwanSeries" in name or "Series" in name:
            gtype = "series"
        else:
            gtype = "regular"
        m = re.search(r"CPBL-(\d{4})", name)
        season = int(m.group(1)) if m else 0
        found.append((gtype, season, p))
    found.sort(key=lambda t: (t[1], type_rank.get(t[0], 9)))
    return found


SOURCES = [(g, p) for (g, _s, p) in discover_sources(RAW_ROOT)]
if not SOURCES:
    raise FileNotFoundError(
        f"No CPBL-*OpenData*.json found under {RAW_ROOT}. "
        "Unzip rebas releases into data/raw/ first."
    )
print("discovered sources:")
for g, p in SOURCES:
    print(f"  [{g:9s}] {p.relative_to(ROOT)}")

# 11 stadiums in source -> 8 normalized levels.
# Bill-James park factor needs N>=20 ideally; the bottom 4 venues all have
# N<10 in 2024 -> collapse to "其他" to avoid overfit on tiny cells.
STADIUM_MAP = {
    "樂天桃園棒球場":     "樂天桃園",
    "臺中市洲際棒球場":   "洲際",
    "臺北市立天母棒球場": "天母",
    "新北市立新莊棒球場": "新莊",
    "澄清湖棒球場":       "澄清湖",
    "臺南市立棒球場":     "臺南",
    "臺北大巨蛋":         "大巨蛋",
    "嘉義市立棒球場":     "其他",
    "花蓮縣立德興棒球場": "其他",
    "臺東棒球村第一棒球場": "其他",
    "斗六棒球場":         "其他",
}
INDOOR_STADIUMS = {"大巨蛋"}

# batter-box stat columns we will re-aggregate per side
BATTER_STAT_KEYS = ["PA", "AB", "R", "H", "RBI", "2B", "3B", "HR",
                    "BB", "IBB", "HBP", "SO", "SH", "SF", "GIDP", "SB", "CS", "E"]


def sum_inning_scores(arr):
    """Robust sum that skips non-numeric inning entries (e.g. 'X')."""
    s = 0
    for v in arr:
        try:
            s += int(v)
        except (ValueError, TypeError):
            continue
    return s


def aggregate_box(box, prefix):
    out = {f"{prefix}_{k}": 0 for k in BATTER_STAT_KEYS}
    for batter in box:
        for k in BATTER_STAT_KEYS:
            v = batter.get(k, 0) or 0
            try:
                out[f"{prefix}_{k}"] += int(v)
            except (ValueError, TypeError):
                pass
    return out


def make_game_id(game, game_type, seq_in_source):
    """Build a stable game_id: {date}-{type}-{seq}."""
    date = (game.get("date") or "")[:10].replace("-", "")
    return f"{date}-{game_type[:3].upper()}-{seq_in_source:03d}"


def parse_date(s):
    if not s:
        return pd.NaT
    s = s.replace("/", "-")
    # rebas pattern: "2024-04-04 17:05:00"
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::\d{2})?)?", s)
    if not m:
        return pd.NaT
    y, mo, d, hh, mm = m.groups()
    hh = hh or "00"; mm = mm or "00"
    return datetime(int(y), int(mo), int(d), int(hh), int(mm))


# ---------------------------------------------------------------------------
rows = []
provenance = {
    "run_id": datetime.utcnow().isoformat() + "Z",
    "rebas_release_tag": "v0.1.0-2024",
    "sources": {},
}

for game_type, path in SOURCES:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    provenance["sources"][game_type] = {
        "path": str(path.relative_to(ROOT)),
        "n_games": len(data),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }

    for seq, g in enumerate(data, start=1):
        home_scores = g.get("homeScores", [])
        away_scores = g.get("awayScores", [])
        h_total = sum_inning_scores(home_scores)
        a_total = sum_inning_scores(away_scores)

        home_box = g.get("homeBatterBox", []) or []
        away_box = g.get("awayBatterBox", []) or []

        row = {
            "game_id":    make_game_id(g, game_type, seq),
            "game_type":  game_type,
            "season":     g.get("season"),
            "seasonId":   g.get("seasonId"),
            "seq":        g.get("seq"),
            "datetime":   g.get("date"),
            "stadium_raw": g.get("stadium"),
            "stadium":    STADIUM_MAP.get(g.get("stadium"), "其他"),
            "is_indoor":  int(STADIUM_MAP.get(g.get("stadium"), "其他") in INDOOR_STADIUMS),
            "home_team":  g.get("homeTeam"),
            "away_team":  g.get("awayTeam"),
            "home_team_id": g.get("homeTeamId"),
            "away_team_id": g.get("awayTeamId"),
            "home_innings_played": len(home_scores),
            "away_innings_played": len(away_scores),
            "home_score": h_total,
            "away_score": a_total,
            "total_score": h_total + a_total,
            "is_home_win": int(h_total > a_total),
            "is_tie":      int(h_total == a_total),
            "n_home_batters": len(home_box),
            "n_away_batters": len(away_box),
        }
        row.update(aggregate_box(home_box, "home"))
        row.update(aggregate_box(away_box, "away"))
        rows.append(row)

df = pd.DataFrame(rows)
df["date"] = df["datetime"].apply(parse_date)
df = df.sort_values(["date", "game_id"]).reset_index(drop=True)

# ---- sanity ----------------------------------------------------------------
print(f"total rows: {len(df)}")
print(f"by game_type: {df['game_type'].value_counts().to_dict()}")
print(f"ties dropped: {df['is_tie'].sum()}")

# 平手場直接丟掉, 我們是 binary classification
df = df.loc[df["is_tie"] == 0].drop(columns=["is_tie"]).reset_index(drop=True)
print(f"after dropping ties: {len(df)}")
print(f"home_win rate: {df['is_home_win'].mean():.3f}")
print(f"stadium normalize roster:")
print(df["stadium"].value_counts().to_string())

# ---- output ----------------------------------------------------------------
out_path = OUT / "raw_games.csv"
df.to_csv(out_path, index=False, encoding="utf-8")
print(f"\nwritten: {out_path}  shape={df.shape}")

provenance["output"] = {
    "path": str(out_path.relative_to(ROOT)),
    "rows": len(df),
    "cols": list(df.columns),
    "sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
}
(PROV / "manifest_step1.json").write_text(
    json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(f"manifest: {PROV / 'manifest_step1.json'}")
