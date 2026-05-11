"""
load_data.py
Cleans and loads all Eurostat datasets into the_15_minute_divide.db.
Run create_db.py first to initialise the schema.

Dataset inventory:
  NUTS2021_urban_rural.xlsx          → nuts3_regions (real urban-rural typology)
  tran_r_net_linear_2_0.csv.gz       → transport_infrastructure (railway/motorway density)
  tran_r_vehst_linear_2_0.csv.gz     → transport_infrastructure (motorisation rate)
  lfst_r_lfe2emprt_linear_2_0.csv.gz → employment_outcomes (employment rate)
  lfst_r_lfu3rt_linear_2_0.csv.gz    → employment_outcomes (unemployment rate)
  edat_lfse_04_linear_2_0.csv.gz     → education_outcomes (tertiary attainment)
  edat_lfse_16_linear_2_0.csv.gz     → education_outcomes (early leavers)
  demo_r_mlifexp_linear_2_0.csv.gz   → health_outcomes (life expectancy)
  hlth_rs_prsrg_linear_2_0.csv.gz    → health_outcomes (physicians per 100k)
  nama_10r_2gdp_linear_2_0.csv.gz    → economic_outcomes (GDP per capita, PPS)

Urban-rural typology comes from the official Eurostat NUTS 2021 spreadsheet.
NUTS-2 regions get a denormalised "dominant typology" column rolled up from
their NUTS-3 children (most common category, ties broken urban >
intermediate > rural). NUTS-2 regions that do not appear in the NUTS 2021
typology (NUTS 2024-only codes, extra-regio "ZZ" aggregates) are dropped
along with any outcome rows referencing them.
"""

import sqlite3
import os

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR  = os.path.join(BASE_DIR, "data", "raw")
DB_PATH  = os.path.join(os.path.dirname(__file__), "the_15_minute_divide.db")


def raw_path(filename):
    return os.path.join(RAW_DIR, filename)


# ---------------------------------------------------------------------------
# EU-27 reference data
# ---------------------------------------------------------------------------
EU27_COUNTRIES = {
    "AT": "Austria",      "BE": "Belgium",    "BG": "Bulgaria",
    "CY": "Cyprus",       "CZ": "Czechia",    "DE": "Germany",
    "DK": "Denmark",      "EE": "Estonia",    "EL": "Greece",
    "ES": "Spain",        "FI": "Finland",    "FR": "France",
    "HR": "Croatia",      "HU": "Hungary",    "IE": "Ireland",
    "IT": "Italy",        "LT": "Lithuania",  "LU": "Luxembourg",
    "LV": "Latvia",       "MT": "Malta",      "NL": "Netherlands",
    "PL": "Poland",       "PT": "Portugal",   "RO": "Romania",
    "SE": "Sweden",       "SI": "Slovenia",   "SK": "Slovakia",
}

# Typology category labels used throughout the database. The official
# Eurostat spreadsheet contains a typo on the urban label
# ("perdominantly urban") which is normalised here.
TYPOLOGY_LABELS = {
    1: "predominantly urban",
    2: "intermediate",
    3: "predominantly rural",
}

# Priority for breaking ties when rolling NUTS-3 typologies up to NUTS-2.
# A NUTS-2 region with equal counts of two categories is classified as the
# more-urban one — large NUTS-2 regions tend to anchor on their main city.
TYPOLOGY_TIE_PRIORITY = {
    "predominantly urban": 0,
    "intermediate":        1,
    "predominantly rural": 2,
}


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def is_nuts2_eu27(series):
    """Boolean mask: True for EU-27 NUTS-2 codes (exactly 4 chars)."""
    s = series.astype(str)
    return (s.str.len() == 4) & (s.str[:2].isin(EU27_COUNTRIES.keys()))


def extract_code_from_combined(series):
    """'AT11: Burgenland' → 'AT11'  (handles combined SDMX-CSV 2.0 format)."""
    return series.astype(str).str.split(": ").str[0]


