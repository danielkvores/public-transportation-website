/**
 * charts.js - Where the Lines End
 * Chart.js 4.x visualisations for the /data page.
 * Data is fetched live from Flask API endpoints (/api/*).
 */

"use strict";

/* -- Colour palette ------------------------------------------------------ */
const COLOURS = {
    "predominantly urban": {
        bg:     "rgba(26, 108, 186, 0.80)",
        border: "rgba(26, 108, 186, 1.00)",
        light:  "rgba(26, 108, 186, 0.18)",
    },
    "intermediate": {
        bg:     "rgba(26, 155, 138, 0.80)",
        border: "rgba(26, 155, 138, 1.00)",
        light:  "rgba(26, 155, 138, 0.18)",
    },
    "predominantly rural": {
        bg:     "rgba(212, 134, 10, 0.80)",
        border: "rgba(212, 134, 10, 1.00)",
        light:  "rgba(212, 134, 10, 0.18)",
    },
    default: {
        bg:     "rgba(107, 114, 128, 0.70)",
        border: "rgba(107, 114, 128, 1.00)",
        light:  "rgba(107, 114, 128, 0.18)",
    },
};

const TYPOLOGIES = [
    "predominantly urban",
    "intermediate",
    "predominantly rural",
];

function colourFor(typology, key = "bg") {
    const c = COLOURS[typology] || COLOURS.default;
    return c[key];
}

Chart.defaults.font.family = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace";
Chart.defaults.font.size = 11;
Chart.defaults.color = "#6b6454";

const GRID_COLOR = "rgba(20, 17, 10, 0.08)";
const AXIS_TITLE = "#6b6454";
const TICK_COLOR = "#3a342a";
const SIGNAL = "#c8371a";
const INK = "#14110a";
const PAPER = "#ece5d2";

const TOOLTIP = {
    backgroundColor: "rgba(20, 17, 10, 0.96)",
    titleColor: "#ece5d2",
    bodyColor: "#ddd5be",
    padding: 12,
    cornerRadius: 0,
    displayColors: true,
    titleFont: { family: "'JetBrains Mono', monospace", size: 11, weight: "600" },
    bodyFont: { family: "'Newsreader', Georgia, serif", size: 12 },
    borderColor: SIGNAL,
    borderWidth: 1,
};

const METRICS = {
    gdp_per_capita: {
        avgField: "avg_gdp_per_capita",
        countryField: "gdp_per_capita_pps",
        euAvgField: "eu_avg_gdp_per_capita",
        label: "GDP per capita (PPS)",
        fmt: v => formatNumber(v, 0) + " PPS",
        tick: v => formatCompact(v),
    },
    railway_density: {
        avgField: "avg_railway_density",
        countryField: "railway_density_per_1000km2",
        euAvgField: "eu_avg_railway_density",
        label: "Railway density (km per 1,000 km²)",
        fmt: v => formatNumber(v, 1) + " km",
        tick: v => formatNumber(v, 0),
    },
    employment: {
        avgField: "avg_employment",
        countryField: "employment_rate_pct",
        euAvgField: "eu_avg_employment",
        label: "Employment rate, age 20-64 (%)",
        fmt: v => formatNumber(v, 1) + "%",
        tick: v => formatNumber(v, 0) + "%",
    },
    life_expectancy: {
        avgField: "avg_life_expectancy",
        countryField: "life_expectancy_at_birth",
        euAvgField: "eu_avg_life_expectancy",
        label: "Life expectancy at birth (years)",
        fmt: v => formatNumber(v, 1) + " yrs",
        tick: v => formatNumber(v, 0),
    },
    tertiary: {
        avgField: "avg_tertiary",
        countryField: "tertiary_attainment_pct",
        euAvgField: "eu_avg_tertiary",
        label: "Tertiary attainment, age 25-34 (%)",
        fmt: v => formatNumber(v, 1) + "%",
        tick: v => formatNumber(v, 0) + "%",
    },
    early_leavers: {
        avgField: "avg_early_leavers",
        countryField: "early_leavers_pct",
        euAvgField: null,
        label: "Early school leavers, age 18-24 (%)",
        fmt: v => formatNumber(v, 1) + "%",
        tick: v => formatNumber(v, 0) + "%",
    },
};

