"""
scripts/step1b_fetch_weather.py

Step 1.4 — Fetch game-time weather and join to raw_games.csv.

Python port of the old R/fetch_cwa.R (which kept failing in Colab on a stale
`station_id` join). Stdlib-only (urllib + json) so it runs anywhere with no
extra install and no API key.

Source = Open-Meteo Archive API (https://archive-api.open-meteo.com/v1/archive)
  - Free, NO API key, hourly ERA5 reanalysis back to 1940, ~10 km grid
  - ERA5 ingests CWA station data anyway; CWA CODiS needs a CAPTCHA session
  - Returns temperature_2m, relative_humidity_2m, wind_speed_10m,
    wind_direction_10m, precipitation

Inputs:
  data/processed/raw_games.csv               (from step1)
  data/raw/_lookup/stadium_to_station.csv    (stadium_raw -> lat/lon)
Output:
  data/processed/games_with_weather.csv      (raw_games + 6 weather cols)

Idempotent: every distinct (lat,lon,window) response is disk-cached under
data/raw/.cache_weather/, so reruns are instant and offline-safe.

Usage:  python3 scripts/step1b_fetch_weather.py
"""
import hashlib
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_GAMES = ROOT / "data/processed/raw_games.csv"
LOOKUP = ROOT / "data/raw/_lookup/stadium_to_station.csv"
OUT = ROOT / "data/processed/games_with_weather.csv"
CACHE = ROOT / "data/raw/.cache_weather"
CACHE.mkdir(parents=True, exist_ok=True)

API_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation"
RETRY_N = 3
DEFAULT_FIRST_PITCH_HOUR = 18   # used only when a game row has no clock time

WIND_BINS = [-1, 22.5, 67.5, 112.5, 157.5, 202.5, 247.5, 292.5, 337.5, 361]
WIND_LABELS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW", "N"]


# ---------------------------------------------------------------------------
# Load games + stadium geo lookup
# ---------------------------------------------------------------------------
games = pd.read_csv(RAW_GAMES)
lookup = pd.read_csv(LOOKUP)

geo = lookup[["stadium_raw", "latitude", "longitude"]].drop_duplicates("stadium_raw")
games = games.merge(geo, on="stadium_raw", how="left")

n_missing_geo = int(games["latitude"].isna().sum())
if n_missing_geo:
    miss = sorted(games.loc[games["latitude"].isna(),
                            "stadium_raw"].dropna().unique())
    # HARD FAIL — never silently write NA weather (that exact "warn then
    # exit 0" pattern is what made the old R fetch_cwa.R waste a whole
    # Colab session). New seasons can introduce venues absent from the
    # lookup; force the user to fix the lookup before any downstream run.
    raise SystemExit(
        f"STOP: {n_missing_geo} games have no lat/lon. Unmapped "
        f"stadium_raw: {miss}. Add these rows (with latitude/longitude) "
        f"to data/raw/_lookup/stadium_to_station.csv and rerun step1b."
    )

# Game datetime: raw rebas string lives in `datetime`; floor to the hour.
# Some rows may carry only a date -> assume the default first-pitch hour.
dt = pd.to_datetime(games["datetime"], errors="coerce")
no_time = dt.dt.hour.eq(0) & dt.dt.minute.eq(0)
dt = dt.mask(no_time, dt.dt.normalize() + pd.Timedelta(hours=DEFAULT_FIRST_PITCH_HOUR))
games["game_dt"] = dt
games["join_hour"] = games["game_dt"].dt.floor("h").dt.strftime("%Y-%m-%dT%H:00")
games["game_date"] = games["game_dt"].dt.date

valid_dates = games["game_dt"].dropna()
date_lo = valid_dates.min().strftime("%Y-%m-%d")
date_hi = valid_dates.max().strftime("%Y-%m-%d")
print(f"games={len(games)}  missing geo={n_missing_geo}  "
      f"date range {date_lo} .. {date_hi}")


