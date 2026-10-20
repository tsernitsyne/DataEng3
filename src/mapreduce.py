import argparse
import csv
import io
import json
from collections import Counter, deque
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations

from common import BUCKET, FIELDS, RAW_KEY, get_vacancy, is_php_vacancy, s3_client, save_json


class S3Stream(io.RawIOBase):
    def __init__(self, body):
        self.body = body

    def readable(self):
        return True

    def readinto(self, buffer):
        data = self.body.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)

    def close(self):
        self.body.close()
        super().close()


def map_chunk(chunk):
    counts = {1: Counter(), 2: Counter(), 3: Counter()}
    vacancies = []

    for row in chunk:
        if not is_php_vacancy(row):
            continue
        vacancy = get_vacancy(row)
        vacancies.append(vacancy)
        for size in (1, 2, 3):
            counts[size].update(combinations(vacancy["skills"], size))

    return counts, vacancies


def count_skills():
    s3 = s3_client()
    response = s3.get_object(Bucket=BUCKET, Key=RAW_KEY)
    stream = io.TextIOWrapper(
        io.BufferedReader(S3Stream(response["Body"])),
        encoding="utf-8-sig",
        newline="",
    )
    csv.field_size_limit(20_000_000)
    reader = csv.DictReader(stream)

    totals = {1: Counter(), 2: Counter(), 3: Counter()}
    vacancies = []
    pending = deque()
    chunk = []
    input_rows = 0
    chunk_count = 0

    def reduce_one():
        chunk_counts, chunk_vacancies = pending.popleft().result()
        for size in (1, 2, 3):
            totals[size].update(chunk_counts[size])
        vacancies.extend(chunk_vacancies)

    try:
        with ProcessPoolExecutor(max_workers=4) as pool:
            for row in reader:
                input_rows += 1
                chunk.append({name: row[name] for name in FIELDS})
                if len(chunk) == 1000:
                    pending.append(pool.submit(map_chunk, chunk))
                    chunk = []
                    chunk_count += 1
                    if len(pending) == 8:
                        reduce_one()

            if chunk:
                pending.append(pool.submit(map_chunk, chunk))
                chunk_count += 1

            while pending:
                reduce_one()
    finally:
        stream.close()

    vacancies.sort(key=lambda vacancy: vacancy["id"])
    records = []
    for size in (1, 2, 3):
        for skills, frequency in sorted(totals[size].items()):
            records.append({
                "size": size,
                "skills": list(skills),
                "frequency": frequency,
            })

    return {
        "input_rows": input_rows,
        "selected_rows": len(vacancies),
        "chunks": chunk_count,
        "bytes_from_s3": response["ContentLength"],
        "counts": records,
        "vacancies": vacancies,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    result = count_skills()
    save_json(args.out, result)
    print(json.dumps({
        "method": "MapReduce",
        "input_rows": result["input_rows"],
        "selected_rows": result["selected_rows"],
        "chunks": result["chunks"],
        "different_sets": len(result["counts"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