def best_year_for(df, geo_col, time_col, value_col, min_coverage=0.80):
    """
    Return the most recent year where ≥ min_coverage of reporting
    regions have a non-null value; fall back to the year with most obs.
    """
    n_regions = df[geo_col].nunique()
    for yr in sorted(df[time_col].dropna().unique(), reverse=True):
        n_valid = df[df[time_col] == yr][value_col].notna().sum()
        if n_regions > 0 and (n_valid / n_regions) >= min_coverage:
            return int(yr)
    counts = df.groupby(time_col)[value_col].count()
    return int(counts.idxmax())


def filter_best_year(df, geo_col, time_col, value_col):
    yr = best_year_for(df, geo_col, time_col, value_col)
    subset = df[df[time_col] == yr].copy()
    print(f"    → year {yr}, {subset[value_col].notna().sum()} regions")
    return subset, yr


def to_float_or_none(val):
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def to_int_or_none(val):
    try:
        f = float(val)
        return None if pd.isna(f) else int(f)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Dataset loaders — each returns a tidy DataFrame:
#   nuts2_code (str), year (int), [metric columns] (float)
# ---------------------------------------------------------------------------

# ---------- Transport ----------

def load_railway_motorway():
    """
    tran_r_net → railway_density_per_1000km2, motorway_density_per_1000km2
    Unit: KM_TKM2 (already a density — km per 1000 km²).
    Format: combined SDMX-CSV (geo = 'AT11: Burgenland').
    """
    print("\n  tran_r_net (railway + motorway density)")
    df = pd.read_csv(raw_path("tran_r_net_linear_2_0.csv.gz"), low_memory=False)

    geo_col   = "geo: Geopolitical entity (reporting)"
    infr_col  = "tra_infr: Transport infrastructure"
    unit_col  = "unit: Unit of measure"
    val_col   = "OBS_VALUE: Observation value"
    time_col  = "TIME_PERIOD: Time"

    df["nuts2_code"] = extract_code_from_combined(df[geo_col])
    df = df[is_nuts2_eu27(df["nuts2_code"])].copy()
    df = df[df[unit_col] == "KM_TKM2: Kilometres per thousand square kilometres"].copy()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df[df[val_col].notna()].copy()

    # Railway
    rail_df, yr_r = filter_best_year(
        df[df[infr_col] == "RL: Total railway lines"],
        "nuts2_code", time_col, val_col
    )
    rail = rail_df[["nuts2_code", time_col, val_col]].copy()
    rail.columns = ["nuts2_code", "year", "railway_density_per_1000km2"]

    # Motorway
    mway_df, yr_m = filter_best_year(
        df[df[infr_col] == "MWAY: Motorways"],
        "nuts2_code", time_col, val_col
    )
    mway = mway_df[["nuts2_code", time_col, val_col]].copy()
    mway.columns = ["nuts2_code", "year", "motorway_density_per_1000km2"]

    # Merge: keep year from railway as reference
    merged = rail.merge(
        mway[["nuts2_code", "motorway_density_per_1000km2"]],
        on="nuts2_code", how="outer"
    )
    # For regions only in motorway data, fill year from yr_m
    if merged["year"].isna().any():
        merged["year"] = merged["year"].fillna(yr_r)

    print(f"    → {len(merged)} merged rows")
    return merged


def load_motorisation():
    """
    tran_r_vehst → motorisation_rate_per_1000 (CAR, P_THAB).
    Format: combined SDMX-CSV.
    """
    print("\n  tran_r_vehst (motorisation rate)")
    df = pd.read_csv(raw_path("tran_r_vehst_linear_2_0.csv.gz"), low_memory=False)

    geo_col  = "geo: Geopolitical entity (reporting)"
    veh_col  = "vehicle: Vehicles"
    unit_col = "unit: Unit of measure"
    val_col  = "OBS_VALUE: Observation value"
    time_col = "TIME_PERIOD: Time"

    df["nuts2_code"] = extract_code_from_combined(df[geo_col])
    df = df[is_nuts2_eu27(df["nuts2_code"])].copy()
    df = df[df[veh_col] == "CAR: Passenger cars"].copy()
    df = df[df[unit_col] == "P_THAB: Per thousand inhabitants"].copy()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df[df[val_col].notna()].copy()

    df, yr = filter_best_year(df, "nuts2_code", time_col, val_col)
    out = df[["nuts2_code", time_col, val_col]].copy()
    out.columns = ["nuts2_code", "year", "motorisation_rate_per_1000"]
    return out


