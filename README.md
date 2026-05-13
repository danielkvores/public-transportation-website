# Where the Lines End

Flask data-journalism project on rail infrastructure, regional inequality, and access to opportunity across EU regions.

The site compares transport infrastructure with employment, education, health, and economic indicators at NUTS-2 level. It focuses on within-country regional differences rather than ranking whole countries against one another.

## Current Scope

- Geographic scope: EU-27 only.
- Analytical unit: retained NUTS-2 regions, joined to a dominant urban-rural typology rolled up from NUTS-3.
- Current analytical universe: 27 countries, 242 NUTS-2 regions, and 1,166 NUTS-3 typology records.
- Raw data location: `data/raw/`.
- Database: `database/the_15_minute_divide.db`.
- Core schema: 8 analytical tables plus 3 runtime tracking tables.

## Running Locally

```bash
uv run flask --app app run --debug
```

Rebuild the analytical database from raw files:

```bash
uv run python database/create_db.py
uv run python database/load_data.py
```

## Data Sources

All indicator data comes from Eurostat. The numeric datasets are stored as gzipped SDMX-CSV 2.0 files; the urban-rural typology is stored as an Excel workbook.

| Local file | Eurostat source | Indicator used | Loader filter | Selected year |
| --- | --- | --- | --- | --- |
| `NUTS2021_urban_rural.xlsx` | [NUTS 2021 reference spreadsheet](https://ec.europa.eu/eurostat/documents/345175/629341/NUTS2021.xlsx) | NUTS-3 urban-rural typology | Sheet `Urban-rural`; categories 1, 2, 3 | NUTS 2021 |
| `tran_r_net_linear_2_0.csv.gz` | [`tran_r_net`](https://ec.europa.eu/eurostat/databrowser/view/tran_r_net/default/table?lang=en) | Railway and motorway density | `tra_infr = RL` and `MWAY`; `unit = KM_TKM2` | 2024 |
| `tran_r_vehst_linear_2_0.csv.gz` | [`tran_r_vehst`](https://ec.europa.eu/eurostat/databrowser/view/tran_r_vehst/default/table?lang=en) | Passenger cars per 1,000 inhabitants | `vehicle = CAR`; `unit = P_THAB` | 2024 |
| `lfst_r_lfe2emprt_linear_2_0.csv.gz` | [`lfst_r_lfe2emprt`](https://ec.europa.eu/eurostat/databrowser/view/lfst_r_lfe2emprt/default/table?lang=en) | Employment rate | `age = Y20-64`; `sex = T`; `unit = PC` | 2024 |
| `lfst_r_lfu3rt_linear_2_0.csv.gz` | [`lfst_r_lfu3rt`](https://ec.europa.eu/eurostat/databrowser/view/lfst_r_lfu3rt/default/table?lang=en) | Unemployment rate | `age = Y15-74`; `sex = T`; `isced11 = TOTAL`; `unit = PC` | 2024 |
| `edat_lfse_04_linear_2_0.csv.gz` | [`edat_lfse_04`](https://ec.europa.eu/eurostat/databrowser/view/edat_lfse_04/default/table?lang=en) | Tertiary attainment | `isced11 = ED5-8`; `age = Y25-34`; `sex = T` | 2024 |
| `edat_lfse_16_linear_2_0.csv.gz` | [`edat_lfse_16`](https://ec.europa.eu/eurostat/databrowser/view/edat_lfse_16/default/table?lang=en) | Early school leavers | `age = Y18-24`; `sex = T` | 2019 |
| `demo_r_mlifexp_linear_2_0.csv.gz` | [`demo_r_mlifexp`](https://ec.europa.eu/eurostat/databrowser/view/demo_r_mlifexp/default/table?lang=en) | Life expectancy at birth | `age = Y_LT1`; `sex = T`; `unit = YR` | 2024 |
| `hlth_rs_prsrg_linear_2_0.csv.gz` | [`hlth_rs_prsrg`](https://ec.europa.eu/eurostat/databrowser/view/hlth_rs_prsrg/default/table?lang=en) | Medical doctors per 100,000 inhabitants | `isco08 = OC221`; `unit = P_HTHAB` | 2016 |
| `nama_10r_2gdp_linear_2_0.csv.gz` | [`nama_10r_2gdp`](https://ec.europa.eu/eurostat/databrowser/view/nama_10r_2gdp/default/table?lang=en) | GDP per capita in PPS | `unit = PPS_EU27_2020_HAB` | 2024 |

For each numeric dataset, the loader selects the most recent year with at least 80% valid coverage among reporting EU-27 NUTS-2 regions. If no year meets that threshold, it uses the year with the most valid observations. The selected year is documented per metric because some topic tables combine two indicators from different source years.

## Typology Handling

Eurostat supplies the urban-rural typology at NUTS-3 level. The site displays NUTS-2 indicators, so the loader assigns each NUTS-2 region a dominant typology based on the most common NUTS-3 category among its children. Ties are broken toward the more urban category.

The current raw typology file uses NUTS 2021 boundaries. Some indicator files already contain NUTS 2024 regional codes, so the loader treats the NUTS 2021 typology as the regional universe and skips four-character codes that do not exist there. Current load result: 242 retained NUTS-2 regions.

## Core Schema

```text
countries (1) ──< (many) nuts2_regions
nuts2_regions (1) ──< (many) nuts3_regions
nuts2_regions (1) ──< (many) transport_infrastructure
nuts2_regions (1) ──< (many) employment_outcomes
nuts2_regions (1) ──< (many) education_outcomes
nuts2_regions (1) ──< (many) health_outcomes
nuts2_regions (1) ──< (many) economic_outcomes
```

The runtime tracking module also creates `tracking_sessions`, `tracking_pageviews`, and `tracking_events`.

## Stack

- Backend: Python 3.13, Flask 3.x, raw SQLite3.
- Data pipeline: pandas 3.x and openpyxl.
- Frontend: Jinja templates, vanilla CSS/JS, Chart.js 4.x from CDN.
- No ORM and no JavaScript build step.

## Main Routes

- `/` narrative landing page.
- `/data` interactive data explorer.
- `/methodology` data sources, cleaning notes, schema, and limitations.
- `/about` project context and technical summary.
- `/tracker` local usage dashboard.
