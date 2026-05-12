import pandas as pd
import mysql.connector
from mysql.connector import errorcode
import numpy as np
import warnings

# Suppress SettingWithCopyWarning, adjusting for different Pandas versions
try:
    # Modern Pandas (>= 1.5)
    warnings.filterwarnings('ignore', category=pd.errors.SettingWithCopyWarning)
except AttributeError:
    # Older Pandas (< 1.5)
    warnings.filterwarnings('ignore', category=pd.core.common.SettingWithCopyWarning)


# --- Configuration ---
DB_CONFIG = {
    'user': 'testuser2',
    'password': '[aaA$SANTI$123]',
    'host': '34.66.156.27',
    'database': 'NBAdatabase'
}

# --- Helper Functions ---

def convert_season(season):
    """
    Standardizes the season string format to 'YYYY-YY'.
    Converts 'YYYY-YYYY' (e.g., '2003-2004') to 'YYYY-YY' (e.g., '2003-04').
    """
    if pd.options.mode.use_inf_as_na and pd.isna(season):
        return None
    try:
        season_str = str(season).strip()
        parts = season_str.split('-')
        
        if len(parts) == 2:
            start_year = parts[0]
            end_part = parts[1]
            
            if len(start_year) == 4 and start_year.isdigit():
                # Case 1: Already 'YYYY-YY' format (e.g., '2023-24')
                if len(end_part) == 2 and end_part.isdigit():
                    return season_str
                
                # Case 2: 'YYYY-YYYY' format (e.g., '2003-2004')
                elif len(end_part) == 4 and end_part.isdigit():
                    # Format as 'YYYY-YY'
                    return f"{start_year}-{end_part[2:]}"
        
        return None
    except:
        return None

def load_csv_data(file_path):
    """Loads a CSV file into a pandas DataFrame."""
    try:
        # Assuming the CSVs use a comma delimiter and UTF-8 encoding
        return pd.read_csv(file_path, encoding='utf-8')
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}. Skipping.")
        return None
    except Exception as e:
        print(f"Error reading {file_path}: {e}. Skipping.")
        return None