# ---------------------------------------------------------------------------
# Open-Meteo fetch with disk cache + retry
# ---------------------------------------------------------------------------
def fetch_openmeteo(lat, lon, start_date, end_date):
    key = hashlib.sha256(
        f"{lat:.4f}_{lon:.4f}_{start_date}_{end_date}".encode()
    ).hexdigest()[:16]
    cache_f = CACHE / f"{key}.json"
    if cache_f.exists():
        body = json.loads(cache_f.read_text())
    else:
        qs = urllib.parse.urlencode({
            "latitude": lat, "longitude": lon,
            "start_date": start_date, "end_date": end_date,
            "hourly": HOURLY, "timezone": "Asia/Taipei",
            "wind_speed_unit": "ms",
        })
        url = f"{API_URL}?{qs}"
        last_err = None
        body = None
        for attempt in range(RETRY_N):
            try:
                with urllib.request.urlopen(url, timeout=60) as resp:
                    if resp.status != 200:
                        raise RuntimeError(f"HTTP {resp.status}")
                    body = json.loads(resp.read().decode())
                cache_f.write_text(json.dumps(body))
                break
            except Exception as e:                       # noqa: BLE001
                last_err = e
                time.sleep(2 ** attempt)
        if body is None:
            raise RuntimeError(f"Open-Meteo failed after {RETRY_N} tries: {last_err}")

    h = body.get("hourly")
    if not h:
        return pd.DataFrame()
    return pd.DataFrame({
        "obs_dt": h["time"],
        "temperature": h["temperature_2m"],
        "humidity": h["relative_humidity_2m"],
        "wind_speed": h["wind_speed_10m"],
        "wind_dir": h["wind_direction_10m"],
        "precip": h["precipitation"],
    })


sites = games.dropna(subset=["latitude"]).drop_duplicates("stadium_raw")[
    ["stadium_raw", "latitude", "longitude"]
]
print(f"distinct sites to query: {len(sites)}")

weather_parts = []
for _, s in sites.iterrows():
    try:
        w = fetch_openmeteo(s["latitude"], s["longitude"], date_lo, date_hi)
    except Exception as e:                                # noqa: BLE001
        print(f"  fetch FAILED {s['stadium_raw']}: {e}")
        continue
    if len(w):
        w["stadium_raw"] = s["stadium_raw"]
        weather_parts.append(w)
        print(f"  {s['stadium_raw']:18s} rows={len(w)}")

# ---------------------------------------------------------------------------
# Join hourly obs to each game
# ---------------------------------------------------------------------------
WCOLS = ["temperature", "humidity", "wind_speed", "wind_dir", "precip"]
if weather_parts:
    weather = pd.concat(weather_parts, ignore_index=True)
    games_w = games.merge(
        weather.rename(columns={"obs_dt": "join_hour"}),
        on=["stadium_raw", "join_hour"], how="left",
    )
else:
    print("WARNING: Open-Meteo returned nothing. Writing NA weather columns.")
    games_w = games.copy()
    for c in WCOLS:
        games_w[c] = np.nan

games_w["wind_dir_cat"] = pd.cut(
    games_w["wind_dir"], bins=WIND_BINS, labels=WIND_LABELS, ordered=False
).astype("object")

miss_rate = float(games_w["temperature"].isna().mean())
print(f"\nweather join missing rate = {miss_rate:.4f}")
if miss_rate > 0.50:
    # geo matched but the hour-key join collapsed -> timezone / time-format
    # bug. Refuse to poison step2/step3 with all-NA weather.
    raise SystemExit(
        f"STOP: weather missing rate {miss_rate:.2%} > 50% — the "
        f"(stadium_raw, join_hour) join is broken (timezone or Open-Meteo "
        f"time-format mismatch), not just a few gaps. Not writing output."
    )
if miss_rate > 0.10:
    print("WARNING: >10% games lack weather — check timezone / coord lookup.")

drop_helpers = ["game_dt", "game_date"]
games_w = games_w.drop(columns=[c for c in drop_helpers if c in games_w.columns])
games_w.to_csv(OUT, index=False, encoding="utf-8")
print(f"written: {OUT}  shape={games_w.shape}")
print(games_w[["game_id", "stadium_raw", "join_hour"] + WCOLS].head(3).to_string(index=False))
