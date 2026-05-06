# DuckDB Internals + CO₂ Analytics Application
DSCI 551 — Foundations of Data Management
Junwei Yin | University of Southern California | Spring 2026

---

## Overview

A CO₂ emissions analytics dashboard built with DuckDB and Streamlit.
Each feature is designed to trigger a specific DuckDB internal mechanism:

| Feature | Internal Mechanism |
|---|---|
| Top Emitters | TOP-N Heap Sort + Predicate Pushdown |
| Country Comparison | Predicate Pushdown via IN-clause |
| CSV vs Parquet Benchmark | Predicate Pushdown performance comparison |
| Trend Explorer | PERFECT_HASH_GROUP_BY + Projection Pushdown |

---

> **Note:** This project was originally a two-person group. My partner withdrew from the course after the midterm report was submitted. The two internal focus areas defined in the midterm report — query execution optimization (TOP-N) and storage-layer optimization (Predicate Pushdown / Parquet) — were retained and fully implemented by me individually.

## Setup & Run

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Convert CSV to Parquet (if needed)**

The Parquet file is already included in the `data/` folder.
If you need to regenerate it, run Cell 12 in `duckdb_start.ipynb`:
```python
con.execute("""
    COPY 'data/co-emissions-per-capita.csv'
    TO 'data/co-emissions-per-capita.parquet'
    (FORMAT parquet)
""")
```

**3. Run the app**
```bash
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

---

## Dataset

CO₂ emissions per capita dataset from [Our World in Data](https://ourworldindata.org/co2-emissions).
- 26,508 records
- 200+ countries and regions
- Years: 1949–2024
- Columns: Entity, Code, Year, CO₂ emissions per capita (tonnes/person)
