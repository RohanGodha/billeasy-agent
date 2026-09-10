# Databricks notebook source
# MAGIC %md
# MAGIC # counter_copilot — Delta seed
# MAGIC
# MAGIC Idempotent notebook that creates the catalog, schema, and six Delta tables
# MAGIC used by `counter-copilot`. Run it once after setting up your Free Edition
# MAGIC workspace + serverless SQL warehouse.

# COMMAND ----------

CATALOG = "counter_copilot"
SCHEMA = "core"

spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA  IF NOT EXISTS {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Table DDLs

DDLS = [
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.counters (
        id STRING, name STRING, counter_type STRING, city STRING, tier STRING,
        operator STRING, monthly_tpv DOUBLE, onboarded_date DATE, kyc_status STRING,
        phone STRING, email STRING, settlement_cycle STRING
    ) USING DELTA
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.counter_health (
        id STRING, counter_id STRING, device_type STRING, pending_settlement DOUBLE,
        avg_daily_txns DOUBLE, digital_share DOUBLE, activated_at DATE
    ) USING DELTA
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.transactions (
        id STRING, counter_id STRING, ts TIMESTAMP, amount DOUBLE,
        category STRING, channel STRING, instrument STRING
    ) USING DELTA
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.modules (
        id STRING, name STRING, category STRING, take_rate DOUBLE,
        min_monthly_tpv DOUBLE, min_daily_txns INT, max_daily_txns INT,
        description STRING, eligibility_json STRING
    ) USING DELTA
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.counter_modules (
        counter_id STRING, module_id STRING, activated_at DATE, status STRING
    ) USING DELTA
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {CATALOG}.{SCHEMA}.field_notes (
        id STRING, counter_id STRING, ts TIMESTAMP, channel STRING, summary STRING
    ) USING DELTA
    """,
]

for d in DDLS:
    spark.sql(d)
print("Tables created.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Loading data
# MAGIC
# MAGIC Upload the CSV exports produced by `backend/scripts/export_sqlite_to_csv.py`
# MAGIC to `/Volumes/counter_copilot/core/seed/` (a Unity Catalog Volume). Then run the
# MAGIC cells below to MERGE them into the Delta tables.

VOLUME = f"/Volumes/{CATALOG}/{SCHEMA}/seed"
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.seed")

def load(table: str, schema: str | None = None):
    path = f"{VOLUME}/{table}.csv"
    df = (
        spark.read.option("header", True)
        .option("inferSchema", True)
        .csv(path)
    )
    if schema:
        for col, typ in schema.items():
            df = df.withColumn(col, df[col].cast(typ))
    df.write.format("delta").mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.{table}")
    print(f"loaded {table}: {df.count()} rows")

load("counters")
load("counter_health")
load("transactions")
load("modules")
load("counter_modules")
load("field_notes")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify

for t in ["counters", "counter_health", "transactions", "modules", "counter_modules", "field_notes"]:
    cnt = spark.sql(f"SELECT COUNT(*) c FROM {CATALOG}.{SCHEMA}.{t}").first()["c"]
    print(f"{t:20s} {cnt:>8d} rows")
