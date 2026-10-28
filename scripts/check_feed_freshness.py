"""Independent freshness watchdog. Uses existing gh authentication; stores no credentials."""
import argparse
from datetime import datetime, timezone
import json
import subprocess
import urllib.request

SITE_URL = "https://ce-williams.github.io/powderline/"
REPOSITORY = "ce-williams/powderline"
ACTIVE = {"queued", "pending", "in_progress", "waiting", "requested"}


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def decide(manifest, runs, current_time, max_age_minutes=40):
    age = (current_time - timestamp(manifest["generatedAt"])).total_seconds() / 60
    if age < -5:
        raise ValueError("Published batch is dated in the future")
    if age <= max_age_minutes:
        return {"action": "fresh", "ageMinutes": round(max(0, age), 1)}
    for run in runs:
        if run["status"] in ACTIVE:
            run_age = (current_time - timestamp(run["createdAt"])).total_seconds() / 60
            return {"action": "build_running" if run_age <= 20 else "build_stalled", "runId": run["databaseId"], "ageMinutes": round(age, 1)}
    return {"action": "refresh_needed", "ageMinutes": round(age, 1)}


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, timeout=30).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Dispatch the existing Pages workflow only when overdue and no build is active")
    args = parser.parse_args()
    request = urllib.request.Request(SITE_URL + "snapshots/manifest.json?watchdog=" + datetime.now(timezone.utc).isoformat(), headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=20) as response:
        manifest = json.load(response)
    runs = json.loads(gh("run", "list", "--repo", REPOSITORY, "--workflow", "pages.yml", "--limit", "10", "--json", "databaseId,status,createdAt"))
    result = decide(manifest, runs, datetime.now(timezone.utc))
    if args.refresh and result["action"] == "refresh_needed":
        result["dispatch"] = gh("workflow", "run", "pages.yml", "--repo", REPOSITORY, "--ref", "main").strip()
        result["action"] = "refresh_requested"
    print(json.dumps(result))
    if result["action"] == "build_stalled":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