# ---------- Employment ----------

def load_employment_rate():
    """
    lfst_r_lfe2emprt → employment_rate_pct (age 20-64, total, %).
    Format: combined SDMX-CSV.
    """
    print("\n  lfst_r_lfe2emprt (employment rate)")
    df = pd.read_csv(raw_path("lfst_r_lfe2emprt_linear_2_0.csv.gz"), low_memory=False)

    geo_col  = "geo: Geopolitical entity (reporting)"
    sex_col  = "sex: Sex"
    age_col  = "age: Age class"
    unit_col = "unit: Unit of measure"
    val_col  = "OBS_VALUE: Observation value"
    time_col = "TIME_PERIOD: Time"

    df["nuts2_code"] = extract_code_from_combined(df[geo_col])
    df = df[is_nuts2_eu27(df["nuts2_code"])].copy()
    df = df[df[sex_col]  == "T: Total"].copy()
    df = df[df[age_col]  == "Y20-64: From 20 to 64 years"].copy()
    df = df[df[unit_col] == "PC: Percentage"].copy()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df[df[val_col].notna()].copy()

    df, yr = filter_best_year(df, "nuts2_code", time_col, val_col)
    out = df[["nuts2_code", time_col, val_col]].copy()
    out.columns = ["nuts2_code", "year", "employment_rate_pct"]
    return out


def load_unemployment_rate():
    """
    lfst_r_lfu3rt → unemployment_rate_pct (age 15-74, total all ISCED, %).
    Format: combined SDMX-CSV (has extra isced11 dimension).
    """
    print("\n  lfst_r_lfu3rt (unemployment rate)")
    df = pd.read_csv(raw_path("lfst_r_lfu3rt_linear_2_0.csv.gz"), low_memory=False)

    geo_col   = "geo: Geopolitical entity (reporting)"
    isced_col = ("isced11: International Standard Classification of "
                 "Education (ISCED 2011)")
    sex_col   = "sex: Sex"
    age_col   = "age: Age class"
    unit_col  = "unit: Unit of measure"
    val_col   = "OBS_VALUE: Observation value"
    time_col  = "TIME_PERIOD: Time"

    df["nuts2_code"] = extract_code_from_combined(df[geo_col])
    df = df[is_nuts2_eu27(df["nuts2_code"])].copy()
    df = df[df[isced_col] == "TOTAL: All ISCED 2011 levels"].copy()
    df = df[df[sex_col]   == "T: Total"].copy()
    df = df[df[age_col]   == "Y15-74: From 15 to 74 years"].copy()
    df = df[df[unit_col]  == "PC: Percentage"].copy()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df[df[val_col].notna()].copy()

    df, yr = filter_best_year(df, "nuts2_code", time_col, val_col)
    out = df[["nuts2_code", time_col, val_col]].copy()
    out.columns = ["nuts2_code", "year", "unemployment_rate_pct"]
    return out


# ---------- Education ----------

def load_tertiary_attainment():
    """
    edat_lfse_04 → tertiary_attainment_pct (ISCED 5-8, age 25-34, total).
    Format: split SDMX-CSV (geo = plain code, OBS_VALUE = numeric).
    """
    print("\n  edat_lfse_04 (tertiary attainment)")
    df = pd.read_csv(raw_path("edat_lfse_04_linear_2_0.csv.gz"), low_memory=False)

    geo_col   = "geo"
    isced_col = "isced11"
    sex_col   = "sex"
    age_col   = "age"
    val_col   = "OBS_VALUE"
    time_col  = "TIME_PERIOD"

    df = df[is_nuts2_eu27(df[geo_col].astype(str))].copy()
    df = df[df[isced_col] == "ED5-8"].copy()
    df = df[df[sex_col]   == "T"].copy()
    df = df[df[age_col]   == "Y25-34"].copy()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df[df[val_col].notna()].copy()

    df, yr = filter_best_year(df, geo_col, time_col, val_col)
    out = df[[geo_col, time_col, val_col]].copy()
    out.columns = ["nuts2_code", "year", "tertiary_attainment_pct"]
    return out


