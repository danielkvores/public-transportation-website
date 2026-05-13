"""
app.py — Where the Lines End
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
        WITH rail_by_typology AS (
            SELECT
                n.urban_rural_typology AS typology,
                AVG(t.railway_density_per_1000km2) AS avg_rail_density
            FROM nuts2_regions n
            JOIN transport_infrastructure t ON n.nuts2_code = t.nuts2_code
            WHERE t.railway_density_per_1000km2 IS NOT NULL
            GROUP BY n.urban_rural_typology
        ),
        country_education_gaps AS (
            SELECT
                n.country_code,
                MAX(ed.tertiary_attainment_pct) - MIN(ed.tertiary_attainment_pct)
                    AS tertiary_gap
            FROM nuts2_regions n
            JOIN education_outcomes ed ON n.nuts2_code = ed.nuts2_code
            WHERE ed.tertiary_attainment_pct IS NOT NULL
            GROUP BY n.country_code
            HAVING COUNT(DISTINCT n.nuts2_code) > 1
        )
        SELECT
            (SELECT COUNT(DISTINCT nuts2_code) FROM nuts2_regions) AS n_regions,
            (SELECT COUNT(DISTINCT country_code) FROM countries) AS n_countries,
            ROUND(
                (SELECT avg_rail_density FROM rail_by_typology
                 WHERE typology = 'predominantly urban')
                / NULLIF(
                    (SELECT avg_rail_density FROM rail_by_typology
                     WHERE typology = 'predominantly rural'),
                    0
                ),
                1
            ) AS rail_density_ratio,
            ROUND((SELECT AVG(tertiary_gap) FROM country_education_gaps), 1)
                AS avg_tertiary_gap
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
         "Railway density", "tran_r_net", "2024",
         "https://ec.europa.eu/eurostat/databrowser/view/tran_r_net/default/table?lang=en"),
        ("transport_infrastructure", "motorway_density_per_1000km2",
         "Motorway density", "tran_r_net", "2024",
         "https://ec.europa.eu/eurostat/databrowser/view/tran_r_net/default/table?lang=en"),
        ("transport_infrastructure", "motorisation_rate_per_1000",
         "Motorisation rate", "tran_r_vehst", "2024",
         "https://ec.europa.eu/eurostat/databrowser/view/tran_r_vehst/default/table?lang=en"),
        ("employment_outcomes", "employment_rate_pct",
         "Employment rate", "lfst_r_lfe2emprt", "2024",
         "https://ec.europa.eu/eurostat/databrowser/view/lfst_r_lfe2emprt/default/table?lang=en"),
        ("employment_outcomes", "unemployment_rate_pct",
         "Unemployment rate", "lfst_r_lfu3rt", "2024",
         "https://ec.europa.eu/eurostat/databrowser/view/lfst_r_lfu3rt/default/table?lang=en"),
        ("education_outcomes", "tertiary_attainment_pct",
         "Tertiary attainment", "edat_lfse_04", "2024",
         "https://ec.europa.eu/eurostat/databrowser/view/edat_lfse_04/default/table?lang=en"),
        ("education_outcomes", "early_leavers_pct",
         "Early school leavers", "edat_lfse_16", "2019",
         "https://ec.europa.eu/eurostat/databrowser/view/edat_lfse_16/default/table?lang=en"),
        ("health_outcomes", "life_expectancy_at_birth",
         "Life expectancy", "demo_r_mlifexp", "2024",
         "https://ec.europa.eu/eurostat/databrowser/view/demo_r_mlifexp/default/table?lang=en"),
        ("health_outcomes", "physicians_per_100k",
         "Physicians", "hlth_rs_prsrg", "2016",
         "https://ec.europa.eu/eurostat/databrowser/view/hlth_rs_prsrg/default/table?lang=en"),
        ("economic_outcomes", "gdp_per_capita_pps",
         "GDP per capita", "nama_10r_2gdp", "2024",
         "https://ec.europa.eu/eurostat/databrowser/view/nama_10r_2gdp/default/table?lang=en"),
    ]
    for table, col, label, source, year, source_url in datasets:
        cur.execute(f"""
            SELECT COUNT(*) AS n,
                   ROUND(AVG({col}), 2)  AS avg_val,
                   ROUND(MIN({col}), 2)  AS min_val,
                   ROUND(MAX({col}), 2)  AS max_val
            FROM {table}
            WHERE {col} IS NOT NULL
        """)
        row = dict(cur.fetchone())
        row.update({
            "label": label,
            "source": source,
            "source_url": source_url,
            "year": year,
        })
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


@app.route("/api/typology-income-split")
def api_typology_income_split():
    """
    Average outcomes by urban-rural typology, split by country GDP half.
    Countries are split by their average NUTS-2 GDP per capita. This keeps
    richer country systems from flattening the sharper gaps in lower-GDP
    member states.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        WITH country_income AS (
            SELECT
                n2.country_code,
                AVG(ec.gdp_per_capita_pps) AS avg_country_gdp
            FROM nuts2_regions n2
            JOIN economic_outcomes ec ON n2.nuts2_code = ec.nuts2_code
            WHERE ec.gdp_per_capita_pps IS NOT NULL
            GROUP BY n2.country_code
        ),
        ranked_countries AS (
            SELECT
                country_code,
                avg_country_gdp,
                NTILE(2) OVER (ORDER BY avg_country_gdp) AS income_half
            FROM country_income
        )
        SELECT
            rc.income_half AS income_group_order,
            CASE rc.income_half
                WHEN 1 THEN 'Lower-GDP country half'
                ELSE 'Higher-GDP country half'
            END AS income_group,
            n2.urban_rural_typology                       AS typology,
            COUNT(DISTINCT n2.nuts2_code)                 AS n_regions,
            ROUND(AVG(ec.gdp_per_capita_pps), 0)          AS avg_gdp_per_capita,
            ROUND(AVG(t.railway_density_per_1000km2), 2)  AS avg_railway_density,
            ROUND(AVG(e.employment_rate_pct), 2)          AS avg_employment,
            ROUND(AVG(h.life_expectancy_at_birth), 2)     AS avg_life_expectancy,
            ROUND(AVG(ed.tertiary_attainment_pct), 2)     AS avg_tertiary,
            ROUND(AVG(ed.early_leavers_pct), 2)           AS avg_early_leavers
        FROM nuts2_regions n2
        JOIN ranked_countries rc ON n2.country_code = rc.country_code
        LEFT JOIN economic_outcomes ec ON n2.nuts2_code = ec.nuts2_code
        LEFT JOIN transport_infrastructure t ON n2.nuts2_code = t.nuts2_code
        LEFT JOIN employment_outcomes e ON n2.nuts2_code = e.nuts2_code
        LEFT JOIN health_outcomes h ON n2.nuts2_code = h.nuts2_code
        LEFT JOIN education_outcomes ed ON n2.nuts2_code = ed.nuts2_code
        GROUP BY rc.income_half, n2.urban_rural_typology
        ORDER BY
            rc.income_half,
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


