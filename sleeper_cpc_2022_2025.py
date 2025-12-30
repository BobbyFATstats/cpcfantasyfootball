import csv
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "https://api.sleeper.app/v1"
START_LEAGUE_ID = "1257104872696713216"
TARGET_SEASONS = {"2025", "2024", "2023", "2022"}
OUT_CSV = "standings_2022_2025.csv"

REQUEST_SLEEP_SECONDS = 0.2


def sleeper_get(path: str) -> Any:
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def to_points(settings: Dict[str, Any], whole_key: str, dec_key: str) -> Optional[float]:
    """
    Sleeper stores points split into integer + decimal portion:
      fpts + fpts_decimal/100
      fpts_against + fpts_against_decimal/100
    """
    whole = settings.get(whole_key)
    dec = settings.get(dec_key)
    if whole is None and dec is None:
        return None
    try:
        whole_val = int(whole or 0)
        dec_val = int(dec or 0)
        return whole_val + (dec_val / 100.0)
    except (ValueError, TypeError):
        return None


def get_league_chain(start_league_id: str, target_seasons: set[str]) -> Dict[str, str]:
    """
    Walks backward using previous_league_id until we collect league_ids for target seasons.
    Returns: {season_str: league_id}
    """
    season_to_league: Dict[str, str] = {}
    league_id = start_league_id

    while league_id:
        league = sleeper_get(f"/league/{league_id}")
        season = str(league.get("season", ""))
        if season in target_seasons and season not in season_to_league:
            season_to_league[season] = str(league.get("league_id"))

        if target_seasons.issubset(set(season_to_league.keys())):
            break

        league_id = league.get("previous_league_id")
        time.sleep(REQUEST_SLEEP_SECONDS)

    return season_to_league


def build_user_map(league_id: str) -> Dict[str, Dict[str, str]]:
    """GET /league/<league_id>/users"""
    users = sleeper_get(f"/league/{league_id}/users")
    user_map: Dict[str, Dict[str, str]] = {}
    for u in users:
        uid = u.get("user_id")
        if uid:
            user_map[str(uid)] = {
                "username": u.get("username", "") or "",
                "display_name": u.get("display_name", "") or "",
            }
    return user_map


def pick_season_draft_id(league_id: str) -> Optional[str]:
    """
    For redraft leagues, this should return the main draft_id.
    GET /league/<league_id>/drafts
    Prefer status == "complete", else fall back to the first one.
    """
    drafts = sleeper_get(f"/league/{league_id}/drafts")
    if not drafts:
        return None

    complete = [d for d in drafts if d.get("status") == "complete" and d.get("draft_id")]
    if complete:
        return str(complete[0]["draft_id"])

    if drafts[0].get("draft_id"):
        return str(drafts[0]["draft_id"])

    return None


def build_roster_draft_slot_map(league_id: str) -> Dict[int, int]:
    """
    Returns {roster_id: draft_slot} using:
      GET /league/<league_id>/drafts
      GET /draft/<draft_id> (slot_to_roster_id)
    """
    draft_id = pick_season_draft_id(league_id)
    if not draft_id:
        return {}

    draft = sleeper_get(f"/draft/{draft_id}")
    slot_to_roster = draft.get("slot_to_roster_id") or {}

    roster_to_slot: Dict[int, int] = {}
    for slot_str, roster_id in slot_to_roster.items():
        try:
            slot = int(slot_str)
            rid = int(roster_id)
            roster_to_slot[rid] = slot
        except (TypeError, ValueError):
            continue

    return roster_to_slot


def safe_get_losers_bracket(league_id: str) -> List[Dict[str, Any]]:
    """
    Docs show both 'losers_bracket' and a 'loses_bracket' typo in one spot.
    We'll try the correct one first, then fallback. :contentReference[oaicite:4]{index=4}
    """
    try:
        return sleeper_get(f"/league/{league_id}/losers_bracket")
    except requests.HTTPError:
        return sleeper_get(f"/league/{league_id}/loses_bracket")


def build_playoff_win_loss_maps(league_id: str) -> Tuple[Dict[int, int], Dict[int, int], Dict[int, int]]:
    """
    Returns:
      - playoff_wins_by_roster (wins across winners+losers brackets)
      - playoff_losses_by_roster (losses across winners+losers brackets)
      - winners_bracket_wins_by_roster (wins in winners bracket only; for Champion calc)
    Bracket row fields include w (winner roster_id) and l (loser roster_id). :contentReference[oaicite:5]{index=5}
    """
    wins: Dict[int, int] = {}
    losses: Dict[int, int] = {}
    wb_wins: Dict[int, int] = {}

    winners_bracket = sleeper_get(f"/league/{league_id}/winners_bracket")
    time.sleep(REQUEST_SLEEP_SECONDS)
    losers_bracket = safe_get_losers_bracket(league_id)

    def bump(d: Dict[int, int], rid: Any) -> None:
        try:
            r = int(rid)
        except (TypeError, ValueError):
            return
        d[r] = d.get(r, 0) + 1

    # Winners bracket
    for match in winners_bracket or []:
        if match.get("w") is not None:
            bump(wins, match.get("w"))
            bump(wb_wins, match.get("w"))
        if match.get("l") is not None:
            bump(losses, match.get("l"))

    # Losers bracket
    for match in losers_bracket or []:
        if match.get("w") is not None:
            bump(wins, match.get("w"))
        if match.get("l") is not None:
            bump(losses, match.get("l"))

    return wins, losses, wb_wins


