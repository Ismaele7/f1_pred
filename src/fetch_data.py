import argparse
import sqlite3
import sys
from pathlib import Path
import pandas as pd
import fastf1

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from src.config import CACHE_DIR, DB_PATH, SEASONS
except ModuleNotFoundError:
    from config import CACHE_DIR, DB_PATH, SEASONS

import requests
import time

# Handle unauthenticated livetiming requests gracefully without burning general API rate limit
_orig_send = fastf1.req.LivetimingAuthAdapter.send

def _custom_livetiming_send(self, request, **kwargs):
    token = self._get_token()
    if token is None:
        resp = requests.Response()
        resp.status_code = 401
        resp.url = request.url
        resp._content = b""
        return resp
    return _orig_send(self, request, **kwargs)

fastf1.req.LivetimingAuthAdapter.send = _custom_livetiming_send

def _safe_limit(self):
    self._timestamps.append(time.time())

fastf1.req._CallsPerIntervalLimitRaise.limit = _safe_limit


def init_db(conn: sqlite3.Connection):
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        year INTEGER NOT NULL,
        round_number INTEGER NOT NULL,
        event_name TEXT NOT NULL,
        circuit_name TEXT NOT NULL,
        session_type TEXT NOT NULL,
        event_date_utc TEXT NOT NULL,
        air_temp_avg REAL,
        track_temp_avg REAL,
        rainfall INTEGER
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS qualifying_results (
        session_id TEXT NOT NULL,
        year INTEGER NOT NULL,
        round_number INTEGER NOT NULL,
        driver_code TEXT NOT NULL,
        team_name TEXT,
        grid_position REAL,
        q1_sec REAL,
        q2_sec REAL,
        q3_sec REAL,
        has_q2 INTEGER NOT NULL,
        has_q3 INTEGER NOT NULL,
        PRIMARY KEY (year, round_number, driver_code),
        FOREIGN KEY (session_id) REFERENCES sessions (session_id)
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS race_results (
        session_id TEXT NOT NULL,
        year INTEGER NOT NULL,
        round_number INTEGER NOT NULL,
        driver_code TEXT NOT NULL,
        team_name TEXT,
        starting_grid REAL,
        finishing_position REAL,
        points REAL,
        status TEXT,
        laps_completed REAL,
        avg_clean_lap_sec REAL,
        PRIMARY KEY (year, round_number, driver_code),
        FOREIGN KEY (session_id) REFERENCES sessions (session_id)
    );
    """)


def insert_df(conn: sqlite3.Connection, table_name: str, df: pd.DataFrame):
    if df.empty:
        return
    cols = list(df.columns)
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({placeholders})"
    records = df.where(pd.notna(df), None).values.tolist()
    conn.executemany(sql, records)


def extract_weather(session) -> tuple[float | None, float | None, int]:
    air_temp = None
    track_temp = None
    rainfall = 0
    try:
        w = session.weather_data
        if w is not None and not w.empty:
            if "AirTemp" in w and w["AirTemp"].notna().any():
                air_temp = float(w["AirTemp"].mean())
            if "TrackTemp" in w and w["TrackTemp"].notna().any():
                track_temp = float(w["TrackTemp"].mean())
            if "Rainfall" in w:
                rainfall = 1 if bool(w["Rainfall"].any()) else 0
    except Exception:
        pass
    return air_temp, track_temp, rainfall


def compute_avg_clean_laps(session_r) -> dict[str, float]:
    try:
        laps = session_r.laps
        if laps is None or laps.empty:
            return {}
        mask = (
            (laps["LapNumber"] != 1)
            & (laps["PitInTime"].isna())
            & (laps["PitOutTime"].isna())
            & (laps["TrackStatus"].astype(str) == "1")
        )
        clean = laps[mask].copy()
        if clean.empty or "LapTime" not in clean:
            return {}
        clean["lap_sec"] = clean["LapTime"].dt.total_seconds()
        clean = clean[clean["lap_sec"] > 0]
        if clean.empty:
            return {}
        driver_col = "Driver" if "Driver" in clean.columns else "DriverNumber"
        return clean.groupby(driver_col)["lap_sec"].mean().to_dict()
    except Exception:
        return {}


def parse_qualifying(session_q, year: int, round_number: int) -> tuple[dict, pd.DataFrame]:
    session_id = f"{year}_{round_number:02d}_Q"
    air_temp, track_temp, rainfall = extract_weather(session_q)
    event_date_utc = pd.to_datetime(session_q.date, utc=True).strftime("%Y-%m-%d %H:%M:%S")

    session_data = {
        "session_id": session_id,
        "year": year,
        "round_number": round_number,
        "event_name": str(session_q.event.get("EventName") or ""),
        "circuit_name": str(session_q.event.get("Location") or session_q.event.get("OfficialEventName") or ""),
        "session_type": "Q",
        "event_date_utc": event_date_utc,
        "air_temp_avg": air_temp,
        "track_temp_avg": track_temp,
        "rainfall": rainfall,
    }

    q_res = session_q.results.copy()
    if q_res.empty:
        raise ValueError(f"Qualifying results empty for {year} R{round_number}")

    driver_codes = q_res["Abbreviation"].fillna(q_res["DriverNumber"].astype(str)).astype(str)
    q1_sec = q_res["Q1"].dt.total_seconds()
    q2_sec = q_res["Q2"].dt.total_seconds()
    q3_sec = q_res["Q3"].dt.total_seconds()

    df_quali = pd.DataFrame({
        "session_id": session_id,
        "year": year,
        "round_number": round_number,
        "driver_code": driver_codes,
        "team_name": q_res["TeamName"].astype(str),
        "grid_position": q_res["Position"],
        "q1_sec": q1_sec,
        "q2_sec": q2_sec,
        "q3_sec": q3_sec,
        "has_q2": q_res["Q2"].notna().astype(int),
        "has_q3": q_res["Q3"].notna().astype(int),
    })

    assert not df_quali.duplicated(subset=["year", "round_number", "driver_code"]).any(), (
        f"Duplicates found in qualifying results for {year} R{round_number}"
    )
    return session_data, df_quali


def parse_race(session_r, year: int, round_number: int) -> tuple[dict, pd.DataFrame]:
    session_id = f"{year}_{round_number:02d}_R"
    air_temp, track_temp, rainfall = extract_weather(session_r)
    event_date_utc = pd.to_datetime(session_r.date, utc=True).strftime("%Y-%m-%d %H:%M:%S")

    session_data = {
        "session_id": session_id,
        "year": year,
        "round_number": round_number,
        "event_name": str(session_r.event.get("EventName") or ""),
        "circuit_name": str(session_r.event.get("Location") or session_r.event.get("OfficialEventName") or ""),
        "session_type": "R",
        "event_date_utc": event_date_utc,
        "air_temp_avg": air_temp,
        "track_temp_avg": track_temp,
        "rainfall": rainfall,
    }

    r_res = session_r.results.copy()
    if r_res.empty:
        raise ValueError(f"Race results empty for {year} R{round_number}")

    driver_codes = r_res["Abbreviation"].fillna(r_res["DriverNumber"].astype(str)).astype(str)
    avg_clean_lap_dict = compute_avg_clean_laps(session_r)

    df_race = pd.DataFrame({
        "session_id": session_id,
        "year": year,
        "round_number": round_number,
        "driver_code": driver_codes,
        "team_name": r_res["TeamName"].astype(str),
        "starting_grid": r_res["GridPosition"],
        "finishing_position": r_res["Position"],
        "points": r_res["Points"],
        "status": r_res["Status"].astype(str),
        "laps_completed": r_res["Laps"],
        "avg_clean_lap_sec": driver_codes.map(avg_clean_lap_dict),
    })

    assert not df_race.duplicated(subset=["year", "round_number", "driver_code"]).any(), (
        f"Duplicates found in race results for {year} R{round_number}"
    )
    return session_data, df_race


def fetch_data(force_refresh: bool = False):
    fastf1.Cache.enable_cache(str(CACHE_DIR))
    fastf1.set_log_level("WARNING")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    if force_refresh:
        with conn:
            for y in SEASONS:
                conn.execute("DELETE FROM qualifying_results WHERE year = ?", (y,))
                conn.execute("DELETE FROM race_results WHERE year = ?", (y,))
                conn.execute("DELETE FROM sessions WHERE year = ?", (y,))

    now_utc = pd.Timestamp.now(tz="UTC")

    for year in SEASONS:
        sched = fastf1.get_event_schedule(year, include_testing=False)
        for _, event in sched.iterrows():
            round_number = int(event["RoundNumber"])
            if round_number <= 0:
                continue

            event_date_utc = pd.to_datetime(event.get("Session5DateUtc"), utc=True)
            if pd.isna(event_date_utc):
                event_date_utc = pd.to_datetime(event.get("EventDate"), utc=True)

            if event_date_utc > now_utc:
                continue

            sessions_in_event = [event.get(f"Session{i}") for i in range(1, 6)]
            if "Qualifying" not in sessions_in_event or "Race" not in sessions_in_event:
                continue

            if not force_refresh:
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) FROM race_results WHERE year = ? AND round_number = ?",
                    (year, round_number),
                )
                if cur.fetchone()[0] > 0:
                    continue

            try:
                s_q = fastf1.get_session(year, round_number, "Q")
                s_q.load(laps=True, telemetry=False, weather=True)

                s_r = fastf1.get_session(year, round_number, "R")
                s_r.load(laps=True, telemetry=False, weather=True)

                q_session, df_quali = parse_qualifying(s_q, year, round_number)
                r_session, df_race = parse_race(s_r, year, round_number)
                df_sessions = pd.DataFrame([q_session, r_session])

                with conn:
                    conn.execute(
                        "DELETE FROM qualifying_results WHERE year = ? AND round_number = ?",
                        (year, round_number),
                    )
                    conn.execute(
                        "DELETE FROM race_results WHERE year = ? AND round_number = ?",
                        (year, round_number),
                    )
                    conn.execute(
                        "DELETE FROM sessions WHERE year = ? AND round_number = ?",
                        (year, round_number),
                    )
                    insert_df(conn, "sessions", df_sessions)
                    insert_df(conn, "qualifying_results", df_quali)
                    insert_df(conn, "race_results", df_race)

            except Exception:
                continue

    for table in ["sessions", "qualifying_results", "race_results"]:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
        print(f"Table: {table}")
        print(f"Row count: {len(df)}")
        print(df.isna().sum())
        print()

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Fetch F1 data and store into SQLite DB.")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Clean and re-insert data for configured SEASONS.",
    )
    args = parser.parse_args()
    fetch_data(force_refresh=args.force_refresh)


if __name__ == "__main__":
    main()