@app.route("/api/rail-density-buckets")
def api_rail_density_buckets():
    """
    NUTS-2 regions grouped into railway-density quartiles.
    Used instead of a cluttered point cloud so the relationship between rail
    density and outcomes can be read as distribution bands.
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        WITH region_metrics AS (
            SELECT
                n2.nuts2_code,
                n2.urban_rural_typology AS typology,
                t.railway_density_per_1000km2 AS railway_density,
                ec.gdp_per_capita_pps,
                e.employment_rate_pct,
                h.life_expectancy_at_birth,
                ed.tertiary_attainment_pct
            FROM nuts2_regions n2
            JOIN transport_infrastructure t ON n2.nuts2_code = t.nuts2_code
            LEFT JOIN economic_outcomes ec ON n2.nuts2_code = ec.nuts2_code
            LEFT JOIN employment_outcomes e ON n2.nuts2_code = e.nuts2_code
            LEFT JOIN health_outcomes h ON n2.nuts2_code = h.nuts2_code
            LEFT JOIN education_outcomes ed ON n2.nuts2_code = ed.nuts2_code
            WHERE t.railway_density_per_1000km2 IS NOT NULL
        ),
        bucketed AS (
            SELECT
                *,
                NTILE(4) OVER (ORDER BY railway_density) AS rail_bucket
            FROM region_metrics
        )
        SELECT
            rail_bucket,
            COUNT(*) AS n_regions,
            ROUND(MIN(railway_density), 2) AS min_railway_density,
            ROUND(MAX(railway_density), 2) AS max_railway_density,
            ROUND(AVG(railway_density), 2) AS avg_railway_density,
            ROUND(AVG(gdp_per_capita_pps), 0) AS avg_gdp_per_capita,
            ROUND(AVG(employment_rate_pct), 2) AS avg_employment,
            ROUND(AVG(life_expectancy_at_birth), 2) AS avg_life_expectancy,
            ROUND(AVG(tertiary_attainment_pct), 2) AS avg_tertiary,
            SUM(CASE WHEN typology = 'predominantly urban' THEN 1 ELSE 0 END) AS urban_regions,
            SUM(CASE WHEN typology = 'intermediate' THEN 1 ELSE 0 END) AS intermediate_regions,
            SUM(CASE WHEN typology = 'predominantly rural' THEN 1 ELSE 0 END) AS rural_regions
        FROM bucketed
        GROUP BY rail_bucket
        ORDER BY rail_bucket
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
            ROUND(AVG(ec.gdp_per_capita_pps), 0)       AS eu_avg_gdp_per_capita,
            ROUND(AVG(t.railway_density_per_1000km2), 2)
                AS eu_avg_railway_density
        FROM nuts2_regions n2
        LEFT JOIN employment_outcomes e  ON n2.nuts2_code = e.nuts2_code
        LEFT JOIN health_outcomes     h  ON n2.nuts2_code = h.nuts2_code
        LEFT JOIN education_outcomes  ed ON n2.nuts2_code = ed.nuts2_code
        LEFT JOIN economic_outcomes   ec ON n2.nuts2_code = ec.nuts2_code
        LEFT JOIN transport_infrastructure t ON n2.nuts2_code = t.nuts2_code
    """)
    eu_avgs = dict(cur.fetchone())
    conn.close()

    return jsonify({"regions": regions, "eu_averages": eu_avgs})


