"""
scripts/run_all.py — one-shot end-to-end pipeline (Python only).

Order:  step1  build raw_games from rebas JSON (any season auto-discovered)
        step1b fetch Open-Meteo weather  -> games_with_weather.csv
        step2  feature engineering       -> model_ready_data.csv
        step3  ablation + tuning + Shiny artifacts

Prints `git log -1` + a CODE FINGERPRINT FIRST, and hard-asserts the
pitcher features actually reached the outputs, so a stale Colab clone can
never again silently emit byte-identical OLD metrics (that exact failure
recurred twice: a stale `git pull`, and re-running Cell 5/6 on a stale
runtime without Cell 2's `reset --hard`).

Usage (local or Colab):  python3 scripts/run_all.py
Fail-fast: any step's non-zero exit aborts the run.
"""
import json
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


def die_stale(why):
    banner("STALE CODE / STALE CACHE — OUTPUT IS NOT TRUSTWORTHY")
    print(f"!! {why}\n"
          "!! Colab is running OLD code or reused an OLD model_ready CSV.\n"
          "!! FIX: Runtime -> Disconnect and delete runtime, reopen the\n"
          "!! notebook, then Run all FROM THE TOP (Cell 2's reset --hard +\n"
          "!! fresh data + fresh pipeline). Re-running only Cell 5/6 on a\n"
          "!! stale runtime reproduces the previous run's numbers verbatim.",
          flush=True)
    sys.exit(3)


def fingerprint():
    """Prove the pitcher code is physically present BEFORE the 10-min run,
    so a stale clone is obvious at the top of Cell 5, not after."""
    s2 = (ROOT / "scripts/step2_features.py").read_text(encoding="utf-8")
    s3 = (ROOT / "scripts/step3_models.py").read_text(encoding="utf-8")
    has_roll = "def rolling_pitching(" in s2
    has_grp = '"m6": PITCHING,' in s3
    print(f"  code fingerprint: step2.rolling_pitching={has_roll}  "
          f"step3.m6==PITCHING={has_grp}", flush=True)
    if not (has_roll and has_grp):
        die_stale("pitcher code ABSENT from working tree "
                  "(Cell 2 did not pull the latest commit)")


def assert_pitching_in_outputs():
    """The deliverable must actually be in the artifacts — version-agnostic
    (catches an old model_ready CSV cached from a prior run too)."""
    mr = ROOT / "data/processed/model_ready_data.csv"
    with open(mr, encoding="utf-8") as f:
        header = f.readline().strip().split(",")
    if "diff_spERA_l5" not in header:
        die_stale("model_ready_data.csv has NO pitcher columns "
                  "(step2 that ran was old, or the CSV is a stale cache)")
    sch = json.loads((ROOT / "Results/eval/feature_schema.json")
                      .read_text(encoding="utf-8"))
    if not sch.get("feature_groups", {}).get("pitching"):
        die_stale("feature_schema.json pitching group is EMPTY "
                  "(step3 that ran was the old m1-m7 scheme)")
    print("  pitcher features confirmed in model_ready_data.csv "
          "+ feature_schema.json", flush=True)


def main():
    banner("CODE VERSION (must be >= 4e3388e for pitcher features)")
    subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--oneline"],
                   check=False)
    subprocess.run(["git", "-C", str(ROOT), "status", "--short"], check=False)
    fingerprint()

    for label, script in STEPS:
        banner(f"RUN  {label}   ({script})")
        r = subprocess.run([sys.executable, str(ROOT / script)], cwd=str(ROOT))
        if r.returncode != 0:
            print(f"\n!! {label} FAILED (exit {r.returncode}) — aborting.")
            sys.exit(r.returncode)

    banner("VERIFY DELIVERABLE — pitcher features in outputs")
    assert_pitching_in_outputs()

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