const COUNTRY_METRICS = {
    gdp_per_capita_pps: METRICS.gdp_per_capita,
    railway_density_per_1000km2: METRICS.railway_density,
    tertiary_attainment_pct: METRICS.tertiary,
    employment_rate_pct: METRICS.employment,
    life_expectancy_at_birth: METRICS.life_expectancy,
};

const GAP_METRICS = COUNTRY_METRICS;

function formatNumber(value, fractionDigits = 1) {
    if (value == null || Number.isNaN(Number(value))) return "n/a";
    return Number(value).toLocaleString("en", {
        minimumFractionDigits: fractionDigits,
        maximumFractionDigits: fractionDigits,
    });
}

function formatCompact(value) {
    if (value == null || Number.isNaN(Number(value))) return "n/a";
    return Intl.NumberFormat("en", {
        notation: "compact",
        maximumFractionDigits: 1,
    }).format(value);
}

function mean(values) {
    const valid = values.filter(v => v != null && !Number.isNaN(Number(v)));
    if (!valid.length) return null;
    return valid.reduce((sum, value) => sum + Number(value), 0) / valid.length;
}

function domainFor(values, { includeZero = false, padRatio = 0.08 } = {}) {
    const valid = values
        .filter(v => v != null && !Number.isNaN(Number(v)))
        .map(Number);

    if (includeZero) valid.push(0);
    if (!valid.length) return {};

    let min = Math.min(...valid);
    let max = Math.max(...valid);
    if (min === max) {
        const pad = Math.max(Math.abs(max) * 0.1, 1);
        return { min: min - pad, max: max + pad };
    }

    const pad = (max - min) * padRatio;
    if (includeZero && min >= 0) min = 0;
    return { min: Math.max(0, min - pad), max: max + pad };
}

function bindButtons(containerId, activeClass, dataAttr, onChange) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.querySelectorAll("button").forEach(button => {
        button.addEventListener("click", () => {
            container
                .querySelectorAll("button")
                .forEach(btn => btn.classList.remove(activeClass));
            button.classList.add(activeClass);
            onChange(button.dataset[dataAttr]);
        });
    });
}

function makeVerticalLinePlugin(id, lines) {
    return {
        id,
        afterDraw(chart) {
            const { ctx, chartArea, scales } = chart;
            const x = scales.x;
            if (!x || !chartArea) return;

            ctx.save();
            lines.forEach(line => {
                if (line.value == null || Number.isNaN(Number(line.value))) return;
                const xPos = x.getPixelForValue(line.value);
                if (xPos < chartArea.left || xPos > chartArea.right) return;

                ctx.beginPath();
                ctx.setLineDash(line.dash || []);
                ctx.strokeStyle = line.color;
                ctx.lineWidth = line.width || 2;
                ctx.moveTo(xPos, chartArea.top);
                ctx.lineTo(xPos, chartArea.bottom);
                ctx.stroke();

                ctx.setLineDash([]);
                ctx.fillStyle = line.color;
                ctx.font = "600 10px 'JetBrains Mono', monospace";
                ctx.textAlign = xPos > chartArea.right - 90 ? "right" : "left";
                const labelX = xPos > chartArea.right - 90 ? xPos - 5 : xPos + 5;
                ctx.fillText(line.label, labelX, chartArea.top + line.offset);
            });
            ctx.restore();
        },
    };
}

function truncateLabel(label, max = 28) {
    if (!label) return "";
    return label.length > max ? label.slice(0, max - 3) + "..." : label;
}


/* -- Chart 1: country regional dot plot --------------------------------- */
let countryChart = null;
let countryData = null;
let activeCountryField = "gdp_per_capita_pps";

async function loadCountryData(countryCode) {
    const res = await fetch(`/api/country/${countryCode}`);
    countryData = await res.json();
    renderCountryChart(activeCountryField);
}

function setCountryMessage(message) {
    const wrap = document.getElementById("country-chart-wrap");
    const placeholder = document.getElementById("country-placeholder");

    if (countryChart) {
        countryChart.destroy();
        countryChart = null;
    }

    wrap.style.display = "none";
    placeholder.style.display = "block";
    placeholder.textContent = message;
}

