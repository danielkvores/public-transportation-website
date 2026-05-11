/**
 * charts.js — The 15-Minute Divide
 * Chart.js 4.x visualisations for the /data page.
 * Data is fetched live from Flask API endpoints (/api/*).
 */

"use strict";

/* ── Colour palette ──────────────────────────────────────────────── */
const COLOURS = {
    "predominantly urban": {
        bg:     "rgba(26,  108, 186, 0.80)",
        border: "rgba(26,  108, 186, 1.00)",
        light:  "rgba(26,  108, 186, 0.20)",
    },
    "intermediate": {
        bg:     "rgba(26,  155, 138, 0.80)",
        border: "rgba(26,  155, 138, 1.00)",
        light:  "rgba(26,  155, 138, 0.20)",
    },
    "predominantly rural": {
        bg:     "rgba(212, 134,  10, 0.80)",
        border: "rgba(212, 134,  10, 1.00)",
        light:  "rgba(212, 134,  10, 0.20)",
    },
    default: {
        bg:     "rgba(107, 114, 128, 0.70)",
        border: "rgba(107, 114, 128, 1.00)",
        light:  "rgba(107, 114, 128, 0.20)",
    },
};

function colourFor(typology, key = "bg") {
    const c = COLOURS[typology] || COLOURS.default;
    return c[key];
}

/* Chart.js global defaults — aligned with the editorial palette */
Chart.defaults.font.family = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace";
Chart.defaults.font.size   = 11;
Chart.defaults.color       = "#6b6454"; /* --ink-muted */

const GRID_COLOR = "rgba(20, 17, 10, 0.08)";
const AXIS_TITLE = "#6b6454"; /* --ink-muted */
const TICK_COLOR = "#3a342a"; /* --ink-soft */

/* Shared tooltip style */
const TOOLTIP = {
    backgroundColor: "rgba(20, 17, 10, 0.96)",
    titleColor: "#ece5d2",
    bodyColor:  "#ddd5be",
    padding: 12,
    cornerRadius: 0,
    displayColors: true,
    titleFont: { family: "'JetBrains Mono', monospace", size: 11, weight: "600" },
    bodyFont:  { family: "'Newsreader', Georgia, serif", size: 12 },
    borderColor: "#c8371a",
    borderWidth: 1,
};


/* ══════════════════════════════════════════════════════════════════
   CHART 1 — Typology outcomes (grouped bar, tabbed)
   ══════════════════════════════════════════════════════════════════ */

let typologyData   = null;
let typologyChart  = null;
let activeMetric   = "employment";

const METRIC_CONFIG = {
    gdp_per_capita: { field: "avg_gdp_per_capita", label: "GDP per capita (PPS, EU27 2020 baseline)", fmt: v => v?.toLocaleString("en", { maximumFractionDigits: 0 }) + " PPS" },
    employment:     { field: "avg_employment",     label: "Employment rate (%)",        fmt: v => v?.toFixed(1) + "%" },
    life_expectancy:{ field: "avg_life_expectancy", label: "Life expectancy at birth (years)", fmt: v => v?.toFixed(1) + " yrs" },
    tertiary:       { field: "avg_tertiary",        label: "Tertiary attainment (%, age 25–34)", fmt: v => v?.toFixed(1) + "%" },
    early_leavers:  { field: "avg_early_leavers",   label: "Early school leavers (%, age 18–24)", fmt: v => v?.toFixed(1) + "%" },
};

async function initTypologyChart() {
    const res  = await fetch("/api/typology-outcomes");
    typologyData = await res.json();
    renderTypologyChart(activeMetric);

    // Tab handlers
    document.querySelectorAll(".chart-tab").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".chart-tab").forEach(b => b.classList.remove("chart-tab--active"));
            btn.classList.add("chart-tab--active");
            activeMetric = btn.dataset.metric;
            renderTypologyChart(activeMetric);
        });
    });
}