def load_early_leavers():
    """
    edat_lfse_16 → early_leavers_pct (age 18-24, total).
    Format: split SDMX-CSV.
    """
    print("\n  edat_lfse_16 (early school leavers)")
    df = pd.read_csv(raw_path("edat_lfse_16_linear_2_0.csv.gz"), low_memory=False)

    geo_col  = "geo"
    sex_col  = "sex"
    age_col  = "age"
    val_col  = "OBS_VALUE"
    time_col = "TIME_PERIOD"

    df = df[is_nuts2_eu27(df[geo_col].astype(str))].copy()
    df = df[df[sex_col] == "T"].copy()
    df = df[df[age_col] == "Y18-24"].copy()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df[df[val_col].notna()].copy()

    df, yr = filter_best_year(df, geo_col, time_col, val_col)
    out = df[[geo_col, time_col, val_col]].copy()
    out.columns = ["nuts2_code", "year", "early_leavers_pct"]
    return out


# ---------- Health ----------

def load_life_expectancy():
    """
    demo_r_mlifexp → life_expectancy_at_birth (Y_LT1 = <1 yr, total, YR).
    Format: combined SDMX-CSV.
    """
    print("\n  demo_r_mlifexp (life expectancy at birth)")
    df = pd.read_csv(raw_path("demo_r_mlifexp_linear_2_0.csv.gz"), low_memory=False)

    geo_col  = "geo: Geopolitical entity (reporting)"
    sex_col  = "sex: Sex"
    age_col  = "age: Age class"
    unit_col = "unit: Unit of measure"
    val_col  = "OBS_VALUE: Observation value"
    time_col = "TIME_PERIOD: Time"

    df["nuts2_code"] = extract_code_from_combined(df[geo_col])
    df = df[is_nuts2_eu27(df["nuts2_code"])].copy()
    df = df[df[sex_col]  == "T: Total"].copy()
    df = df[df[age_col]  == "Y_LT1: Less than 1 year"].copy()
    df = df[df[unit_col] == "YR: Year"].copy()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df[df[val_col].notna()].copy()

    df, yr = filter_best_year(df, "nuts2_code", time_col, val_col)
    out = df[["nuts2_code", time_col, val_col]].copy()
    out.columns = ["nuts2_code", "year", "life_expectancy_at_birth"]
    return out


# ---------- Economic ----------

def load_gdp_per_capita():
    """
    nama_10r_2gdp → gdp_per_capita_pps (PPS_EU27_2020_HAB).

    Purchasing-power-adjusted GDP per inhabitant in PPS units (EU27 2020
    baseline), so values are comparable across countries with different
    price levels — Wien at 54,600 vs. Severozapaden at 12,400 reflects
    real economic output, not exchange-rate noise.

    Format: split SDMX-CSV (geo = bare code, OBS_VALUE = numeric).
    """
    print("\n  nama_10r_2gdp (GDP per capita, PPS)")
    df = pd.read_csv(raw_path("nama_10r_2gdp_linear_2_0.csv.gz"), low_memory=False)

    geo_col  = "geo"
    unit_col = "unit"
    val_col  = "OBS_VALUE"
    time_col = "TIME_PERIOD"

    df = df[is_nuts2_eu27(df[geo_col].astype(str))].copy()
    df = df[df[unit_col] == "PPS_EU27_2020_HAB"].copy()
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df[df[val_col].notna()].copy()

    df, yr = filter_best_year(df, geo_col, time_col, val_col)
    out = df[[geo_col, time_col, val_col]].copy()
    out.columns = ["nuts2_code", "year", "gdp_per_capita_pps"]
    return out


