import json
import math
import os
import re
from pathlib import Path

import boto3
from botocore.config import Config


ROOT = Path(__file__).resolve().parents[1]
BUCKET = "hh-lake"
RAW_KEY = "raw/it_vacancies_2024.csv"
PHP_IN_TITLE = re.compile(r"(?<!\w)php(?!\w)", re.IGNORECASE)
FIELDS = (
    "source",
    "vacancy_id",
    "name",
    "role",
    "area",
    "key_skills",
    "salary_from",
    "salary_to",
    "currency",
    "gross",
)


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT", "http://127.0.0.1:9110"),
        region_name="us-east-1",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def is_php_vacancy(row):
    role = (row.get("role") or "").strip().lower()
    title = row.get("name") or ""
    return role == "программист, разработчик" and PHP_IN_TITLE.search(title) is not None


def get_skills(text):
    parts = (text or "").split(";")
    return sorted({part.strip().lower() for part in parts if part.strip()})


def get_salary(row):
    if (row.get("currency") or "").upper() not in ("RUR", "RUB"):
        return None
    if (row.get("gross") or "").lower() != "false":
        return None

    def positive_number(text):
        try:
            number = float(text)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) and number > 0 else None

    lower = positive_number(row.get("salary_from"))
    upper = positive_number(row.get("salary_to"))
    if lower is not None and upper is not None:
        if lower > upper:
            return None
        return (lower + upper) / 2
    return lower if lower is not None else upper


def get_vacancy(row):
    return {
        "id": row["source"] + ":" + row["vacancy_id"],
        "area": row.get("area") or "",
        "skills": get_skills(row.get("key_skills")),
        "salary": get_salary(row),
    }


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