def build_transactions_count_by_roster(league_id: str, max_weeks: int = 18) -> Dict[int, int]:
    """
    Counts number of transactions per roster across the season.

    Uses:
      GET /league/<league_id>/transactions/<round> (round == week in football) :contentReference[oaicite:6]{index=6}

    Each transaction has 'roster_ids' involved. We count each transaction once per roster_id in that list. :contentReference[oaicite:7]{index=7}

    Implementation detail: we iterate weeks 1..max_weeks and stop early after a few empty weeks.
    """
    counts: Dict[int, int] = {}
    empty_streak = 0

    for week in range(1, max_weeks + 1):
        txs = sleeper_get(f"/league/{league_id}/transactions/{week}")
        time.sleep(REQUEST_SLEEP_SECONDS)

        if not txs:
            empty_streak += 1
            if empty_streak >= 3:
                break
            continue

        empty_streak = 0
        for tx in txs:
            roster_ids = tx.get("roster_ids") or []
            for rid in roster_ids:
                try:
                    r = int(rid)
                except (TypeError, ValueError):
                    continue
                counts[r] = counts.get(r, 0) + 1

    return counts


def pull_season_rows(season: str, league_id: str) -> List[Dict[str, Any]]:
    """
    Pulls standings-like season totals per roster plus:
      - draft_slot
      - playoff wins/losses
      - champion (Y/N)
      - total transactions
    """
    user_map = build_user_map(league_id)
    time.sleep(REQUEST_SLEEP_SECONDS)

    draft_slot_by_roster = build_roster_draft_slot_map(league_id)
    time.sleep(REQUEST_SLEEP_SECONDS)

    playoff_wins_by_roster, playoff_losses_by_roster, wb_wins_by_roster = build_playoff_win_loss_maps(league_id)
    time.sleep(REQUEST_SLEEP_SECONDS)

    tx_count_by_roster = build_transactions_count_by_roster(league_id, max_weeks=18)
    time.sleep(REQUEST_SLEEP_SECONDS)

    rosters = sleeper_get(f"/league/{league_id}/rosters")
    rows: List[Dict[str, Any]] = []

    for r in rosters:
        settings = r.get("settings", {}) or {}
        owner_id = str(r.get("owner_id", "") or "")
        roster_id = r.get("roster_id", "")

        # draft_slot_by_roster is keyed by int roster_id
        draft_slot = ""
        rid_int: Optional[int] = None
        if roster_id != "":
            try:
                rid_int = int(roster_id)
                draft_slot = draft_slot_by_roster.get(rid_int, "")
            except (TypeError, ValueError):
                rid_int = None
                draft_slot = ""

        user = user_map.get(owner_id, {"username": "", "display_name": ""})

        wins = settings.get("wins", "")
        losses = settings.get("losses", "")

        pf = to_points(settings, "fpts", "fpts_decimal")
        pa = to_points(settings, "fpts_against", "fpts_against_decimal")
        max_pf = to_points(settings, "ppts", "ppts_decimal")  # optional in many leagues

        # Playoffs + Champion
        playoff_wins = playoff_wins_by_roster.get(rid_int or -1, 0) if rid_int is not None else 0
        playoff_losses = playoff_losses_by_roster.get(rid_int or -1, 0) if rid_int is not None else 0
        champion = "Y" if (rid_int is not None and wb_wins_by_roster.get(rid_int, 0) == 2) else "N"

        # Transactions
        total_transactions = tx_count_by_roster.get(rid_int or -1, 0) if rid_int is not None else 0

        rows.append(
            {
                "season": season,
                "draft_slot": draft_slot,
                "roster_id": roster_id,
                "username": user.get("username", ""),
                "display_name": user.get("display_name", ""),
                "wins": wins,
                "losses": losses,
                "pf": pf if pf is not None else "",
                "max_pf": max_pf if max_pf is not None else "",
                "pa": pa if pa is not None else "",
                "playoff_wins": playoff_wins,
                "playoff_losses": playoff_losses,
                "champion": champion,
                "total_transactions": total_transactions,
            }
        )

    # Sort like standings by wins desc, then PF desc
    def sort_key(x: Dict[str, Any]) -> Tuple[int, float]:
        w = int(x["wins"] or 0)
        pfv = float(x["pf"] or 0.0)
        return (w, pfv)

    rows.sort(key=sort_key, reverse=True)
    return rows


def main() -> None:
    season_to_league = get_league_chain(START_LEAGUE_ID, TARGET_SEASONS)

    missing = TARGET_SEASONS - set(season_to_league.keys())
    if missing:
        print(f"Warning: could not find league_id(s) for season(s): {sorted(missing)}")
        print("This usually means the starting league_id isn't linked to those seasons via previous_league_id.")

    all_rows: List[Dict[str, Any]] = []
    for season in sorted(season_to_league.keys(), reverse=True):
        league_id = season_to_league[season]
        print(f"Fetching season {season} (league_id={league_id})...")
        all_rows.extend(pull_season_rows(season, league_id))
        time.sleep(REQUEST_SLEEP_SECONDS)

    fieldnames = [
        "season",
        "draft_slot",
        "roster_id",
        "username",
        "display_name",
        "wins",
        "losses",
        "pf",
        "max_pf",
        "pa",
        "playoff_wins",
        "playoff_losses",
        "champion",
        "total_transactions",
    ]

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
