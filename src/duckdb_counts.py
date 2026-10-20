import argparse
import json
import os

import duckdb

from common import BUCKET, RAW_KEY, ROOT, save_json


def sql_string(value):
    return "'" + value.replace("'", "''") + "'"


def count_skills():
    extension_dir = os.getenv(
        "DUCKDB_EXTENSION_DIRECTORY",
        str(ROOT / ".duckdb-extensions"),
    )
    os.makedirs(extension_dir, exist_ok=True)
    db = duckdb.connect(config={"extension_directory": extension_dir})
    db.execute("LOAD httpfs")

    endpoint = os.getenv("S3_ENDPOINT", "http://127.0.0.1:9110")
    access_key = sql_string(os.environ["AWS_ACCESS_KEY_ID"])
    secret_key = sql_string(os.environ["AWS_SECRET_ACCESS_KEY"])
    host = sql_string(endpoint.split("://", 1)[1])
    use_ssl = str(endpoint.startswith("https://")).lower()

    db.execute(
        "CREATE SECRET lake ("
        "TYPE S3, "
        f"KEY_ID {access_key}, "
        f"SECRET {secret_key}, "
        f"ENDPOINT {host}, "
        "REGION 'us-east-1', "
        "URL_STYLE 'path', "
        f"USE_SSL {use_ssl})"
    )

    sql = (ROOT / "sql" / "php_counts.sql").read_text(encoding="utf-8")
    sql = sql.replace("__S3_URI__", f"s3://{BUCKET}/{RAW_KEY}")
    rows = db.execute(sql).fetchall()
    selected_rows = db.execute("SELECT count(*) FROM php_rows").fetchone()[0]
    db.close()

    counts = [
        {"size": size, "skills": skills, "frequency": frequency}
        for size, skills, frequency in rows
    ]
    return {"selected_rows": selected_rows, "counts": counts}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    result = count_skills()
    save_json(args.out, result)
    print(json.dumps({
        "method": "DuckDB",
        "selected_rows": result["selected_rows"],
        "different_sets": len(result["counts"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