function renderTypologyChart(metric) {
    const cfg = METRIC_CONFIG[metric];
    if (!cfg || !typologyData) return;

    const labels  = typologyData.map(d => d.typology);
    const values  = typologyData.map(d => d[cfg.field]);
    const bgColours = labels.map(l => colourFor(l, "bg"));
    const bdColours = labels.map(l => colourFor(l, "border"));

    const ctx = document.getElementById("chart-typology").getContext("2d");

    if (typologyChart) typologyChart.destroy();

    typologyChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: cfg.label,
                data: values,
                backgroundColor: bgColours,
                borderColor:     bdColours,
                borderWidth: 2,
                borderRadius: 6,
                borderSkipped: false,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...TOOLTIP,
                    callbacks: {
                        label: ctx => ` ${cfg.label}: ${cfg.fmt(ctx.parsed.y)}`,
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: false,
                    grid: { color: GRID_COLOR },
                    ticks: { callback: v => cfg.fmt(v) },
                    title: {
                        display: true,
                        text: cfg.label,
                        color: AXIS_TITLE,
                        font: { size: 11 },
                    },
                },
                x: {
                    grid: { display: false },
                    ticks: {
                        font: { weight: "600", size: 12, family: "'Newsreader', Georgia, serif" },
                        color: TICK_COLOR,
                    },
                },
            },
        },
    });
}


/* ══════════════════════════════════════════════════════════════════
   CHART 2 — Scatter: railway density vs employment rate
   ══════════════════════════════════════════════════════════════════ */

async function initScatterChart() {
    const res  = await fetch("/api/transport-employment");
    const data = await res.json();

    // Group by typology for separate datasets (so legend + colours work)
    const typologies = ["predominantly urban", "intermediate", "predominantly rural"];
    const datasets = typologies.map(typ => {
        const pts = data
            .filter(d => d.typology === typ)
            .map(d => ({
                x: d.railway_density_per_1000km2,
                y: d.employment_rate_pct,
                label: `${d.region_name} (${d.nuts2_code})`,
                country: d.country_name,
            }));
        return {
            label: typ,
            data: pts,
            backgroundColor: colourFor(typ, "bg"),
            borderColor:     colourFor(typ, "border"),
            borderWidth: 1,
            pointRadius: 5,
            pointHoverRadius: 8,
        };
    });

    // Add a simple linear trend line across all points
    const allX = data.map(d => d.railway_density_per_1000km2).filter(v => v != null);
    const allY = data.map(d => d.employment_rate_pct).filter(v => v != null);
    const trend = linearRegression(
        data.filter(d => d.railway_density_per_1000km2 != null && d.employment_rate_pct != null)
            .map(d => ({ x: d.railway_density_per_1000km2, y: d.employment_rate_pct }))
    );

    if (trend) {
        const xMin = Math.min(...allX);
        const xMax = Math.max(...allX);
        datasets.push({
            label: "Trend line",
            data: [
                { x: xMin, y: trend.slope * xMin + trend.intercept },
                { x: xMax, y: trend.slope * xMax + trend.intercept },
            ],
            type: "line",
            borderColor: "rgba(200, 55, 26, 0.75)", /* --signal */
            borderWidth: 2,
            borderDash: [6, 4],
            pointRadius: 0,
            fill: false,
        });
    }

    const ctx = document.getElementById("chart-scatter").getContext("2d");
    new Chart(ctx, {
        type: "scatter",
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "top",
                    labels: { font: { size: 11 }, padding: 16 },
                },
                tooltip: {
                    ...TOOLTIP,
                    callbacks: {
                        title: items => items[0]?.raw?.label || "",
                        label: item => [
                            `Country: ${item.raw.country || ""}`,
                            `Railway density: ${item.parsed.x?.toFixed(1)} km/1000km²`,
                            `Employment rate: ${item.parsed.y?.toFixed(1)}%`,
                        ],
                    },
                },
            },
            scales: {
                x: {
                    title: {
                        display: true,
                        text: "Railway density (km per 1,000 km²)",
                        color: AXIS_TITLE, font: { size: 11 },
                    },
                    grid: { color: GRID_COLOR },
                },
                y: {
                    title: {
                        display: true,
                        text: "Employment rate, age 20–64 (%)",
                        color: AXIS_TITLE, font: { size: 11 },
                    },
                    grid: { color: GRID_COLOR },
                },
            },
        },
    });
}