def load_physicians():
    """
    hlth_rs_prsrg → physicians_per_100k (OC221 medical doctors, P_HTHAB).
    Format: split SDMX-CSV. Dataset ends 2020/2021.
    """
    print("\n  hlth_rs_prsrg (physicians per 100k)")
    df = pd.read_csv(raw_path("hlth_rs_prsrg_linear_2_0.csv.gz"), low_memory=False)

    geo_col  = "geo"
    isco_col = "isco08"
    unit_col = "unit"
    val_col  = "OBS_VALUE"
    time_col = "TIME_PERIOD"

    df = df[is_nuts2_eu27(df[geo_col].astype(str))].copy()
    df = df[df[isco_col] == "OC221"].copy()      # Medical doctors
    df = df[df[unit_col] == "P_HTHAB"].copy()    # Per 100k inhabitants
    df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
    df = df[df[val_col].notna()].copy()

    df, yr = filter_best_year(df, geo_col, time_col, val_col)
    out = df[[geo_col, time_col, val_col]].copy()
    out.columns = ["nuts2_code", "year", "physicians_per_100k"]
    return out


# ---------------------------------------------------------------------------
# Region names: extract from combined-format datasets
# ---------------------------------------------------------------------------

def extract_region_names():
    """
    Parse 'AT11: Burgenland' → {AT11: Burgenland} from employment dataset
    (best NUTS-2 coverage), supplemented from transport data.
    """
    print("\n  Extracting NUTS-2 region names")
    names = {}
    for fname in [
        "lfst_r_lfe2emprt_linear_2_0.csv.gz",
        "tran_r_net_linear_2_0.csv.gz",
    ]:
        df = pd.read_csv(raw_path(fname), low_memory=False,
                         usecols=["geo: Geopolitical entity (reporting)"])
        col = "geo: Geopolitical entity (reporting)"
        for val in df[col].dropna().unique():
            parts = str(val).split(": ", 1)
            if len(parts) == 2:
                code, name = parts[0].strip(), parts[1].strip()
                if len(code) == 4 and code[:2] in EU27_COUNTRIES and code not in names:
                    names[code] = name
    print(f"    → {len(names)} region names found")
    return names


# ---------------------------------------------------------------------------
# Urban-rural typology: official Eurostat NUTS 2021 classification
# ---------------------------------------------------------------------------

def load_urban_rural_typology():
    """
    Load the official Eurostat urban-rural typology (NUTS 2021).

    Source: https://ec.europa.eu/eurostat/documents/345175/629341/NUTS2021.xlsx
    Sheet:  "Urban-rural"
    Columns of interest:
      NUTS_ID                    — 5-character NUTS-3 code
      "URBAN-RURAL CATEGORY "    — integer 1/2/3 (note trailing space)
      "URBAN-RURAL LABEL"        — text label

    Returns a DataFrame keyed by nuts3_code with:
      nuts3_code, nuts2_code, country_code, urban_rural_typology
    Filtered to EU-27 only.
    """
    print("\n  NUTS2021_urban_rural.xlsx (official urban-rural typology)")
    df = pd.read_excel(
        raw_path("NUTS2021_urban_rural.xlsx"),
        sheet_name="Urban-rural",
        usecols=["NUTS_ID", "URBAN-RURAL CATEGORY "],
    )
    df.columns = ["nuts3_code", "category"]
    df["nuts3_code"] = df["nuts3_code"].astype(str).str.strip()

    df = df[df["nuts3_code"].str.len() == 5].copy()
    df["country_code"] = df["nuts3_code"].str[:2]
    df["nuts2_code"]   = df["nuts3_code"].str[:4]
    df = df[df["country_code"].isin(EU27_COUNTRIES.keys())].copy()

    df["category"] = pd.to_numeric(df["category"], errors="coerce").astype("Int64")
    df = df[df["category"].isin([1, 2, 3])].copy()
    df["urban_rural_typology"] = df["category"].map(TYPOLOGY_LABELS)

    df = df[["nuts3_code", "nuts2_code", "country_code",
             "urban_rural_typology"]].reset_index(drop=True)

    print(f"    → {len(df)} NUTS-3 regions ({df['nuts2_code'].nunique()} NUTS-2 parents)")
    for label, n in df["urban_rural_typology"].value_counts().items():
        print(f"       {label}: {n}")
    return df


