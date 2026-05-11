"""
create_db.py
Creates the SQLite database and all 7 tables for "The 15-Minute Divide".
Run this before load_data.py.
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "the_15_minute_divide.db")


def create_database():
    # Remove existing DB so we start fresh
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing database at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Enable foreign key enforcement
    cur.execute("PRAGMA foreign_keys = ON;")

    # ------------------------------------------------------------------
    # 1. countries
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE countries (
            country_code VARCHAR(2) PRIMARY KEY,
            country_name VARCHAR(100) NOT NULL
        );
    """)

    # ------------------------------------------------------------------
    # 2. nuts2_regions
    # urban_rural_typology is a roll-up from NUTS-3 children (dominant
    # category, ties broken urban > intermediate > rural). Stored here
    # as a denormalised attribute so dashboard queries don't need a
    # GROUP BY across nuts3_regions on every request.
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE nuts2_regions (
            nuts2_code           VARCHAR(4)  PRIMARY KEY,
            country_code         VARCHAR(2)  NOT NULL,
            region_name          VARCHAR(200) NOT NULL,
            urban_rural_typology VARCHAR(25)  NOT NULL,
            FOREIGN KEY (country_code) REFERENCES countries(country_code)
        );
    """)

    # ------------------------------------------------------------------
    # 3. nuts3_regions
    # Holds the official Eurostat NUTS-3 urban-rural typology
    # (NUTS 2021 boundaries). Region names are not provided by the
    # typology source, so they may fall back to the NUTS-3 code.
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE nuts3_regions (
            nuts3_code           VARCHAR(5)  PRIMARY KEY,
            nuts2_code           VARCHAR(4)  NOT NULL,
            region_name          VARCHAR(200),
            urban_rural_typology VARCHAR(25)  NOT NULL,
            FOREIGN KEY (nuts2_code) REFERENCES nuts2_regions(nuts2_code)
        );
    """)

    # ------------------------------------------------------------------
    # 4. transport_infrastructure
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE transport_infrastructure (
            id                          INTEGER PRIMARY KEY AUTOINCREMENT,
            nuts2_code                  VARCHAR(4) NOT NULL,
            year                        INTEGER    NOT NULL,
            railway_density_per_1000km2 REAL,
            motorway_density_per_1000km2 REAL,
            motorisation_rate_per_1000  REAL,
            FOREIGN KEY (nuts2_code) REFERENCES nuts2_regions(nuts2_code)
        );
    """)

    # ------------------------------------------------------------------
    # 5. employment_outcomes
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE employment_outcomes (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            nuts2_code           VARCHAR(4) NOT NULL,
            year                 INTEGER    NOT NULL,
            employment_rate_pct  REAL,
            unemployment_rate_pct REAL,
            FOREIGN KEY (nuts2_code) REFERENCES nuts2_regions(nuts2_code)
        );
    """)

    # ------------------------------------------------------------------
    # 6. education_outcomes
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE education_outcomes (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            nuts2_code              VARCHAR(4) NOT NULL,
            year                    INTEGER    NOT NULL,
            tertiary_attainment_pct REAL,
            early_leavers_pct       REAL,
            FOREIGN KEY (nuts2_code) REFERENCES nuts2_regions(nuts2_code)
        );
    """)

    # ------------------------------------------------------------------
    # 7. health_outcomes
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE health_outcomes (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            nuts2_code             VARCHAR(4) NOT NULL,
            year                   INTEGER    NOT NULL,
            life_expectancy_at_birth REAL,
            physicians_per_100k    REAL,
            FOREIGN KEY (nuts2_code) REFERENCES nuts2_regions(nuts2_code)
        );
    """)

    # ------------------------------------------------------------------
    # 8. economic_outcomes
    # GDP per capita in purchasing power standards (PPS) so values are
    # comparable across countries with different price levels.
    # ------------------------------------------------------------------
    cur.execute("""
        CREATE TABLE economic_outcomes (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            nuts2_code          VARCHAR(4) NOT NULL,
            year                INTEGER    NOT NULL,
            gdp_per_capita_pps  REAL,
            FOREIGN KEY (nuts2_code) REFERENCES nuts2_regions(nuts2_code)
        );
    """)

    conn.commit()
    conn.close()
    print(f"Database created successfully at {DB_PATH}")
    print("Tables created: countries, nuts2_regions, nuts3_regions,")
    print("  transport_infrastructure, employment_outcomes,")
    print("  education_outcomes, health_outcomes, economic_outcomes")


if __name__ == "__main__":
    create_database()
