import requests
import pandas as pd
import time

BASE_URL = "https://site.web.api.espn.com/apis/v2/sports/basketball/nba/standings"

def season_label(season_end_year: int) -> str:
    """
    Turn ESPN's season end year into label like '2002-2003'.
    Example: 2003 -> '2002-2003'
    """
    start = season_end_year - 1
    end = season_end_year
    return f"{start}-{end}"

def get_season_standings(season_year: int) -> pd.DataFrame:
    """
    Pull ESPN NBA league standings for a given season (ending year)
    and return only the fields we care about.
    """
    params = {
        "region": "us",
        "lang": "en",
        "contentorigin": "espn",
        "type": 0,   # regular season
        "level": 1,  # league-wide standings (not conference)
        "sort": "winpercent:desc,wins:desc,gamesbehind:asc",
        "season": season_year,
    }

    resp = requests.get(BASE_URL, params=params)
    resp.raise_for_status()
    data = resp.json()

    entries = data["standings"]["entries"]

    rows = []
    for rank, e in enumerate(entries, start=1):  # rank within whole league
        team = e["team"]

        # basic fields
        row = {
            "season": season_label(season_year),
            "league_rank": rank,
            "team_name": team["displayName"],
        }

        # pull wins, losses, home, road from stats
        stats_map = {}
        for s in e.get("stats", []):
            stat_type = s.get("type")
            if not stat_type:
                continue
            value = s.get("value")
            if (value is None or value == "") and s.get("summary"):
                value = s["summary"]
            stats_map[stat_type] = value

        row["wins"] = int(stats_map.get("wins", 0))
        row["losses"] = int(stats_map.get("losses", 0))
        row["home"] = stats_map.get("home")      # string like '31-10'
        row["road"] = stats_map.get("road")      # string like '20-21'

        rows.append(row)

    df = pd.DataFrame(rows)
    return df


def main():
    # ESPN uses the end year: 2003 = 2002-2003 season, 2025 = 2024-2025
    season_years = range(2003, 2026)  # 2003..2025 inclusive

    all_seasons = []
    for season in season_years:
        print(f"Fetching season ending {season} ({season_label(season)})...")
        try:
            df_season = get_season_standings(season)
            all_seasons.append(df_season)
        except Exception as e:
            print(f"  !! Failed for {season}: {e}")
        time.sleep(0.5)  # small pause to be polite

    if not all_seasons:
        print("No data downloaded.")
        return

    df_all = pd.concat(all_seasons, ignore_index=True)

    # Reorder columns just to be clean
    df_all = df_all[["season", "league_rank", "team_name",
                     "wins", "losses", "home", "road"]]

    out_file = "nba_standings_2002_2003_to_2024_2025_espn.csv"
    df_all.to_csv(out_file, index=False)
    print(f"Saved {len(df_all)} rows to {out_file}")


if __name__ == "__main__":
    main()
