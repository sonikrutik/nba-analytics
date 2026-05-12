import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time

def scrape_espn_salaries_season(end_year, sleep_sec=0.3, session=None):
    """
    Scrape a single NBA season from ESPN salaries pages.
    end_year: season end year (e.g., 2024 for 2023-24 season)
    Returns: DataFrame with columns: season, Name, Team, Salary
    """
    base = f"https://www.espn.com/nba/salaries/_/year/{end_year}/page/"
    rows = []
    p = 1

    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})

    while True:
        url = base + str(p)
        r = session.get(url, timeout=20)
        if r.status_code == 404:
            # No such page/season page
            break
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "lxml")

        # Primary selector (stable on ESPN)
        table = soup.select_one("#my-players-table table.tablehead")
        if not table:
            # Fallback: any table with the expected header cells
            tables = soup.select("table.tablehead")
            if tables:
                table = tables[0]

        page_rows = 0
        if table:
            for tr in table.select("tr"):
                tds = tr.find_all("td")
                if len(tds) != 4:
                    continue
                # Skip header rows (they repeat per page)
                if tds[0].get_text(strip=True).upper() == "RK":
                    continue

                name_raw = tds[1].get_text(" ", strip=True)  # e.g., "Stephen Curry, G"
                team     = tds[2].get_text(" ", strip=True)
                salary   = tds[3].get_text(strip=True)       # e.g., "$51,915,615"

                # Clean name: drop trailing ", G"/", F"/", C" etc.
                name = name_raw.split(",")[0].strip()

                # Salary -> int (None if missing)
                salary_num = int(re.sub(r"[^\d]", "", salary)) if salary else None

                # Proper season label: start-end (e.g., 2023-2024)
                season = f"{end_year-1}-{end_year}"

                rows.append({"season": season, "Name": name, "Team": team, "Salary": salary_num})
                page_rows += 1

        # If this page had no data rows, we're done
        if page_rows == 0:
            break

        p += 1
        if sleep_sec:
            time.sleep(sleep_sec)

    return pd.DataFrame(rows)


def scrape_espn_salaries_range(start_end_year=2001, end_end_year=2025, sleep_sec=0.3):
    """
    Scrape multiple seasons by ESPN 'end year' (inclusive).
    Example: start_end_year=2001 -> 2000-01, end_end_year=2025 -> 2024-25.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})

    all_dfs = []
    for y in range(start_end_year, end_end_year + 1):
        try:
            df_season = scrape_espn_salaries_season(y, sleep_sec=sleep_sec, session=session)
            if not df_season.empty:
                all_dfs.append(df_season)
                print(f"Scraped season {y-1}-{y}: {len(df_season)} rows")
            else:
                print(f"No data for season {y-1}-{y} (skipping).")
        except requests.HTTPError as e:
            print(f"HTTP error for season {y-1}-{y}: {e}")
        except Exception as e:
            print(f"Error for season {y-1}-{y}: {e}")

    if all_dfs:
        out = pd.concat(all_dfs, ignore_index=True)
        # Optional: drop exact duplicates just in case
        out = out.drop_duplicates(subset=["season", "Name", "Team", "Salary"])
        return out
    else:
        return pd.DataFrame(columns=["season", "Name", "Team", "Salary"])


# === Run the full scrape ===
# 2000-01 through 2024-25 corresponds to end years 2001..2025
df = scrape_espn_salaries_range(start_end_year=2001, end_end_year=2025, sleep_sec=0.25)

# Save
df.to_csv("nba_salaries_2000-01_to_2024-25.csv", index=False)

print(df.head())
print("Total rows:", len(df))