/** Simple ordinary-least-squares linear regression on {x, y} points. */
function linearRegression(pts) {
    const n = pts.length;
    if (n < 2) return null;
    const meanX = pts.reduce((s, p) => s + p.x, 0) / n;
    const meanY = pts.reduce((s, p) => s + p.y, 0) / n;
    let num = 0, den = 0;
    for (const p of pts) {
        num += (p.x - meanX) * (p.y - meanY);
        den += (p.x - meanX) ** 2;
    }
    if (den === 0) return null;
    const slope     = num / den;
    const intercept = meanY - slope * meanX;
    return { slope, intercept };
}


/* ══════════════════════════════════════════════════════════════════
   CHART 3 — Country comparison (dynamic, dropdown-driven)
   ══════════════════════════════════════════════════════════════════ */

let countryChart   = null;
let countryData    = null;
let activeField    = "gdp_per_capita_pps";

const FIELD_LABELS = {
    "gdp_per_capita_pps":        "GDP per capita (PPS)",
    "employment_rate_pct":       "Employment rate, age 20–64 (%)",
    "life_expectancy_at_birth":  "Life expectancy at birth (years)",
    "tertiary_attainment_pct":   "Tertiary attainment, age 25–34 (%)",
};
const EU_AVG_FIELDS = {
    "gdp_per_capita_pps":       "eu_avg_gdp_per_capita",
    "employment_rate_pct":      "eu_avg_employment",
    "life_expectancy_at_birth": "eu_avg_life_expectancy",
    "tertiary_attainment_pct":  "eu_avg_tertiary",
};

async function loadCountryData(countryCode) {
    const res   = await fetch(`/api/country/${countryCode}`);
    countryData = await res.json();
    renderCountryChart(activeField);

    document.getElementById("country-chart-wrap").style.display = "block";
    document.getElementById("country-placeholder").style.display = "none";
}

function renderCountryChart(field) {
    if (!countryData) return;

    const regions = countryData.regions.filter(r => r[field] != null);
    regions.sort((a, b) => (b[field] || 0) - (a[field] || 0));

    const labels  = regions.map(r => r.region_name || r.nuts2_code);
    const values  = regions.map(r => r[field]);
    const bgCols  = regions.map(r => colourFor(r.typology || "default", "bg"));
    const bdCols  = regions.map(r => colourFor(r.typology || "default", "border"));

    const euAvg   = countryData.eu_averages?.[EU_AVG_FIELDS[field]];
    const axisLbl = FIELD_LABELS[field] || field;

    // Inline plugin: draw a dashed vertical reference line at EU average
    const euAvgLinePlugin = euAvg ? {
        id: "euAvgLine",
        afterDraw(chart) {
            const { ctx: c, scales: { x } } = chart;
            if (!x) return;
            const xPos = x.getPixelForValue(euAvg);
            const top    = chart.chartArea.top;
            const bottom = chart.chartArea.bottom;
            c.save();
            c.beginPath();
            c.setLineDash([6, 4]);
            c.strokeStyle = "rgba(200, 55, 26, 0.85)"; /* --signal */
            c.lineWidth = 2;
            c.moveTo(xPos, top);
            c.lineTo(xPos, bottom);
            c.stroke();
            c.fillStyle = "#c8371a"; /* --signal */
            c.font = "600 10px 'JetBrains Mono', monospace";
            c.fillText(`EU avg: ${euAvg?.toFixed(1)}`, xPos + 4, top + 14);
            c.restore();
        },
    } : null;

    const canvas = document.getElementById("chart-country");
    const ctx = canvas.getContext("2d");
    if (countryChart) countryChart.destroy();

    countryChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [
                {
                    label: axisLbl,
                    data: values,
                    backgroundColor: bgCols,
                    borderColor:     bdCols,
                    borderWidth: 2,
                    borderRadius: 5,
                    borderSkipped: false,
                },
            ],
        },
        plugins: euAvgLinePlugin ? [euAvgLinePlugin] : [],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: "y",   // horizontal bars for readability
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...TOOLTIP,
                    callbacks: {
                        label: ctx => ` ${axisLbl}: ${ctx.parsed.x?.toFixed(1)}`,
                    },
                },
                // EU average reference line drawn via afterDraw plugin below
            },
            scales: {
                x: {
                    beginAtZero: false,
                    grid: { color: GRID_COLOR },
                    title: { display: true, text: axisLbl, color: AXIS_TITLE, font: { size: 11 } },
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { size: 11 } },
                },
            },
        },
    });
}