def preprocess_data():
    """Reads, cleans, and transforms all necessary CSV data into DataFrames ready for insertion."""
    print("Starting data preprocessing...")

    # Load all raw files
    raw_dfs = {
        'teams': load_csv_data('teams.csv'),
        'player': load_csv_data('player.csv'),
        'history': load_csv_data('player team history.csv'),
        'awards_raw': load_csv_data('player awards.csv'),
        'stats_raw': load_csv_data('Player data.csv'),
        'standings_raw': load_csv_data('nba_standings_2002_2003_to_2024_2025_espn.csv'),
        'attendance_raw': load_csv_data('nba_attendance_2000-01_to_2024-25.csv'),
        'salaries_raw': load_csv_data('nba_salaries_2000-01_to_2024-25.csv')
    }
    if any(df is None for key, df in raw_dfs.items() if key != 'draft'):
        print("Required CSV files are missing or could not be loaded. Aborting preprocessing.")
        return None, None, None, None, None, None, None 

    # --- 1. team table processing ---
    teams_df = raw_dfs['teams']
    teams_df = teams_df[teams_df['Team ID'] != 0].copy()
    teams_df = teams_df[['Team ID', 'Team Name', 'City', 'State', 'Conference', 'Division']].copy()
    teams_df.rename(columns={
        'Team ID': 'TeamID', 'Team Name': 'TeamName', 'City': 'City',
        'State': 'State', 'Conference': 'Conference', 'Division': 'Division'
    }, inplace=True)
    teams_df.drop_duplicates(subset=['TeamID'], inplace=True)
    teams_df['TeamID'] = teams_df['TeamID'].astype(int)
    teams_df['TeamName'] = teams_df['TeamName'].astype(str)
    
    # Create TeamName-to-TeamID mapping for later joins
    team_name_to_id = teams_df.set_index('TeamName')['TeamID'].to_dict()
    print(f"-> Processed {len(teams_df)} unique teams.")

    # --- 2. awardtype table processing ---
    awards_raw_df = raw_dfs['awards_raw']
    award_names = awards_raw_df['Award'].unique()
    award_type_df = pd.DataFrame({
        'AwardName': award_names,
        'AwardTypeID': np.arange(1, len(award_names) + 1),
        'Description': ['Description TBD'] * len(award_names)
    })
    award_type_df.loc[award_type_df['AwardName'] == 'NBA All-Star', 'Description'] = 'Recognition for selection to the NBA All-Star Game'
    award_type_df.loc[award_type_df['AwardName'] == 'NBA Most Valuable Player', 'Description'] = 'Award given to the best performing player of the regular season'
    award_type_df['Description'] = award_type_df['Description'].fillna('').astype(str)
    print(f"-> Processed {len(award_type_df)} unique award types.")

    # --- 3. player table processing ---
    player_df = raw_dfs['player']
    history_df = raw_dfs['history']

    current_teams = history_df[
        (history_df['IsCurrent'] == True) & (history_df['TEAM_ID'] != 0)
    ].copy()
    
    # Standardize Season format in history before sorting/merging
    current_teams['EndSeason'] = current_teams['EndSeason'].apply(convert_season)
    
    current_teams['EndSeason_Sort'] = current_teams['EndSeason'].apply(lambda x: str(x).replace('-', ''))
    current_teams.sort_values(by=['Player_ID', 'EndSeason_Sort'], ascending=False, inplace=True)
    current_teams.drop_duplicates(subset=['Player_ID'], keep='first', inplace=True)

    player_df = pd.merge(player_df, current_teams[['Player_ID', 'TEAM_ID']], on='Player_ID', how='left')
    player_df = player_df.dropna(subset=['TEAM_ID']).copy()
    player_df['TEAM_ID'] = player_df['TEAM_ID'].astype(int)

    player_df.rename(columns={
        'Player_ID': 'PlayerID', 'FullName': 'Name', 'TEAM_ID': 'TeamID',
        'DateOfBirth': 'DateOfBirth', 'SeasonExperience': 'SeasonExperience'
    }, inplace=True)

    player_df = player_df[['PlayerID', 'TeamID', 'Position', 'Name', 'DateOfBirth', 'Height', 'Weight', 'SeasonExperience']].copy()
    player_df['DateOfBirth'] = player_df['DateOfBirth'].astype(str).str.split('T').str[0]
    player_df['Height'] = player_df['Height'].fillna('').astype(str)
    player_df['Position'] = player_df['Position'].fillna('').astype(str)
    player_df.drop_duplicates(subset=['PlayerID'], keep='first', inplace=True)
    
    # Create PlayerName-to-PlayerID mapping for salary joins
    player_name_to_id = player_df.set_index('Name')['PlayerID'].to_dict()
    print(f"-> Processed {len(player_df)} players with current teams.")

    # --- 4. playeraward table processing ---
    player_awards_df = awards_raw_df.copy()
    # Standardize Season format
    player_awards_df['Season'] = player_awards_df['Season'].apply(convert_season)
    player_awards_df = player_awards_df.dropna(subset=['Season']).copy()

    player_awards_df = pd.merge(
        player_awards_df, award_type_df[['AwardName', 'AwardTypeID']],
        left_on='Award', right_on='AwardName', how='left'
    )
    player_awards_df.dropna(subset=['AwardTypeID', 'Player_ID'], inplace=True)
    player_awards_df['AwardTypeID'] = player_awards_df['AwardTypeID'].astype(int)

    player_awards_df['PlayerAwardID'] = np.arange(1, len(player_awards_df) + 1)
    player_awards_df.rename(columns={'Player_ID': 'PlayerID'}, inplace=True)
    player_award_final_df = player_awards_df[['PlayerAwardID', 'PlayerID', 'AwardTypeID', 'Season']].copy()
    print(f"-> Processed {len(player_award_final_df)} player awards.")

    # --- 5. playerstat table processing ---
    player_stat_df = raw_dfs['stats_raw']
    player_stat_df = player_stat_df.dropna(subset=['Player_ID']).copy()
    player_stat_df['PlayerID'] = player_stat_df['Player_ID'].astype(int)
    # Standardize Season format
    player_stat_df['Season'] = player_stat_df['Season'].apply(convert_season)
    player_stat_df = player_stat_df.dropna(subset=['Season']).copy()

    # Rename and round columns
    player_stat_df.rename(columns={
        'MIN': 'MinutesPlayedPerGame', 'FG_PCT': 'FieldGoalPercentage', 'FG3_PCT': 'ThreePointPercentage', 'FT_PCT': 'FreeThrowPercentage',
        'PTS': 'PointsPerGame', 'AST': 'AssistsPerGame', 'REB': 'ReboundsPerGame',
        'STL': 'StealsPerGame', 'BLK': 'BlocksPerGame', 'TOV': 'TurnoversPerGame'
    }, inplace=True)

    # Apply rounding
    player_stat_df['MinutesPlayedPerGame'] = player_stat_df['MinutesPlayedPerGame'].round(1)
    player_stat_df['FieldGoalPercentage'] = player_stat_df['FieldGoalPercentage'].round(3)
    player_stat_df['ThreePointPercentage'] = player_stat_df['ThreePointPercentage'].round(3)
    player_stat_df['FreeThrowPercentage'] = player_stat_df['FreeThrowPercentage'].round(3)
    player_stat_df['PointsPerGame'] = player_stat_df['PointsPerGame'].round(2)
    player_stat_df['AssistsPerGame'] = player_stat_df['AssistsPerGame'].round(2)
    player_stat_df['ReboundsPerGame'] = player_stat_df['ReboundsPerGame'].round(2)
    player_stat_df['StealsPerGame'] = player_stat_df['StealsPerGame'].round(2)
    player_stat_df['BlocksPerGame'] = player_stat_df['BlocksPerGame'].round(2)
    player_stat_df['TurnoversPerGame'] = player_stat_df['TurnoversPerGame'].round(2)

    player_stat_final_df = player_stat_df[[
        'PlayerID', 'Season', 'PointsPerGame', 'AssistsPerGame', 'ReboundsPerGame',
        'StealsPerGame', 'BlocksPerGame', 'TurnoversPerGame', 'MinutesPlayedPerGame',
        'FieldGoalPercentage', 'ThreePointPercentage', 'FreeThrowPercentage'
    ]].copy()
    player_stat_final_df.drop_duplicates(subset=['PlayerID', 'Season'], keep='first', inplace=True)
    print(f"-> Processed {len(player_stat_final_df)} player season stats.")

    # --- 6. salary table processing ---
    salaries_df = raw_dfs['salaries_raw'].copy()
    # Standardize Season format
    salaries_df['Season'] = salaries_df['season'].apply(convert_season)
    salaries_df.dropna(subset=['Name', 'Season'], inplace=True)
    
    salaries_df['SalaryAmount'] = (
        salaries_df['Salary']
        .astype(str)
        .str.replace('$', '', regex=False)
        .str.replace(',', '', regex=False)
    )
    # Convert to numeric, errors='coerce' turns invalid strings (like 'nan') into NaN
    salaries_df['SalaryAmount'] = pd.to_numeric(salaries_df['SalaryAmount'], errors='coerce')
    
    salaries_df['PlayerID'] = salaries_df['Name'].map(player_name_to_id)
    
    # Filter for players found in the Player table and drop rows where salary conversion failed
    salaries_final_df = salaries_df.dropna(subset=['PlayerID', 'SalaryAmount']).copy()
    salaries_final_df['PlayerID'] = salaries_final_df['PlayerID'].astype(int)
    salaries_final_df['SalaryID'] = np.arange(1, len(salaries_final_df) + 1)
    salaries_final_df = salaries_final_df[['SalaryID', 'PlayerID', 'SalaryAmount', 'Season']].copy()
    print(f"-> Processed {len(salaries_final_df)} player salaries.")

    # --- 7. teamseasonstat table processing ---
    standings_df = raw_dfs['standings_raw'].copy()
    attendance_df = raw_dfs['attendance_raw'].copy()

    # Clean Standings Data
    standings_df.rename(columns={'season': 'Season', 'team_name': 'TeamName', 'wins': 'Wins', 'losses': 'Losses', 'league_rank': 'SeasonRank'}, inplace=True)
    # Standardize Season format
    standings_df['Season'] = standings_df['Season'].apply(convert_season)
    standings_df.dropna(subset=['Season', 'TeamName'], inplace=True)
    
    # FIX: Robust splitting logic for home/road records
    standings_df['home'] = standings_df['home'].astype(str)
    standings_df['road'] = standings_df['road'].astype(str)
    
    # Processing 'home'
    home_split_cols = standings_df['home'].str.split('-', expand=True, n=1)
    if home_split_cols.shape[1] == 1:
        home_split_cols.loc[:, 1] = '0' # Add a 'Losses' column with '0' if only 'Wins' were present

    # Processing 'road'
    road_split_cols = standings_df['road'].str.split('-', expand=True, n=1)
    if road_split_cols.shape[1] == 1:
        road_split_cols.loc[:, 1] = '0' # Add a 'Losses' column with '0' if only 'Wins' were present

    # Assign the two guaranteed columns
    standings_df.loc[:, 'HomeWins'] = home_split_cols[0]
    standings_df.loc[:, 'HomeLosses'] = home_split_cols[1]
    standings_df.loc[:, 'AwayWins'] = road_split_cols[0]
    standings_df.loc[:, 'AwayLosses'] = road_split_cols[1]
    
    # Convert extracted win/loss columns to numeric
    standings_df['HomeWins'] = pd.to_numeric(standings_df['HomeWins'], errors='coerce').fillna(0).astype(int)
    standings_df['HomeLosses'] = pd.to_numeric(standings_df['HomeLosses'], errors='coerce').fillna(0).astype(int)
    standings_df['AwayWins'] = pd.to_numeric(standings_df['AwayWins'], errors='coerce').fillna(0).astype(int)
    standings_df['AwayLosses'] = pd.to_numeric(standings_df['AwayLosses'], errors='coerce').fillna(0).astype(int)

    standings_df.drop(columns=['home', 'road', 'HomeLosses', 'AwayLosses'], inplace=True)
    
    # Clean Attendance Data
    attendance_df.rename(columns={'season': 'Season', 'team': 'TeamName', 'overall_avg': 'AttendanceCount'}, inplace=True)
    # Standardize Season format
    attendance_df['Season'] = attendance_df['Season'].apply(convert_season)
    attendance_df.dropna(subset=['Season', 'TeamName'], inplace=True)
    attendance_df['AttendanceCount'] = attendance_df['AttendanceCount'].astype(int) 

    # Merge Standings and Attendance
    team_stats_df = pd.merge(
        standings_df[['Season', 'TeamName', 'Wins', 'Losses', 'HomeWins', 'AwayWins', 'SeasonRank']],
        attendance_df[['Season', 'TeamName', 'AttendanceCount']],
        on=['Season', 'TeamName'],
        how='left'
    )
    
    # Map Team Name to TeamID (Requires careful matching)
    team_name_mapping = {
        'Boston Celtics': 'Celtics', 'Brooklyn Nets': 'Nets', 'New Jersey Nets': 'Nets',
        'New York Knicks': 'Knicks', 'Philadelphia 76ers': '76ers', 'Toronto Raptors': 'Raptors',
        'Chicago Bulls': 'Bulls', 'Cleveland Cavaliers': 'Cavaliers', 'Detroit Pistons': 'Pistons',
        'Indiana Pacers': 'Pacers', 'Milwaukee Bucks': 'Bucks',
        'Atlanta Hawks': 'Hawks', 'Charlotte Hornets': 'Hornets', 'Orlando Magic': 'Magic',
        'Miami Heat': 'Heat', 'Washington Wizards': 'Wizards',
        'Denver Nuggets': 'Nuggets', 'Minnesota Timberwolves': 'Timberwolves', 'Oklahoma City Thunder': 'Thunder',
        'Portland Trail Blazers': 'Trail Blazers', 'Utah Jazz': 'Jazz',
        'Golden State Warriors': 'Warriors', 'LA Clippers': 'Clippers', 'Los Angeles Clippers': 'Clippers',
        'Los Angeles Lakers': 'Lakers', 'Phoenix Suns': 'Suns', 'Sacramento Kings': 'Kings',
        'Dallas Mavericks': 'Mavericks', 'Houston Rockets': 'Rockets', 'Memphis Grizzlies': 'Grizzlies',
        'New Orleans Pelicans': 'Pelicans', 'San Antonio Spurs': 'Spurs',
        'New Orleans Hornets': 'Pelicans', 'Charlotte Bobcats': 'Hornets',
        'Seattle SuperSonics': 'Thunder' 
    }

    # Apply the standard name mapping
    team_stats_df['StandardTeamName'] = team_stats_df['TeamName'].map(team_name_mapping).fillna(team_stats_df['TeamName'])
    team_stats_df['TeamID'] = team_stats_df['StandardTeamName'].map(team_name_to_id)
    
    # Final cleanup and selection
    team_stats_final_df = team_stats_df.dropna(subset=['TeamID', 'Season']).copy()
    team_stats_final_df['TeamID'] = team_stats_final_df['TeamID'].astype(int)
    team_stats_final_df['AttendanceCount'] = team_stats_final_df['AttendanceCount'].fillna(0).astype(int)
    
    team_stats_final_df = team_stats_final_df[['TeamID', 'Season', 'Wins', 'Losses', 'HomeWins', 'AwayWins', 'AttendanceCount', 'SeasonRank']].copy()
    team_stats_final_df.drop_duplicates(subset=['TeamID', 'Season'], keep='first', inplace=True)
    print(f"-> Processed {len(team_stats_final_df)} team season stats.")


    return teams_df, award_type_df, player_df, player_award_final_df, player_stat_final_df, salaries_final_df, team_stats_final_df

