import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

BASE = "https://www.espn.com/nba/attendance/_/year/{end_year}"

def _to_int(x):
    """Strip commas/whitespace and return int (or None)."""
    s = re.sub(r"[^\d-]", "", x or "")
    return int(s) if s else None

def scrape_attendance_season(end_year, session=None, sleep_sec=0.25):
    """
    Scrape ESPN NBA attendance for a single season (ending year).
    Returns a DataFrame with:
      season, team, home_gms, home_avg, road_gms, road_avg, overall_avg
    """
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

    url = BASE.format(end_year=end_year)
    r = session.get(url, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    table = soup.select_one("#my-teams-table table.tablehead")
    if not table:
        # Fallback: try any ESPN-styled table on page
        table = soup.select_one("table.tablehead")
        if not table:
            return pd.DataFrame(columns=[
                "season","team","home_gms","home_avg","road_gms","road_avg","overall_avg"
            ])

    rows_out = []
    for tr in table.select("tr"):
        tds = tr.find_all("td")
        # Data rows have 12 tds: RK, TEAM, Home(GMS,TOTAL,AVG,PCT), Road(GMS,AVG,PCT), Overall(GMS,AVG,PCT)
        if len(tds) != 12:
            continue
        # Skip header rows that repeat
        if tds[0].get_text(strip=True).upper() in {"RK", ""} and "TEAM" in tds[1].get_text():
            continue

        team = tds[1].get_text(strip=True)
        # Skip conference summary rows like East/West
        if team.lower() in {"east", "west"}:
            continue

        # Parse columns by fixed positions (see structure above)
        home_gms   = _to_int(tds[2].get_text(strip=True))
        home_avg   = _to_int(tds[4].get_text(strip=True))
        road_gms   = _to_int(tds[6].get_text(strip=True))
        road_avg   = _to_int(tds[7].get_text(strip=True))
        overall_gms = _to_int(tds[9].get_text(strip=True))
        overall_avg = _to_int(tds[10].get_text(strip=True))

        # If no games parsed, likely a non-team row—skip
        if home_gms is None and road_gms is None and overall_avg is None:
            continue

        season = f"{end_year-1}-{end_year}"
        rows_out.append({
            "season": season,
            "team": team,
            "home_gms": home_gms,
            "home_avg": home_avg,
            "road_gms": road_gms,
            "road_avg": road_avg,
            "overall_gms": overall_gms,
            "overall_avg": overall_avg,
        })

    if sleep_sec:
        time.sleep(sleep_sec)

    return pd.DataFrame(rows_out)

def scrape_attendance_range(start_end_year=2001, end_end_year=2025, sleep_sec=0.25):
    """
    Scrape multiple seasons (inclusive) by ESPN end-year.
      2001 -> 2000-01  ...  2025 -> 2024-25
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    all_dfs = []

    for y in range(start_end_year, end_end_year + 1):
        try:
            df_season = scrape_attendance_season(y, session=session, sleep_sec=sleep_sec)
            if not df_season.empty:
                all_dfs.append(df_season)
                print(f"Scraped {y-1}-{y}: {len(df_season)} rows")
            else:
                print(f"No table for {y-1}-{y}, skipping.")
        except Exception as e:
            print(f"Error on {y-1}-{y}: {e}")

    if not all_dfs:
        return pd.DataFrame(columns=[
            "season","team","home_gms","home_avg","road_gms","road_avg","overall_gms","overall_avg"
        ])

    out = pd.concat(all_dfs, ignore_index=True)
    # Optional cleanup: ensure integers
    int_cols = ["home_gms","home_avg","road_gms","road_avg","overall_gms","overall_avg"]
    for c in int_cols:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")

    return out

# === Run for 2000-01 through 2024-25 ===
df = scrape_attendance_range(start_end_year=2001, end_end_year=2025, sleep_sec=0.2)
print(df.head())
df.to_csv("nba_attendance_2000-01_to_2024-25.csv", index=False)
print("Saved: nba_attendance_2000-01_to_2024-25.csv")
