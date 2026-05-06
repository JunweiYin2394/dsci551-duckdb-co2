import streamlit as st
import duckdb
import pandas as pd
import time

st.title("CO₂ Analytics — DuckDB Internals Probe")

con = duckdb.connect()

CSV_PATH     = "data/co-emissions-per-capita.csv"
PARQUET_PATH = "data/co-emissions-per-capita.parquet"

page = st.sidebar.radio("Feature", [
    "Top Emitters",
    "Country Comparison",
    "CSV vs Parquet Benchmark",
    "Trend Explorer"
])

def run_timed(sql):
    t0 = time.perf_counter()
    df = con.execute(sql).df()
    ms = (time.perf_counter() - t0) * 1000
    return df, ms

def show_explain(sql, use_parquet=True):
    path = PARQUET_PATH if use_parquet else CSV_PATH
    sql = sql.replace("__DATA__", f"'{path}'")
    plan = con.execute(f"EXPLAIN {sql}").fetchdf()["explain_value"][0]
    st.code(plan)


# ── Page 1: Top Emitters ──────────────────────────────────────────────────────
if page == "Top Emitters":
    st.header("Top Emitters")
    st.caption("Internal: TOP_N Heap Sort — O(N log K) instead of O(N log N)")

    year = st.slider("Year", 1950, 2024, 2022)
    k    = st.select_slider("Top K", [5, 10, 15, 20, 50], value=10)
    show_plan = st.checkbox("Show EXPLAIN plan")

    df, ms = run_timed(f"""
        SELECT Entity, Code, Year, "CO₂ emissions per capita" AS co2_pc
        FROM '{PARQUET_PATH}'
        WHERE Year = {year}
        ORDER BY co2_pc DESC
        LIMIT {k}
    """)

    st.metric("Query time", f"{ms:.1f} ms")
    st.bar_chart(df.set_index("Entity")["co2_pc"])
    st.dataframe(df, hide_index=True)

    if show_plan:
        st.subheader("EXPLAIN Plan")
        st.write("User picks Top K → DuckDB uses TOP_N heap, never sorts all rows.")
        show_explain(f"""
            SELECT Entity, Code, Year, "CO₂ emissions per capita" AS co2_pc
            FROM __DATA__
            WHERE Year = {year}
            ORDER BY co2_pc DESC
            LIMIT {k}
        """)


# ── Page 2: Country Comparison ───────────────────────────────────────────────
elif page == "Country Comparison":
    st.header("Country Comparison")
    st.caption("Internal: SEMI HASH JOIN — IN-clause builds a hash table, not repeated OR checks")

    COUNTRIES = ["China", "United States", "India", "Germany", "Russia",
                 "Japan", "United Kingdom", "Canada", "Australia", "Brazil"]

    selected  = st.multiselect("Countries", COUNTRIES, default=["China", "United States", "India"])
    yr_range  = st.slider("Year range", 1960, 2024, (2000, 2022))
    show_plan = st.checkbox("Show EXPLAIN plan")

    if not selected:
        st.warning("Select at least one country.")
        st.stop()

    in_list = ", ".join(f"'{c}'" for c in selected)
    df, ms = run_timed(f"""
        SELECT Entity, Year, "CO₂ emissions per capita" AS co2_pc
        FROM '{PARQUET_PATH}'
        WHERE Entity IN ({in_list})
          AND Year BETWEEN {yr_range[0]} AND {yr_range[1]}
        ORDER BY Year
    """)

    st.metric("Query time", f"{ms:.1f} ms")
    pivot = df.pivot(index="Year", columns="Entity", values="co2_pc")
    st.line_chart(pivot)
    st.dataframe(df, hide_index=True)

    if show_plan:
        st.subheader("EXPLAIN Plan")
        st.write("IN-clause → DuckDB builds a hash table and does SEMI HASH JOIN instead of repeated OR.")
        show_explain(f"""
            SELECT Entity, Year, "CO₂ emissions per capita" AS co2_pc
            FROM __DATA__
            WHERE Entity IN ({in_list})
              AND Year BETWEEN {yr_range[0]} AND {yr_range[1]}
            ORDER BY Year
        """)


