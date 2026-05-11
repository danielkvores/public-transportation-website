"""
app.py — The 15-Minute Divide
Flask web application. All data is served from SQLite via raw sqlite3.
"""

import sqlite3
import os
from flask import Flask, render_template, jsonify, request

from tracking import (
    bp as tracking_bp,
    before_request_hook as tracking_before_request,
    context_processor as tracking_context_processor,
    init_tracking_schema,
)

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "database", "the_15_minute_divide.db")
app.config["DB_PATH"] = DB_PATH

# Signed-cookie secret for the visitor session_id used by tracking.py.
# Override via env var in any non-local deployment.
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY", "dev-secret-the-15-minute-divide-change-me"
)

init_tracking_schema(DB_PATH)
app.register_blueprint(tracking_bp)
app.before_request(tracking_before_request)
app.context_processor(tracking_context_processor)


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # rows behave like dicts
    return conn


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    conn = get_db()
    cur = conn.cursor()

    # Quick headline stats for the hero section
    cur.execute("""
        SELECT
            COUNT(DISTINCT n.nuts2_code)                         AS n_regions,
            ROUND(AVG(e.employment_rate_pct), 1)                 AS avg_emp,
            ROUND(MAX(e.employment_rate_pct) - MIN(e.employment_rate_pct), 1) AS emp_range,
            ROUND(MAX(h.life_expectancy_at_birth)
                - MIN(h.life_expectancy_at_birth), 1)            AS le_range
        FROM nuts2_regions n
        LEFT JOIN employment_outcomes e ON n.nuts2_code = e.nuts2_code
        LEFT JOIN health_outcomes     h ON n.nuts2_code = h.nuts2_code
    """)
    stats = dict(cur.fetchone())
    conn.close()
    return render_template("index.html", stats=stats)


@app.route("/data")
def data():
    conn = get_db()
    cur = conn.cursor()

    # Country list for the dropdown
    cur.execute("SELECT country_code, country_name FROM countries ORDER BY country_name")
    countries = [dict(r) for r in cur.fetchall()]
    conn.close()
    return render_template("data.html", countries=countries)


@app.route("/methodology")
def methodology():
    conn = get_db()
    cur = conn.cursor()

    # Dataset summary for methodology table
    summaries = []
    datasets = [
        ("transport_infrastructure", "railway_density_per_1000km2",
         "Transport Infrastructure", "tran_r_net / tran_r_vehst", "2024"),
        ("employment_outcomes", "employment_rate_pct",
         "Employment Outcomes", "lfst_r_lfe2emprt / lfst_r_lfu3rt", "2024"),
        ("education_outcomes", "tertiary_attainment_pct",
         "Education Outcomes", "edat_lfse_04 / edat_lfse_16", "2024 / 2019"),
        ("health_outcomes", "life_expectancy_at_birth",
         "Health Outcomes", "demo_r_mlifexp / hlth_rs_prsrg", "2024 / 2016"),
        ("economic_outcomes", "gdp_per_capita_pps",
         "Economic Outcomes", "nama_10r_2gdp", "2024"),
    ]
    for table, col, label, source, year in datasets:
        cur.execute(f"""
            SELECT COUNT(*) AS n,
                   ROUND(AVG({col}), 2)  AS avg_val,
                   ROUND(MIN({col}), 2)  AS min_val,
                   ROUND(MAX({col}), 2)  AS max_val
            FROM {table}
            WHERE {col} IS NOT NULL
        """)
        row = dict(cur.fetchone())
        row.update({"label": label, "source": source, "year": year})
        summaries.append(row)

    conn.close()
    return render_template("methodology.html", summaries=summaries)


@app.route("/about")
def about():
    return render_template("about.html")


# ---------------------------------------------------------------------------
# API routes — return JSON for Chart.js
# ---------------------------------------------------------------------------