def derive_nuts2_typology(df_typ):
    """
    Roll up NUTS-3 typology to NUTS-2 by majority. Ties are broken in favour
    of the more-urban category (urban > intermediate > rural) on the
    grounds that a NUTS-2 region is most usefully labelled by its anchor
    city / urban core.

    Returns: dict mapping nuts2_code → typology label.
    """
    out = {}
    for code, group in df_typ.groupby("nuts2_code"):
        counts = group["urban_rural_typology"].value_counts()
        top = counts.max()
        winners = sorted(
            counts[counts == top].index,
            key=lambda lbl: TYPOLOGY_TIE_PRIORITY[lbl],
        )
        out[code] = winners[0]
    return out


# ---------------------------------------------------------------------------
# Database insertion
# ---------------------------------------------------------------------------

def insert_countries(cur):
    cur.executemany(
        "INSERT OR IGNORE INTO countries (country_code, country_name) VALUES (?, ?)",
        EU27_COUNTRIES.items()
    )
    print(f"  countries: {len(EU27_COUNTRIES)} rows")


def insert_nuts2_regions(cur, region_names, n2_typology):
    """
    Insert NUTS-2 regions only if they appear in the official typology.
    The typology defines the universe of acceptable NUTS-2 codes; outcome
    rows referencing other codes will be dropped via foreign-key filtering
    in the outcome inserters.
    """
    rows = [
        (code, code[:2], name, n2_typology[code])
        for code, name in region_names.items()
        if code in n2_typology
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO nuts2_regions"
        " (nuts2_code, country_code, region_name, urban_rural_typology)"
        " VALUES (?, ?, ?, ?)",
        rows
    )
    print(f"  nuts2_regions: {len(rows)} rows"
          f" (dropped {len(region_names) - len(rows)} codes not in NUTS 2021 typology)")


def insert_nuts3_regions(cur, df_typology):
    """
    Insert real NUTS-3 entries from the Eurostat typology spreadsheet.
    Only NUTS-3 whose NUTS-2 parent made it into nuts2_regions are kept,
    so the foreign key always resolves.
    Region names are not provided by the typology source — left NULL.
    """
    valid_nuts2 = {
        r[0] for r in cur.execute("SELECT nuts2_code FROM nuts2_regions").fetchall()
    }
    rows = [
        (row["nuts3_code"], row["nuts2_code"], None, row["urban_rural_typology"])
        for _, row in df_typology.iterrows()
        if row["nuts2_code"] in valid_nuts2
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO nuts3_regions"
        " (nuts3_code, nuts2_code, region_name, urban_rural_typology)"
        " VALUES (?, ?, ?, ?)",
        rows
    )
    print(f"  nuts3_regions: {len(rows)} rows")


def _valid_nuts2(cur):
    """Set of NUTS-2 codes that survived the typology filter."""
    return {r[0] for r in cur.execute("SELECT nuts2_code FROM nuts2_regions").fetchall()}


def insert_transport(cur, df_rail_mway, df_motor):
    """
    Build a complete set of transport rows by combining railway/motorway
    density (df_rail_mway) with motorisation rate (df_motor). Rows whose
    NUTS-2 code does not exist in nuts2_regions are skipped to satisfy
    foreign-key constraints.
    """
    valid = _valid_nuts2(cur)

    motor_lookup = dict(zip(
        df_motor["nuts2_code"],
        zip(df_motor["year"], df_motor["motorisation_rate_per_1000"])
    ))

    rows = []
    seen = set()
    skipped = 0

    for _, row in df_rail_mway.iterrows():
        code = str(row["nuts2_code"])
        if code in seen:
            continue
        seen.add(code)
        if code not in valid:
            skipped += 1
            continue
        yr = to_int_or_none(row.get("year"))
        if yr is None:
            continue
        motor_yr, motor_val = motor_lookup.get(code, (None, None))
        rows.append((
            code, yr,
            to_float_or_none(row.get("railway_density_per_1000km2")),
            to_float_or_none(row.get("motorway_density_per_1000km2")),
            to_float_or_none(motor_val),
        ))

    for code, (yr, val) in motor_lookup.items():
        if code in seen:
            continue
        seen.add(code)
        if code not in valid:
            skipped += 1
            continue
        yr_int = to_int_or_none(yr)
        if yr_int is None:
            continue
        rows.append((code, yr_int, None, None, to_float_or_none(val)))

    cur.executemany(
        "INSERT INTO transport_infrastructure"
        " (nuts2_code, year, railway_density_per_1000km2,"
        "  motorway_density_per_1000km2, motorisation_rate_per_1000)"
        " VALUES (?, ?, ?, ?, ?)",
        rows
    )
    print(f"  transport_infrastructure: {len(rows)} rows (skipped {skipped})")