function renderCountryChart(field) {
    if (!countryData) return;

    const cfg = COUNTRY_METRICS[field];
    if (!cfg) return;

    const regions = countryData.regions
        .filter(region => region[field] != null)
        .sort((a, b) => b[field] - a[field]);

    if (!regions.length) {
        setCountryMessage(`No regional ${cfg.label.toLowerCase()} data is available for this country.`);
        return;
    }

    const wrap = document.getElementById("country-chart-wrap");
    const placeholder = document.getElementById("country-placeholder");
    wrap.style.display = "block";
    wrap.style.height = `${Math.max(440, Math.min(1080, regions.length * 25 + 170))}px`;
    placeholder.style.display = "none";

    const values = regions.map(region => Number(region[field]));
    const countryAvg = mean(values);
    const euAvg = cfg.euAvgField ? countryData.eu_averages?.[cfg.euAvgField] : null;
    const domain = domainFor([...values, countryAvg, euAvg], { padRatio: 0.1 });
    const labels = regions.map(region => region.region_name || region.nuts2_code);

    const points = regions.map((region, index) => ({
        x: Number(region[field]),
        y: index,
        label: region.region_name || region.nuts2_code,
        code: region.nuts2_code,
        typology: region.typology || "unknown",
    }));

    const ctx = document.getElementById("chart-country").getContext("2d");
    if (countryChart) countryChart.destroy();

    countryChart = new Chart(ctx, {
        type: "scatter",
        data: {
            datasets: [{
                label: "Regions",
                data: points,
                backgroundColor: points.map(point => colourFor(point.typology, "bg")),
                borderColor: points.map(point => colourFor(point.typology, "border")),
                borderWidth: 1.5,
                pointRadius: 5,
                pointHoverRadius: 7,
            }],
        },
        plugins: [
            makeVerticalLinePlugin("countryReferences", [
                {
                    value: countryAvg,
                    label: `country avg ${cfg.fmt(countryAvg)}`,
                    color: SIGNAL,
                    dash: [],
                    offset: 14,
                },
                {
                    value: euAvg,
                    label: `EU avg ${cfg.fmt(euAvg)}`,
                    color: INK,
                    dash: [6, 4],
                    offset: 30,
                },
            ]),
        ],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            parsing: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...TOOLTIP,
                    callbacks: {
                        title: items => items[0]?.raw?.label || "",
                        label: item => [
                            `Code: ${item.raw.code}`,
                            `Type: ${item.raw.typology}`,
                            `${cfg.label}: ${cfg.fmt(item.parsed.x)}`,
                        ],
                    },
                },
            },
            scales: {
                x: {
                    ...domain,
                    grid: { color: GRID_COLOR },
                    ticks: { callback: value => cfg.tick(value) },
                    title: {
                        display: true,
                        text: cfg.label,
                        color: AXIS_TITLE,
                        font: { size: 11 },
                    },
                },
                y: {
                    type: "linear",
                    min: -0.75,
                    max: labels.length - 0.25,
                    reverse: true,
                    grid: { display: false },
                    ticks: {
                        stepSize: 1,
                        color: TICK_COLOR,
                        font: { size: labels.length > 24 ? 9 : 10 },
                        callback: value => Number.isInteger(value)
                            ? truncateLabel(labels[value], labels.length > 24 ? 22 : 30)
                            : "",
                    },
                },
            },
        },
    });
}

function initCountryControls() {
    const select = document.getElementById("country-select");
    if (!select) return;

    select.addEventListener("change", () => {
        if (select.value) {
            loadCountryData(select.value).catch(err => {
                console.error("Country chart:", err);
                setCountryMessage("The country data could not be loaded.");
            });
        } else {
            countryData = null;
            setCountryMessage("Select a country to load its regional data");
        }
    });

    bindButtons("country-metric-toggle", "metric-btn--active", "field", field => {
        activeCountryField = field;
        renderCountryChart(activeCountryField);
    });
}


/* -- Chart 2: typology by country income half --------------------------- */
let splitData = null;
let splitChart = null;
let activeSplitMetric = "gdp_per_capita";

async function initIncomeSplitChart() {
    const res = await fetch("/api/typology-income-split");
    splitData = await res.json();
    renderIncomeSplitChart(activeSplitMetric);

    bindButtons("split-metric-tabs", "chart-tab--active", "metric", metric => {
        activeSplitMetric = metric;
        renderIncomeSplitChart(activeSplitMetric);
    });
}

