"""Coleta rosters, status de lesão, draft, conferências e agenda da liga ESPN Fantasy Basketball.

Uso:
    python espn_collector.py
Gera CSVs em data/: rosters.csv, draft.csv, teams.csv e schedule.csv.
Requer ESPN_S2 e SWID no .env (cookies da sua conta, liga privada).
"""
import os
import csv
import requests
from dotenv import load_dotenv

from config import LEAGUE_ID, SEASON, DATA_DIR, POSITION

load_dotenv()

BASE = (
    f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{SEASON}"
    f"/segments/0/leagues/{LEAGUE_ID}"
)


def get_session() -> requests.Session:
    espn_s2 = os.getenv("ESPN_S2")
    swid = os.getenv("SWID")
    if not espn_s2 or not swid:
        raise SystemExit("Defina ESPN_S2 e SWID no arquivo .env")
    s = requests.Session()
    s.cookies.set("espn_s2", espn_s2, domain=".espn.com")
    s.cookies.set("SWID", swid, domain=".espn.com")
    return s


def fetch_league(s: requests.Session) -> dict:
    params = [("view", "mTeam"), ("view", "mRoster"), ("view", "mSettings"), ("view", "mDraftDetail")]
    r = s.get(BASE, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_schedule(s: requests.Session) -> list:
    r = s.get(BASE, params=[("view", "mMatchupScore")], timeout=30)
    r.raise_for_status()
    return r.json().get("schedule", [])


def team_names(data: dict) -> dict:
    return {t["id"]: t.get("name") or t.get("location", "?") for t in data.get("teams", [])}


def write_rosters(data: dict, path) -> int:
    members = {m["id"]: f'{m.get("firstName", "")} {m.get("lastName", "")}'.strip()
               for m in data.get("members", [])}
    rows = []
    for team in data.get("teams", []):
        owner_ids = team.get("owners", [])
        owner = members.get(owner_ids[0], "?") if owner_ids else "?"
        team_name = team.get("name") or team.get("location", "?")
        for entry in team.get("roster", {}).get("entries", []):
            player = entry.get("playerPoolEntry", {}).get("player", {})
            rows.append({
                "team_id": team["id"],
                "team_name": team_name,
                "owner": owner,
                "lineup_slot": entry.get("lineupSlotId"),
                "espn_player_id": player.get("id"),
                "player_name": player.get("fullName"),
                "position": POSITION.get(player.get("defaultPositionId"), player.get("defaultPositionId")),
                "position_id": player.get("defaultPositionId"),
                "eligible_slots": "|".join(str(x) for x in player.get("eligibleSlots", [])),
                "pro_team_id": player.get("proTeamId"),
                "injury_status": player.get("injuryStatus", "ACTIVE"),
                "acquisition_type": entry.get("acquisitionType"),
            })
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["team_id"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def write_draft(data: dict, path) -> int:
    picks = data.get("draftDetail", {}).get("picks", [])
    names = team_names(data)
    rows = [{
        "overall_pick": p.get("overallPickNumber"),
        "round": p.get("roundId"),
        "round_pick": p.get("roundPickNumber"),
        "team_id": p.get("teamId"),
        "team_name": names.get(p.get("teamId"), "?"),
        "espn_player_id": p.get("playerId"),
        "auto_draft": p.get("autoDraftTypeId"),
    } for p in picks]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["overall_pick"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def write_teams(data: dict, path) -> int:
    """Uma linha por time, com a conferência (divisão do ESPN: East / West)."""
    divisions = {d["id"]: d["name"] for d in data.get("settings", {}).get("scheduleSettings", {}).get("divisions", [])}
    members = {m["id"]: f'{m.get("firstName", "")} {m.get("lastName", "")}'.strip()
               for m in data.get("members", [])}
    rows = []
    for t in data.get("teams", []):
        owners = t.get("owners", [])
        rows.append({
            "team_id": t["id"],
            "team_name": t.get("name") or t.get("location", "?"),
            "owner": members.get(owners[0], "?") if owners else "?",
            "conferencia": divisions.get(t.get("divisionId"), ""),
            "playoff_seed": t.get("playoffSeed"),
        })
    rows.sort(key=lambda r: (r["conferencia"], r["team_name"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def write_schedule(schedule: list, data: dict, path) -> int:
    names = team_names(data)
    rows = [{
        "semana": m.get("matchupPeriodId"),
        "mandante": names.get(m.get("home", {}).get("teamId"), "?"),
        "visitante": names.get(m.get("away", {}).get("teamId"), "?"),
    } for m in schedule]
    rows.sort(key=lambda r: (r["semana"] or 0, r["mandante"]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["semana", "mandante", "visitante"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    s = get_session()
    data = fetch_league(s)
    schedule = fetch_schedule(s)
    n_roster = write_rosters(data, DATA_DIR / "rosters.csv")
    n_draft = write_draft(data, DATA_DIR / "draft.csv")
    n_teams = write_teams(data, DATA_DIR / "teams.csv")
    n_sched = write_schedule(schedule, data, DATA_DIR / "schedule.csv")
    print(f"rosters.csv: {n_roster} jogadores | draft.csv: {n_draft} picks | "
          f"teams.csv: {n_teams} times | schedule.csv: {n_sched} confrontos")


if __name__ == "__main__":
    main()