def insert_employment(cur, df_emp, df_unemp):
    valid = _valid_nuts2(cur)

    unemp_lookup = dict(zip(
        df_unemp["nuts2_code"],
        df_unemp["unemployment_rate_pct"]
    ))
    rows = []
    seen = set()
    skipped = 0

    for _, row in df_emp.iterrows():
        code = str(row["nuts2_code"])
        if code in seen:
            continue
        seen.add(code)
        if code not in valid:
            skipped += 1
            continue
        yr = to_int_or_none(row.get("year"))
        if yr is None:
            continue
        rows.append((
            code, yr,
            to_float_or_none(row.get("employment_rate_pct")),
            to_float_or_none(unemp_lookup.get(code)),
        ))

    unemp_year = int(df_unemp["year"].mode()[0]) if len(df_unemp) > 0 else 2024
    for _, row in df_unemp.iterrows():
        code = str(row["nuts2_code"])
        if code in seen:
            continue
        seen.add(code)
        if code not in valid:
            skipped += 1
            continue
        yr = to_int_or_none(row.get("year", unemp_year))
        if yr is None:
            continue
        rows.append((code, yr, None, to_float_or_none(row.get("unemployment_rate_pct"))))

    cur.executemany(
        "INSERT INTO employment_outcomes"
        " (nuts2_code, year, employment_rate_pct, unemployment_rate_pct)"
        " VALUES (?, ?, ?, ?)",
        rows
    )
    print(f"  employment_outcomes: {len(rows)} rows (skipped {skipped})")


def insert_education(cur, df_tert, df_early):
    valid = _valid_nuts2(cur)

    early_lookup = dict(zip(
        df_early["nuts2_code"],
        df_early["early_leavers_pct"]
    ))
    rows = []
    seen = set()
    skipped = 0

    for _, row in df_tert.iterrows():
        code = str(row["nuts2_code"])
        if code in seen:
            continue
        seen.add(code)
        if code not in valid:
            skipped += 1
            continue
        yr = to_int_or_none(row.get("year"))
        if yr is None:
            continue
        rows.append((
            code, yr,
            to_float_or_none(row.get("tertiary_attainment_pct")),
            to_float_or_none(early_lookup.get(code)),
        ))

    early_year = int(df_early["year"].mode()[0]) if len(df_early) > 0 else 2024
    for _, row in df_early.iterrows():
        code = str(row["nuts2_code"])
        if code in seen:
            continue
        seen.add(code)
        if code not in valid:
            skipped += 1
            continue
        yr = to_int_or_none(row.get("year", early_year))
        if yr is None:
            continue
        rows.append((code, yr, None, to_float_or_none(row.get("early_leavers_pct"))))

    cur.executemany(
        "INSERT INTO education_outcomes"
        " (nuts2_code, year, tertiary_attainment_pct, early_leavers_pct)"
        " VALUES (?, ?, ?, ?)",
        rows
    )
    print(f"  education_outcomes: {len(rows)} rows (skipped {skipped})")


def insert_economic(cur, df_gdp):
    valid = _valid_nuts2(cur)
    rows = []
    seen = set()
    skipped = 0

    for _, row in df_gdp.iterrows():
        code = str(row["nuts2_code"])
        if code in seen:
            continue
        seen.add(code)
        if code not in valid:
            skipped += 1
            continue
        yr = to_int_or_none(row.get("year"))
        if yr is None:
            continue
        rows.append((code, yr, to_float_or_none(row.get("gdp_per_capita_pps"))))

    cur.executemany(
        "INSERT INTO economic_outcomes (nuts2_code, year, gdp_per_capita_pps)"
        " VALUES (?, ?, ?)",
        rows
    )
    print(f"  economic_outcomes: {len(rows)} rows (skipped {skipped})")