@app.route("/api/typology-outcomes")
def api_typology_outcomes():
    """
    Average key outcomes grouped by urban-rural typology.
    Typology is read from nuts2_regions (the dominant-NUTS-3 rollup) so
    each NUTS-2 region contributes once per group.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            n2.urban_rural_typology                       AS typology,
            ROUND(AVG(e.employment_rate_pct),   2)        AS avg_employment,
            ROUND(AVG(e.unemployment_rate_pct), 2)        AS avg_unemployment,
            ROUND(AVG(h.life_expectancy_at_birth), 2)     AS avg_life_expectancy,
            ROUND(AVG(ed.tertiary_attainment_pct), 2)     AS avg_tertiary,
            ROUND(AVG(ed.early_leavers_pct), 2)           AS avg_early_leavers,
            ROUND(AVG(ec.gdp_per_capita_pps), 0)          AS avg_gdp_per_capita,
            COUNT(DISTINCT n2.nuts2_code)                 AS n_regions
        FROM nuts2_regions n2
        LEFT JOIN employment_outcomes  e  ON n2.nuts2_code = e.nuts2_code
        LEFT JOIN health_outcomes      h  ON n2.nuts2_code = h.nuts2_code
        LEFT JOIN education_outcomes   ed ON n2.nuts2_code = ed.nuts2_code
        LEFT JOIN economic_outcomes    ec ON n2.nuts2_code = ec.nuts2_code
        GROUP BY n2.urban_rural_typology
        ORDER BY
            CASE n2.urban_rural_typology
                WHEN 'predominantly urban' THEN 1
                WHEN 'intermediate'        THEN 2
                WHEN 'predominantly rural' THEN 3
            END
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/transport-employment")
def api_transport_employment():
    """
    Scatter plot data: railway density vs employment rate.
    Each point is a NUTS-2 region, coloured by typology.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            n2.nuts2_code,
            n2.region_name,
            c.country_name,
            n2.urban_rural_typology                    AS typology,
            t.railway_density_per_1000km2,
            e.employment_rate_pct,
            h.life_expectancy_at_birth
        FROM nuts2_regions n2
        JOIN countries c        ON n2.country_code = c.country_code
        LEFT JOIN transport_infrastructure t ON n2.nuts2_code = t.nuts2_code
        LEFT JOIN employment_outcomes      e ON n2.nuts2_code = e.nuts2_code
        LEFT JOIN health_outcomes          h ON n2.nuts2_code = h.nuts2_code
        WHERE t.railway_density_per_1000km2 IS NOT NULL
          AND e.employment_rate_pct          IS NOT NULL
        ORDER BY n2.nuts2_code
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/country/<country_code>")
def api_country(country_code):
    """
    All NUTS-2 regions for a given country with their key outcomes.
    Used for the country-comparison chart.
    """
    # Whitelist: only accept known EU-27 country codes
    VALID_CODES = {
        "AT","BE","BG","CY","CZ","DE","DK","EE","EL","ES",
        "FI","FR","HR","HU","IE","IT","LT","LU","LV","MT",
        "NL","PL","PT","RO","SE","SI","SK"
    }
    if country_code.upper() not in VALID_CODES:
        return jsonify({"error": "Invalid country code"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            n2.nuts2_code,
            n2.region_name,
            n2.urban_rural_typology                AS typology,
            e.employment_rate_pct,
            e.unemployment_rate_pct,
            h.life_expectancy_at_birth,
            ed.tertiary_attainment_pct,
            ed.early_leavers_pct,
            ec.gdp_per_capita_pps,
            t.railway_density_per_1000km2,
            t.motorway_density_per_1000km2,
            t.motorisation_rate_per_1000
        FROM nuts2_regions n2
        LEFT JOIN employment_outcomes        e ON n2.nuts2_code = e.nuts2_code
        LEFT JOIN health_outcomes            h ON n2.nuts2_code = h.nuts2_code
        LEFT JOIN education_outcomes        ed ON n2.nuts2_code = ed.nuts2_code
        LEFT JOIN economic_outcomes         ec ON n2.nuts2_code = ec.nuts2_code
        LEFT JOIN transport_infrastructure   t ON n2.nuts2_code = t.nuts2_code
        WHERE n2.country_code = ?
        ORDER BY n2.region_name
    """, (country_code.upper(),))
    regions = [dict(r) for r in cur.fetchall()]

    # Compute EU-wide averages for comparison lines
    cur.execute("""
        SELECT
            ROUND(AVG(e.employment_rate_pct), 2)       AS eu_avg_employment,
            ROUND(AVG(h.life_expectancy_at_birth), 2)  AS eu_avg_life_expectancy,
            ROUND(AVG(ed.tertiary_attainment_pct), 2)  AS eu_avg_tertiary,
            ROUND(AVG(ec.gdp_per_capita_pps), 0)       AS eu_avg_gdp_per_capita
        FROM nuts2_regions n2
        LEFT JOIN employment_outcomes e  ON n2.nuts2_code = e.nuts2_code
        LEFT JOIN health_outcomes     h  ON n2.nuts2_code = h.nuts2_code
        LEFT JOIN education_outcomes  ed ON n2.nuts2_code = ed.nuts2_code
        LEFT JOIN economic_outcomes   ec ON n2.nuts2_code = ec.nuts2_code
    """)
    eu_avgs = dict(cur.fetchone())
    conn.close()

    return jsonify({"regions": regions, "eu_averages": eu_avgs})


@app.route("/api/regional-rankings")
def api_regional_rankings():
    """
    All regions ranked by employment rate, with typology colour-coding.
    Used for the ranked bar chart.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            n2.nuts2_code,
            n2.region_name,
            c.country_name,
            n2.urban_rural_typology   AS typology,
            e.employment_rate_pct,
            h.life_expectancy_at_birth,
            t.railway_density_per_1000km2
        FROM nuts2_regions n2
        JOIN countries c        ON n2.country_code = c.country_code
        LEFT JOIN employment_outcomes e  ON n2.nuts2_code = e.nuts2_code
        LEFT JOIN health_outcomes     h  ON n2.nuts2_code = h.nuts2_code
        LEFT JOIN transport_infrastructure t ON n2.nuts2_code = t.nuts2_code
        WHERE e.employment_rate_pct IS NOT NULL
        ORDER BY e.employment_rate_pct DESC
        LIMIT 60
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route("/api/transport-health")
def api_transport_health():
    """
    Motorisation rate vs life expectancy — shows the car-dependency trap.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            n2.nuts2_code,
            n2.region_name,
            c.country_name,
            n2.urban_rural_typology              AS typology,
            t.motorisation_rate_per_1000,
            h.life_expectancy_at_birth,
            e.employment_rate_pct
        FROM nuts2_regions n2
        JOIN countries c        ON n2.country_code = c.country_code
        LEFT JOIN transport_infrastructure  t  ON n2.nuts2_code = t.nuts2_code
        LEFT JOIN health_outcomes           h  ON n2.nuts2_code = h.nuts2_code
        LEFT JOIN employment_outcomes       e  ON n2.nuts2_code = e.nuts2_code
        WHERE t.motorisation_rate_per_1000  IS NOT NULL
          AND h.life_expectancy_at_birth    IS NOT NULL
        ORDER BY n2.nuts2_code
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


if __name__ == "__main__":
    app.run(debug=True)