function renderIncomeSplitChart(metric) {
    if (!splitData) return;

    const cfg = METRICS[metric];
    if (!cfg) return;

    const groups = [...new Set(splitData.map(row => row.income_group))]
        .sort((a, b) => {
            const aOrder = splitData.find(row => row.income_group === a)?.income_group_order || 0;
            const bOrder = splitData.find(row => row.income_group === b)?.income_group_order || 0;
            return aOrder - bOrder;
        });

    const datasets = TYPOLOGIES.map(typology => ({
        label: typology,
        data: groups.map(group => {
            const row = splitData.find(item => (
                item.income_group === group && item.typology === typology
            ));
            return row?.[cfg.avgField] ?? null;
        }),
        backgroundColor: colourFor(typology, "bg"),
        borderColor: colourFor(typology, "border"),
        borderWidth: 2,
        borderRadius: 5,
        borderSkipped: false,
    }));

    const ctx = document.getElementById("chart-income-split").getContext("2d");
    if (splitChart) splitChart.destroy();

    splitChart = new Chart(ctx, {
        type: "bar",
        data: { labels: groups, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "top",
                    labels: { font: { size: 11 }, padding: 14 },
                },
                tooltip: {
                    ...TOOLTIP,
                    callbacks: {
                        label: item => {
                            const row = splitData.find(entry => (
                                entry.income_group === item.label &&
                                entry.typology === item.dataset.label
                            ));
                            return [
                                `${item.dataset.label}: ${cfg.fmt(item.parsed.y)}`,
                                `Regions: ${row?.n_regions ?? "n/a"}`,
                            ];
                        },
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: GRID_COLOR },
                    ticks: { callback: value => cfg.tick(value) },
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
                        color: TICK_COLOR,
                        font: { weight: "600", size: 12, family: "'Newsreader', Georgia, serif" },
                    },
                },
            },
        },
    });
}


/* -- Chart 3: railway density buckets ----------------------------------- */
let railBucketData = null;
let railBucketChart = null;
let activeRailBucketMetric = "gdp_per_capita";

async function initRailBucketChart() {
    const res = await fetch("/api/rail-density-buckets");
    railBucketData = await res.json();
    renderRailBucketChart(activeRailBucketMetric);

    bindButtons("rail-bucket-tabs", "chart-tab--active", "metric", metric => {
        activeRailBucketMetric = metric;
        renderRailBucketChart(activeRailBucketMetric);
    });
}

function bucketLabel(row) {
    return [
        `Q${row.rail_bucket}`,
        `${formatNumber(row.min_railway_density, 0)}-${formatNumber(row.max_railway_density, 0)} km`,
    ];
}

function renderRailBucketChart(metric) {
    if (!railBucketData) return;

    const cfg = METRICS[metric];
    if (!cfg) return;

    const labels = railBucketData.map(bucketLabel);
    const values = railBucketData.map(row => row[cfg.avgField]);

    const ctx = document.getElementById("chart-rail-buckets").getContext("2d");
    if (railBucketChart) railBucketChart.destroy();

    railBucketChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: cfg.label,
                data: values,
                backgroundColor: "rgba(200, 55, 26, 0.72)",
                borderColor: "rgba(200, 55, 26, 1)",
                borderWidth: 2,
                borderRadius: 5,
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
                        title: items => {
                            const row = railBucketData[items[0].dataIndex];
                            return `Rail-density band Q${row.rail_bucket}`;
                        },
                        label: item => `${cfg.label}: ${cfg.fmt(item.parsed.y)}`,
                        afterLabel: item => {
                            const row = railBucketData[item.dataIndex];
                            return [
                                `Rail range: ${formatNumber(row.min_railway_density, 1)}-${formatNumber(row.max_railway_density, 1)} km/1,000 km²`,
                                `Average rail density: ${formatNumber(row.avg_railway_density, 1)} km/1,000 km²`,
                                `Regions: ${row.n_regions}`,
                                `Urban/intermediate/rural: ${row.urban_regions}/${row.intermediate_regions}/${row.rural_regions}`,
                            ];
                        },
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: GRID_COLOR },
                    ticks: { callback: value => cfg.tick(value) },
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
                        color: TICK_COLOR,
                        font: { weight: "600", size: 11 },
                    },
                },
            },
        },
    });
}


/* -- Chart 4: country gap dumbbells ------------------------------------- */
let gapData = null;
let gapChart = null;
let activeGapMetric = "gdp_per_capita_pps";