def insert_health(cur, df_life, df_phys):
    valid = _valid_nuts2(cur)

    phys_lookup = dict(zip(
        df_phys["nuts2_code"],
        df_phys["physicians_per_100k"]
    ))
    rows = []
    seen = set()
    skipped = 0

    for _, row in df_life.iterrows():
        code = str(row["nuts2_code"])
        if code in seen:
            continue
        seen.add(code)
        if code not in valid:
            skipped += 1
            continue
        yr = to_int_or_none(row.get("year"))
        if yr is None:
            continue
        rows.append((
            code, yr,
            to_float_or_none(row.get("life_expectancy_at_birth")),
            to_float_or_none(phys_lookup.get(code)),
        ))

    phys_year = int(df_phys["year"].mode()[0]) if len(df_phys) > 0 else 2020
    for _, row in df_phys.iterrows():
        code = str(row["nuts2_code"])
        if code in seen:
            continue
        seen.add(code)
        if code not in valid:
            skipped += 1
            continue
        yr = to_int_or_none(row.get("year", phys_year))
        if yr is None:
            continue
        rows.append((code, yr, None, to_float_or_none(row.get("physicians_per_100k"))))

    cur.executemany(
        "INSERT INTO health_outcomes"
        " (nuts2_code, year, life_expectancy_at_birth, physicians_per_100k)"
        " VALUES (?, ?, ?, ?)",
        rows
    )
    print(f"  health_outcomes: {len(rows)} rows (skipped {skipped})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("The 15-Minute Divide — Data Loader")
    print("=" * 60)

    # ---- 1. Load and clean all datasets ----
    print("\n=== Loading & cleaning datasets ===")
    df_typ       = load_urban_rural_typology()
    df_rail_mway = load_railway_motorway()
    df_motor     = load_motorisation()
    df_emp       = load_employment_rate()
    df_unemp     = load_unemployment_rate()
    df_tert      = load_tertiary_attainment()
    df_early     = load_early_leavers()
    df_life      = load_life_expectancy()
    df_phys      = load_physicians()
    df_gdp       = load_gdp_per_capita()

    # ---- 2. Build region name lookup ----
    region_names = extract_region_names()

    # Supplement with any code seen in datasets but missing from name lookup
    all_dfs = [df_rail_mway, df_motor, df_emp, df_unemp,
               df_tert, df_early, df_life, df_phys, df_gdp]
    for df in all_dfs:
        for code in df["nuts2_code"].dropna().unique():
            code = str(code)
            if len(code) == 4 and code[:2] in EU27_COUNTRIES:
                if code not in region_names:
                    region_names[code] = code  # fall back to the code as name

    # ---- 3. Roll typology up to NUTS-2 ----
    n2_typology = derive_nuts2_typology(df_typ)
    print(f"\n  Derived NUTS-2 dominant typology for {len(n2_typology)} regions")
    dist = pd.Series(n2_typology).value_counts()
    for k, v in dist.items():
        print(f"    {k}: {v}")

    # ---- 4. Insert into database ----
    print("\n=== Inserting into database ===")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    insert_countries(cur)
    insert_nuts2_regions(cur, region_names, n2_typology)
    insert_nuts3_regions(cur, df_typ)
    insert_transport(cur, df_rail_mway, df_motor)
    insert_employment(cur, df_emp, df_unemp)
    insert_education(cur, df_tert, df_early)
    insert_health(cur, df_life, df_phys)
    insert_economic(cur, df_gdp)

    conn.commit()
    conn.close()

    # ---- 5. Summary ----
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    print("\n" + "=" * 60)
    print("Load complete — final row counts:")
    tables = [
        "countries", "nuts2_regions", "nuts3_regions",
        "transport_infrastructure", "employment_outcomes",
        "education_outcomes", "health_outcomes", "economic_outcomes",
    ]
    for t in tables:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<35} {n:>5}")
    conn.close()
    print("=" * 60)


if __name__ == "__main__":
    main()