function initCountryControls() {
    const sel = document.getElementById("country-select");
    sel.addEventListener("change", () => {
        if (sel.value) loadCountryData(sel.value);
    });

    document.querySelectorAll(".metric-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".metric-btn").forEach(b => b.classList.remove("metric-btn--active"));
            btn.classList.add("metric-btn--active");
            activeField = btn.dataset.field;
            renderCountryChart(activeField);
        });
    });
}


/* ══════════════════════════════════════════════════════════════════
   CHART 4 — Regional rankings (horizontal bar, top 60 by employment)
   ══════════════════════════════════════════════════════════════════ */

async function initRankingsChart() {
    const res  = await fetch("/api/regional-rankings");
    const data = await res.json();

    const labels    = data.map(d => `${d.region_name} (${d.country_name})`);
    const values    = data.map(d => d.employment_rate_pct);
    const bgColours = data.map(d => colourFor(d.typology, "bg"));
    const bdColours = data.map(d => colourFor(d.typology, "border"));

    // Compute overall average for reference line
    const avg = values.reduce((s, v) => s + (v || 0), 0) / values.filter(v => v).length;

    const ctx = document.getElementById("chart-rankings").getContext("2d");
    new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: "Employment rate, age 20–64 (%)",
                data: values,
                backgroundColor: bgColours,
                borderColor:     bdColours,
                borderWidth: 1.5,
                borderRadius: 4,
                borderSkipped: false,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: "y",
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...TOOLTIP,
                    callbacks: {
                        label: ctx => ` Employment rate: ${ctx.parsed.x?.toFixed(1)}%`,
                        afterLabel: ctx => {
                            const d = data[ctx.dataIndex];
                            return [
                                `Type: ${d.typology || "unknown"}`,
                                `Railway density: ${d.railway_density_per_1000km2?.toFixed(1) ?? "n/a"} km/1000km²`,
                            ];
                        },
                    },
                },
            },
            scales: {
                x: {
                    min: 50,
                    grid: { color: GRID_COLOR },
                    title: {
                        display: true,
                        text: "Employment rate, age 20–64 (%)",
                        color: AXIS_TITLE, font: { size: 11 },
                    },
                },
                y: {
                    grid: { display: false },
                    ticks: { font: { size: 9.5 } },
                },
            },
        },
    });
}


/* ── Bootstrap all charts on DOMContentLoaded ─────────────────── */
document.addEventListener("DOMContentLoaded", () => {
    // Chart 1: typology bar chart
    initTypologyChart().catch(err => console.error("Typology chart:", err));

    // Chart 2: scatter
    initScatterChart().catch(err => console.error("Scatter chart:", err));

    // Chart 3: country comparison
    initCountryControls();

    // Chart 4: regional rankings
    initRankingsChart().catch(err => console.error("Rankings chart:", err));
});