# ── Page 3: CSV vs Parquet ───────────────────────────────────────────────────
elif page == "CSV vs Parquet Benchmark":
    st.header("CSV vs Parquet Benchmark")
    st.caption("Internal: Predicate Pushdown — Parquet filters at disk, CSV reads everything first")

    year   = st.slider("Filter year", 1950, 2024, 2020)
    n_runs = st.select_slider("Runs to average", [1, 3, 5], value=3)

    if st.button("Run Benchmark"):
        q = """SELECT Entity, "CO₂ emissions per capita" AS co2_pc
               FROM '{path}'
               WHERE Year = {year}
               ORDER BY co2_pc DESC LIMIT 20"""

        # warm up
        con.execute(q.format(path=CSV_PATH,     year=year)).df()
        con.execute(q.format(path=PARQUET_PATH, year=year)).df()

        csv_times, pq_times = [], []
        for _ in range(n_runs):
            _, t = run_timed(q.format(path=CSV_PATH,     year=year)); csv_times.append(t)
            _, t = run_timed(q.format(path=PARQUET_PATH, year=year)); pq_times.append(t)

        csv_avg = sum(csv_times) / n_runs
        pq_avg  = sum(pq_times)  / n_runs

        col1, col2, col3 = st.columns(3)
        col1.metric("CSV avg",     f"{csv_avg:.1f} ms")
        col2.metric("Parquet avg", f"{pq_avg:.1f} ms")
        col3.metric("Speedup",     f"{csv_avg/pq_avg:.1f}x")

        chart = pd.DataFrame({"Time (ms)": [csv_avg, pq_avg]}, index=["CSV", "Parquet"])
        st.bar_chart(chart)

        st.subheader("CSV EXPLAIN Plan")
        st.write("Filter happens AFTER full scan — READ_CSV_AUTO reads all 39,000 rows first.")
        show_explain(f"""
            SELECT Entity, "CO₂ emissions per capita" AS co2_pc
            FROM __DATA__
            WHERE Year = {year}
            ORDER BY co2_pc DESC LIMIT 20
        """, use_parquet=False)

        st.subheader("Parquet EXPLAIN Plan")
        st.write("Filter pushed INTO scanner — only matching rows leave the disk.")
        show_explain(f"""
            SELECT Entity, "CO₂ emissions per capita" AS co2_pc
            FROM __DATA__
            WHERE Year = {year}
            ORDER BY co2_pc DESC LIMIT 20
        """, use_parquet=True)


# ── Page 4: Trend Explorer ───────────────────────────────────────────────────
elif page == "Trend Explorer":
    st.header("Trend Explorer")
    st.caption("Internal: Vectorized GROUP BY — aggregation runs on columns in 1024-value batches")

    metric      = st.selectbox("Aggregate", ["AVG", "MAX", "MIN", "SUM"])
    yr_range    = st.slider("Year range", 1950, 2024, (1990, 2022))
    min_records = st.slider("Min countries per year", 10, 100, 30)
    show_plan   = st.checkbox("Show EXPLAIN plan")

    df, ms = run_timed(f"""
        SELECT Year,
               {metric}("CO₂ emissions per capita") AS agg_value,
               COUNT(*) AS num_countries
        FROM '{PARQUET_PATH}'
        WHERE Year BETWEEN {yr_range[0]} AND {yr_range[1]}
        GROUP BY Year
        HAVING COUNT(*) >= {min_records}
        ORDER BY Year
    """)

    st.metric("Query time", f"{ms:.1f} ms")
    st.line_chart(df.set_index("Year")["agg_value"])
    st.dataframe(df, hide_index=True)

    if show_plan:
        st.subheader("EXPLAIN Plan")
        st.write("GROUP BY → DuckDB uses HASH_GROUP_BY, processes CO₂ column in vectorized batches.")
        show_explain(f"""
            SELECT Year,
                   {metric}("CO₂ emissions per capita") AS agg_value,
                   COUNT(*) AS num_countries
            FROM __DATA__
            WHERE Year BETWEEN {yr_range[0]} AND {yr_range[1]}
            GROUP BY Year
            HAVING COUNT(*) >= {min_records}
            ORDER BY Year
        """)