def insert_data_to_mysql(conn, cursor, table_name, df, columns):
    """Dynamically creates and executes INSERT statements for a given DataFrame."""
    if df.empty:
        print(f"  [SKIPPED] {table_name}: DataFrame is empty.")
        return

    # Build the INSERT query
    cols = ', '.join([f'`{col}`' for col in columns])
    placeholders = ', '.join(['%s'] * len(columns))
    insert_query = f"INSERT INTO `{table_name}` ({cols}) VALUES ({placeholders})"

    # Prepare data rows for execution
    data_to_insert = []
    for _, row in df.iterrows():
        # Convert pandas/numpy types to native Python types (int, float, str, None)
        data_row = []
        for val in row[columns]:
            if pd.options.mode.use_inf_as_na and pd.isna(val):
                data_row.append(None)
            elif isinstance(val, (np.int64, np.int32)):
                data_row.append(int(val))
            elif isinstance(val, (np.float64, np.float32)):
                data_row.append(float(val))
            else:
                data_row.append(val)
        data_to_insert.append(tuple(data_row))

    print(f"  [INSERTING] {table_name}: {len(data_to_insert)} records...")
    
    try:
        cursor.executemany(insert_query, data_to_insert)
        conn.commit()
        print(f"  [SUCCESS] {table_name} populated.")
    except mysql.connector.Error as err:
        print(f"  [ERROR] Failed to insert data into {table_name}: {err.msg}")
        conn.rollback()

