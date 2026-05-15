"""
scripts/run_all.py — one-shot end-to-end pipeline (Python only).

Order:  step1  build raw_games from rebas JSON (any season auto-discovered)
        step1b fetch Open-Meteo weather  -> games_with_weather.csv
        step2  feature engineering       -> model_ready_data.csv
        step3  ablation + tuning + Shiny artifacts

Prints `git log -1` FIRST so a stale `git pull` can never silently run old
code again (that exact bug burned a whole Colab session before).

Usage (local or Colab):  python3 scripts/run_all.py
Fail-fast: any step's non-zero exit aborts the run.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = [
    ("step1  raw_games", "scripts/step1_build_raw_games.py"),
    ("step1b weather", "scripts/step1b_fetch_weather.py"),
    ("step2  features", "scripts/step2_features.py"),
    ("step3  models", "scripts/step3_models.py"),
]


def banner(msg):
    print("\n" + "#" * 72 + f"\n#  {msg}\n" + "#" * 72, flush=True)


def main():
    banner("CODE VERSION (verify this matches origin before trusting output)")
    subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--oneline"],
                   check=False)
    subprocess.run(["git", "-C", str(ROOT), "status", "--short"], check=False)

    for label, script in STEPS:
        banner(f"RUN  {label}   ({script})")
        r = subprocess.run([sys.executable, str(ROOT / script)], cwd=str(ROOT))
        if r.returncode != 0:
            print(f"\n!! {label} FAILED (exit {r.returncode}) — aborting.")
            sys.exit(r.returncode)

    banner("PIPELINE COMPLETE")
    for f in ["data/processed/raw_games.csv",
              "data/processed/games_with_weather.csv",
              "data/processed/model_ready_data.csv",
              "models/best_model.joblib",
              "Results/eval/predictions.csv",
              "Results/eval/feature_schema.json",
              "Results/eval/_final_metrics.json"]:
        p = ROOT / f
        flag = "OK " if p.exists() else "MISSING"
        print(f"  [{flag}] {f}")


if __name__ == "__main__":
    main()
