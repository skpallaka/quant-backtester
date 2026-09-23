"""Aggregate daily returns and rolling volatility across the ticker
universe using PySpark: JDBC read straight from Postgres, window functions
for per-ticker daily returns and 30-day trailing rolling volatility, then
groupBy/agg to per-ticker and per-sector summary stats.

Run with:
  JAVA_HOME=$(brew --prefix openjdk@17) python scripts/spark_analysis.py

Requires Postgres up and populated (docker compose up -d postgres &&
python scripts/fetch_universe.py) and a JDK 17+ on PATH/JAVA_HOME --
PySpark 4.x doesn't run on Java 8.
"""

from __future__ import annotations

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

from quant_backtester.data.loader import get_database_url
from quant_backtester.tickers import TICKERS


def jdbc_url_and_properties() -> tuple[str, dict]:
    """Convert the SQLAlchemy-style DATABASE_URL into a plain JDBC url +
    connection properties, since Spark's JDBC reader doesn't speak the
    `postgresql+psycopg://` driver prefix SQLAlchemy uses.
    """
    url = get_database_url().removeprefix("postgresql+psycopg://")
    creds, host_and_db = url.split("@")
    user, password = creds.split(":")
    return f"jdbc:postgresql://{host_and_db}", {
        "user": user,
        "password": password,
        "driver": "org.postgresql.Driver",
    }


def main() -> None:
    spark = (
        SparkSession.builder
        .appName("quant-backtester-ticker-analysis")
        .master("local[*]")
        .config("spark.jars.packages", "org.postgresql:postgresql:42.7.4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    jdbc_url, props = jdbc_url_and_properties()
    ohlcv = spark.read.jdbc(url=jdbc_url, table="ohlcv", properties=props)

    sectors = spark.createDataFrame(list(TICKERS.items()), ["ticker", "sector"])
    df = ohlcv.join(sectors, "ticker")

    ticker_ordered = Window.partitionBy("ticker").orderBy("date")
    df = df.withColumn("prev_close", F.lag("close").over(ticker_ordered))
    df = df.withColumn("daily_return", (F.col("close") - F.col("prev_close")) / F.col("prev_close"))

    rolling_30d = ticker_ordered.rowsBetween(-29, 0)
    df = df.withColumn("rolling_vol_30d", F.stddev("daily_return").over(rolling_30d))
    df = df.withColumn("annualized_vol_30d", F.col("rolling_vol_30d") * F.sqrt(F.lit(252.0)))

    print(f"\n=== {df.count()} rows across {df.select('ticker').distinct().count()} tickers ===\n")

    print("=== Sample: rolling volatility for one ticker (NVDA) ===")
    df.filter(F.col("ticker") == "NVDA") \
      .select("date", "close", "daily_return", "annualized_vol_30d") \
      .orderBy(F.desc("date")).show(10, truncate=False)

    print("=== Per-ticker summary (annualized Sharpe-like ratio, ranked) ===")
    per_ticker = df.groupBy("ticker", "sector").agg(
        F.count("daily_return").alias("n_days"),
        F.avg("daily_return").alias("avg_daily_return"),
        F.stddev("daily_return").alias("daily_return_std"),
        (F.avg("daily_return") / F.stddev("daily_return") * F.sqrt(F.lit(252.0))).alias("sharpe_annualized"),
        F.avg("annualized_vol_30d").alias("avg_annualized_vol"),
    ).orderBy(F.desc("sharpe_annualized"))
    per_ticker.show(40, truncate=False)

    print("=== Per-sector aggregation ===")
    per_sector = df.groupBy("sector").agg(
        F.countDistinct("ticker").alias("n_tickers"),
        F.avg("daily_return").alias("avg_daily_return"),
        F.avg("annualized_vol_30d").alias("avg_annualized_vol"),
        F.stddev("daily_return").alias("cross_sectional_return_std"),
    ).orderBy(F.desc("avg_daily_return"))
    per_sector.show(truncate=False)

    per_ticker.toPandas().to_csv("results/spark_per_ticker_summary.csv", index=False)
    per_sector.toPandas().to_csv("results/spark_per_sector_summary.csv", index=False)
    print("\nSaved results/spark_per_ticker_summary.csv and results/spark_per_sector_summary.csv")

    spark.stop()


if __name__ == "__main__":
    main()