def main():
    """Main function to run the ETL process."""
    # 1. Preprocess data
    teams_df, award_type_df, player_df, player_award_df, player_stat_df, salaries_df, team_stats_df = preprocess_data()
    
    if teams_df is None:
        return

    # 2. Database connection
    try:
        print(f"\nAttempting to connect to MySQL database: {DB_CONFIG['database']}...")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("Connection successful.")

    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("ERROR: Authentication failed. Check your user name or password in DB_CONFIG.")
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("ERROR: Database does not exist. Please create the 'NBAdatabase' first.")
        else:
            print(f"ERROR: {err}")
        return

    # 3. Insert data into tables (respecting FK constraints)
    print("\nStarting data insertion into NBAdatabase...")

    # Group 1: Base Tables (No External FKs)
    insert_data_to_mysql(conn, cursor, 'team', teams_df, teams_df.columns.tolist())
    insert_data_to_mysql(conn, cursor, 'awardtype', award_type_df, award_type_df.columns.tolist())

    # Group 2: Player-Related (Requires TeamID)
    insert_data_to_mysql(conn, cursor, 'player', player_df, player_df.columns.tolist())

    # Group 3: Stats/Awards/Salary (Requires PlayerID/TeamID/AwardTypeID)
    insert_data_to_mysql(conn, cursor, 'playeraward', player_award_df, player_award_df.columns.tolist())
    insert_data_to_mysql(conn, cursor, 'playerstat', player_stat_df, player_stat_df.columns.tolist())
    insert_data_to_mysql(conn, cursor, 'salary', salaries_df, salaries_df.columns.tolist())
    insert_data_to_mysql(conn, cursor, 'teamseasonstat', team_stats_df, team_stats_df.columns.tolist())

    # 4. Cleanup
    cursor.close()
    conn.close()
    print("\nData loading complete and connection closed.")

if __name__ == '__main__':
    main()