@app.route("/api/country-gap-rankings")
def api_country_gap_rankings():
    """
    Country-level regional gaps for each metric.
    Each metric contains the lowest and highest NUTS-2 region in that country,
    so the chart can draw a min-to-max dumbbell instead of a long ranking list.
    """
    metric_fields = {
        "gdp_per_capita_pps": "GDP per capita (PPS)",
        "employment_rate_pct": "Employment rate, age 20-64 (%)",
        "life_expectancy_at_birth": "Life expectancy at birth (years)",
        "tertiary_attainment_pct": "Tertiary attainment, age 25-34 (%)",
        "railway_density_per_1000km2": "Railway density (km per 1,000 km²)",
    }

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            n2.country_code,
            c.country_name,
            n2.nuts2_code,
            n2.region_name,
            n2.urban_rural_typology AS typology,
            ec.gdp_per_capita_pps,
            e.employment_rate_pct,
            h.life_expectancy_at_birth,
            ed.tertiary_attainment_pct,
            t.railway_density_per_1000km2
        FROM nuts2_regions n2
        JOIN countries c ON n2.country_code = c.country_code
        LEFT JOIN economic_outcomes ec ON n2.nuts2_code = ec.nuts2_code
        LEFT JOIN employment_outcomes e ON n2.nuts2_code = e.nuts2_code
        LEFT JOIN health_outcomes h ON n2.nuts2_code = h.nuts2_code
        LEFT JOIN education_outcomes ed ON n2.nuts2_code = ed.nuts2_code
        LEFT JOIN transport_infrastructure t ON n2.nuts2_code = t.nuts2_code
        ORDER BY c.country_name, n2.region_name
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    countries = {}
    for row in rows:
        code = row["country_code"]
        country = countries.setdefault(code, {
            "country_code": code,
            "country_name": row["country_name"],
            "n_regions": 0,
            "metrics": {},
        })
        country["n_regions"] += 1

    for country in countries.values():
        country_rows = [r for r in rows if r["country_code"] == country["country_code"]]
        for field, label in metric_fields.items():
            valid = [r for r in country_rows if r[field] is not None]
            if len(valid) < 2:
                country["metrics"][field] = None
                continue

            min_row = min(valid, key=lambda r: r[field])
            max_row = max(valid, key=lambda r: r[field])
            country["metrics"][field] = {
                "label": label,
                "count": len(valid),
                "min": min_row[field],
                "max": max_row[field],
                "gap": max_row[field] - min_row[field],
                "min_region": min_row["region_name"],
                "max_region": max_row["region_name"],
                "min_code": min_row["nuts2_code"],
                "max_code": max_row["nuts2_code"],
            }

    return jsonify(list(countries.values()))


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
