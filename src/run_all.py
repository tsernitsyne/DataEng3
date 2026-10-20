import argparse
import csv
import hashlib
import io
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import psutil
from boto3.s3.transfer import TransferConfig

from analyze import analyze
from common import BUCKET, RAW_KEY, ROOT, is_php_vacancy, s3_client, save_json


def upload_data(csv_path, s3):
    bucket_names = {item["Name"] for item in s3.list_buckets()["Buckets"]}
    if BUCKET not in bucket_names:
        s3.create_bucket(Bucket=BUCKET)

    started = time.perf_counter()
    s3.upload_file(
        str(csv_path),
        BUCKET,
        RAW_KEY,
        Config=TransferConfig(
            multipart_threshold=64 * 1024 * 1024,
            multipart_chunksize=64 * 1024 * 1024,
            max_concurrency=2,
        ),
    )

    digest = hashlib.sha256()
    with csv_path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)

    segment = io.StringIO(newline="")
    csv.field_size_limit(20_000_000)
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(segment, fieldnames=reader.fieldnames)
        writer.writeheader()
        segment_rows = 0
        for row in reader:
            if is_php_vacancy(row):
                writer.writerow(row)
                segment_rows += 1

    segment_bytes = segment.getvalue().encode("utf-8")
    s3.put_object(Bucket=BUCKET, Key="segments/php.csv", Body=segment_bytes)
    raw = s3.head_object(Bucket=BUCKET, Key=RAW_KEY)

    result = {
        "bucket": BUCKET,
        "raw_key": RAW_KEY,
        "raw_bytes": raw["ContentLength"],
        "raw_sha256": digest.hexdigest(),
        "segment_key": "segments/php.csv",
        "segment_rows": segment_rows,
        "segment_bytes": len(segment_bytes),
        "upload_seconds": round(time.perf_counter() - started, 3),
    }
    save_json(ROOT / "results" / "storage.json", result)
    return result


def measure(script, run_number):
    run_path = ROOT / ".runs" / f"{script}-{run_number}.json"
    log_path = ROOT / "evidence" / f"{script}-{run_number}.log"
    run_path.parent.mkdir(exist_ok=True)
    log_path.parent.mkdir(exist_ok=True)
    command = [
        sys.executable,
        str(ROOT / "src" / f"{script}.py"),
        "--out",
        str(run_path),
    ]

    started = time.perf_counter()
    peak_bytes = 0
    with log_path.open("w", encoding="utf-8") as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        process = psutil.Process(child.pid)
        while child.poll() is None:
            try:
                processes = [process] + process.children(recursive=True)
            except psutil.NoSuchProcess:
                processes = []
            total_bytes = 0
            for item in processes:
                try:
                    total_bytes += item.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            peak_bytes = max(peak_bytes, total_bytes)
            time.sleep(0.02)

    if child.returncode != 0:
        raise RuntimeError(f"{script} failed; see {log_path}")

    measurement = {
        "method": script,
        "run": run_number,
        "seconds": round(time.perf_counter() - started, 3),
        "peak_memory_mib": round(peak_bytes / 1024 / 1024, 1),
    }
    output = json.loads(run_path.read_text(encoding="utf-8"))
    return measurement, output


def upload_counts(count_rows, s3):
    uploaded = []
    for size in (1, 2, 3):
        text = io.StringIO(newline="")
        writer = csv.writer(text)
        writer.writerow(["skills", "frequency"])
        matching = [row for row in count_rows if row["size"] == size]
        for row in matching:
            writer.writerow([
                json.dumps(row["skills"], ensure_ascii=False),
                row["frequency"],
            ])

        body = text.getvalue().encode("utf-8")
        key = f"results/php/skills_{size}.csv"
        s3.put_object(Bucket=BUCKET, Key=key, Body=body)
        downloaded = s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
        if downloaded != body:
            raise RuntimeError(f"S3 verification failed: {key}")
        (ROOT / "results" / f"skills_{size}.csv").write_bytes(body)
        uploaded.append({"key": key, "rows": len(matching), "bytes": len(body)})

    save_json(ROOT / "results" / "uploaded-results.json", uploaded)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    args = parser.parse_args()

    s3 = s3_client()
    storage = upload_data(args.csv, s3)
    before = s3.head_object(Bucket=BUCKET, Key=RAW_KEY)
    print(f"Uploaded {storage['raw_bytes']} bytes; PHP vacancies: {storage['segment_rows']}", flush=True)

    _, reference = measure("mapreduce", 0)
    _, sql_result = measure("duckdb_counts", 0)
    if reference["counts"] != sql_result["counts"]:
        raise RuntimeError("MapReduce and DuckDB counts differ")
    if reference["selected_rows"] != sql_result["selected_rows"]:
        raise RuntimeError("MapReduce and DuckDB selected different vacancy counts")

    measurements = []
    for run_number in (1, 2, 3):
        methods = ("mapreduce", "duckdb_counts")
        if run_number == 2:
            methods = tuple(reversed(methods))
        for method in methods:
            measurement, result = measure(method, run_number)
            if result["counts"] != reference["counts"]:
                raise RuntimeError(f"Counts differ: {method}, run {run_number}")
            measurements.append(measurement)
            print(measurement, flush=True)

    save_json(ROOT / "results" / "benchmark.json", measurements)
    vacancies = reference["vacancies"]
    summary = {}
    for size in (1, 2, 3):
        rows = [row for row in reference["counts"] if row["size"] == size]
        total = sum(row["frequency"] for row in rows)
        expected = sum(math.comb(len(row["skills"]), size) for row in vacancies)
        if total != expected:
            raise RuntimeError(f"Combination total differs for size {size}")
        summary[str(size)] = {"different_sets": len(rows), "occurrences": total}

    report = analyze(vacancies, reference["counts"])
    save_json(ROOT / "results" / "analysis.json", report)
    upload_counts(reference["counts"], s3)

    after = s3.head_object(Bucket=BUCKET, Key=RAW_KEY)
    if before["ETag"] != after["ETag"] or before["ContentLength"] != after["ContentLength"]:
        raise RuntimeError("The input object changed during calculation")

    save_json(ROOT / "results" / "verification.json", {
        "selected_rows": reference["selected_rows"],
        "all_count_rows_equal": True,
        "warmups": 2,
        "measured_runs": 6,
        "summary": summary,
    })
    print("All MapReduce and DuckDB results match", flush=True)


if __name__ == "__main__":
    main()
