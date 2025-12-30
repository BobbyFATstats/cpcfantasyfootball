import csv
import time
from typing import Dict, Any, List, Optional, Tuple

import requests

BASE_URL = "https://api.sleeper.app/v1"
LEAGUE_ID = "1257104872696713216"
WEEKS = range(1, 16)  # weeks 1-15
OUT_CSV = "weekly_highest_scorer_weeks_1_15.csv"

# Be polite with the API
REQUEST_SLEEP_SECONDS = 0.2


def sleeper_get(path: str) -> Any:
    """GET a Sleeper API endpoint and return parsed JSON."""
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def build_mappings(league_id: str) -> Tuple[Dict[int, str], Dict[str, Dict[str, str]]]:
    """
    Returns:
      - roster_owner: {roster_id(int): owner_id(str)}
      - user_map: {user_id(str): {"username": str, "display_name": str}}
    """
    users = sleeper_get(f"/league/{league_id}/users")
    user_map: Dict[str, Dict[str, str]] = {}
    for u in users:
        uid = u.get("user_id")
        if uid:
            user_map[uid] = {
                "username": u.get("username", "") or "",
                "display_name": u.get("display_name", "") or "",
            }

    time.sleep(REQUEST_SLEEP_SECONDS)

    rosters = sleeper_get(f"/league/{league_id}/rosters")
    roster_owner: Dict[int, str] = {}
    for r in rosters:
        rid = r.get("roster_id")
        oid = r.get("owner_id")
        if isinstance(rid, int) and oid:
            roster_owner[rid] = oid

    return roster_owner, user_map


def user_info_for_roster(
    roster_id: int,
    roster_owner: Dict[int, str],
    user_map: Dict[str, Dict[str, str]],
) -> Dict[str, str]:
    owner_id = roster_owner.get(roster_id, "")
    return user_map.get(owner_id, {"username": "", "display_name": ""})


def find_week_high_scorer(
    league_id: str,
    week: int,
    roster_owner: Dict[int, str],
    user_map: Dict[str, Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """
    For a given week, finds the roster with the max 'points' across all matchups.
    Returns a row dict with requested columns, or None if no data.
    """
    matchups: List[Dict[str, Any]] = sleeper_get(f"/league/{league_id}/matchups/{week}")
    if not matchups:
        return None

    # Each object is one team; max by points
    best = max(
        matchups,
        key=lambda m: (m.get("points") is not None, float(m.get("points") or 0.0)),
    )

    matchup_id = best.get("matchup_id")
    roster_id = best.get("roster_id")
    points = best.get("points")

    if matchup_id is None or roster_id is None:
        return None

    roster_id = int(roster_id)

    # Opponent = same matchup_id, different roster_id
    opponent = next(
        (
            m
            for m in matchups
            if m.get("matchup_id") == matchup_id and int(m.get("roster_id")) != roster_id
        ),
        None,
    )
    opponent_roster_id = int(opponent.get("roster_id")) if opponent and opponent.get("roster_id") is not None else None

    # Map roster -> user
    best_user = user_info_for_roster(roster_id, roster_owner, user_map)
    opp_user = user_info_for_roster(opponent_roster_id, roster_owner, user_map) if opponent_roster_id else {"username": "", "display_name": ""}

    return {
        "week": week,
        "matchup_id": matchup_id,
        "roster_id": roster_id,
        "username": best_user.get("username", ""),
        "display_name": best_user.get("display_name", ""),
        "points": points,
        "opponent_roster_id": opponent_roster_id if opponent_roster_id is not None else "",
        "opponent_username": opp_user.get("username", ""),
        # If you also want it, uncomment:
        # "opponent_display_name": opp_user.get("display_name", ""),
    }


def main() -> None:
    roster_owner, user_map = build_mappings(LEAGUE_ID)

    rows: List[Dict[str, Any]] = []
    for week in WEEKS:
        row = find_week_high_scorer(LEAGUE_ID, week, roster_owner, user_map)
        if row:
            rows.append(row)
        time.sleep(REQUEST_SLEEP_SECONDS)

    fieldnames = [
        "week",
        "matchup_id",
        "roster_id",
        "username",
        "display_name",
        "points",
        "opponent_roster_id",
        "opponent_username",
    ]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