async function initCountryGapChart() {
    const res = await fetch("/api/country-gap-rankings");
    gapData = await res.json();
    renderCountryGapChart(activeGapMetric);

    bindButtons("gap-metric-tabs", "chart-tab--active", "metric", metric => {
        activeGapMetric = metric;
        renderCountryGapChart(activeGapMetric);
    });
}

function makeDumbbellEndpointPlugin(rows, cfg) {
    return {
        id: "dumbbellEndpoints",
        afterDatasetsDraw(chart) {
            const { ctx, chartArea, scales } = chart;
            const x = scales.x;
            const y = scales.y;
            if (!x || !y || !chartArea) return;

            ctx.save();
            rows.forEach((row, index) => {
                const metric = row.metrics[activeGapMetric];
                if (!metric) return;
                const yPos = y.getPixelForValue(index);
                const xMin = x.getPixelForValue(metric.min);
                const xMax = x.getPixelForValue(metric.max);

                [
                    { xPos: xMin, fill: PAPER, stroke: INK },
                    { xPos: xMax, fill: SIGNAL, stroke: SIGNAL },
                ].forEach(point => {
                    ctx.beginPath();
                    ctx.arc(point.xPos, yPos, 5.5, 0, Math.PI * 2);
                    ctx.fillStyle = point.fill;
                    ctx.fill();
                    ctx.lineWidth = 2;
                    ctx.strokeStyle = point.stroke;
                    ctx.stroke();
                });
            });
            ctx.restore();
        },
    };
}

function renderCountryGapChart(field) {
    if (!gapData) return;

    const cfg = GAP_METRICS[field];
    if (!cfg) return;

    const rows = gapData
        .filter(country => country.metrics?.[field])
        .sort((a, b) => b.metrics[field].gap - a.metrics[field].gap)
        .slice(0, 18);

    const labels = rows.map(row => row.country_name);
    const values = rows.map(row => {
        const metric = row.metrics[field];
        return [metric.min, metric.max];
    });
    const domainValues = rows.flatMap(row => {
        const metric = row.metrics[field];
        return [metric.min, metric.max];
    });
    const domain = domainFor(domainValues, { padRatio: 0.06 });

    const ctx = document.getElementById("chart-country-gaps").getContext("2d");
    if (gapChart) gapChart.destroy();

    gapChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels,
            datasets: [{
                label: cfg.label,
                data: values,
                backgroundColor: "rgba(20, 17, 10, 0.12)",
                borderColor: "rgba(20, 17, 10, 0.55)",
                borderWidth: 1.5,
                borderSkipped: false,
                barPercentage: 0.34,
                categoryPercentage: 0.82,
            }],
        },
        plugins: [makeDumbbellEndpointPlugin(rows, cfg)],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: "y",
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...TOOLTIP,
                    callbacks: {
                        title: items => rows[items[0].dataIndex]?.country_name || "",
                        label: item => {
                            const row = rows[item.dataIndex];
                            const metric = row.metrics[field];
                            return [
                                `Gap: ${cfg.fmt(metric.gap)}`,
                                `Lowest: ${metric.min_region} (${cfg.fmt(metric.min)})`,
                                `Highest: ${metric.max_region} (${cfg.fmt(metric.max)})`,
                                `Regions with data: ${metric.count}/${row.n_regions}`,
                            ];
                        },
                    },
                },
            },
            scales: {
                x: {
                    ...domain,
                    grid: { color: GRID_COLOR },
                    ticks: { callback: value => cfg.tick(value) },
                    title: {
                        display: true,
                        text: cfg.label,
                        color: AXIS_TITLE,
                        font: { size: 11 },
                    },
                },
                y: {
                    grid: { display: false },
                    ticks: {
                        color: TICK_COLOR,
                        font: { size: 10.5, family: "'Newsreader', Georgia, serif" },
                    },
                },
            },
        },
    });
}


/* -- Bootstrap ----------------------------------------------------------- */
document.addEventListener("DOMContentLoaded", () => {
    initCountryControls();
    initIncomeSplitChart().catch(err => console.error("Income split chart:", err));
    initRailBucketChart().catch(err => console.error("Rail bucket chart:", err));
    initCountryGapChart().catch(err => console.error("Country gap chart:", err));
});
