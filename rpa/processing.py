import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sqlite3


SOURCE_FIELDS = ("id_solicitacao", "data", "area", "descricao", "valor", "status")
FIELD_NAMES = {
    "id_solicitacao": "request_id",
    "data": "date",
    "area": "area",
    "descricao": "description",
    "valor": "amount",
    "status": "status",
}
REPORT_FIELDS = (
    "type", "area", "records_read", "valid", "rejected", "approved", "pending",
    "canceled", "approved_total",
)
VALID_STATUSES = {"Aprovado", "Pendente", "Cancelado"}
SCHEMA = Path(__file__).resolve().parents[1] / "schema.sql"


def parse_amount(value):
    if not re.fullmatch(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d{1,2})?", value):
        raise ValueError("amount has an invalid Brazilian monetary format")

    try:
        amount = Decimal(value.replace(".", "").replace(",", ".")).quantize(
            Decimal("0.01")
        )
    except InvalidOperation as error:
        raise ValueError("amount is invalid") from error

    if amount <= 0:
        raise ValueError("amount must be greater than zero")

    return amount


def validate_row(original):
    for field in SOURCE_FIELDS:
        value = original.get(field)
        if value is None or not value.strip():
            raise ValueError(f"{FIELD_NAMES[field]} is required")

    if None in original:
        raise ValueError("row has extra columns")

    request = {FIELD_NAMES[field]: original[field].strip() for field in SOURCE_FIELDS}

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", request["date"]):
        raise ValueError("date is invalid")

    try:
        request["date"] = date.fromisoformat(request["date"]).isoformat()
    except ValueError as error:
        raise ValueError("date is invalid") from error

    request["amount"] = parse_amount(request["amount"])

    if request["status"] not in VALID_STATUSES:
        raise ValueError("status is invalid")

    return request


def write_rejections(path, rejected_rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(*SOURCE_FIELDS, "reason"), delimiter=";")
        writer.writeheader()
        for original, reason in rejected_rows:
            writer.writerow({**{field: original.get(field) for field in SOURCE_FIELDS},
                             "reason": reason})


def write_report(path, counts, area_totals):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REPORT_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerow({"type": "TOTAL", "area": "", **counts,
                         "approved_total": f"{sum(area_totals.values(), Decimal('0')):.2f}"})

        for area in sorted(area_totals):
            writer.writerow({"type": "AREA", "area": area,
                             "approved_total": f"{area_totals[area]:.2f}"})


def process_batch(source, database, rejections, report, logger):
    counts = {
        "records_read": 0,
        "valid": 0,
        "rejected": 0,
        "approved": 0,
        "pending": 0,
        "canceled": 0,
    }
    area_totals = {}
    rejected_rows = []
    seen_ids = set()

    database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database) as connection:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))

        with source.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter=";")
            missing = set(SOURCE_FIELDS) - set(reader.fieldnames or ())
            if missing:
                raise ValueError(f"Missing required headers: {', '.join(sorted(missing))}")

            for original in reader:
                counts["records_read"] += 1

                try:
                    request = validate_row(original)
                    if request["request_id"] in seen_ids:
                        raise ValueError("duplicate request_id")
                except ValueError as error:
                    reason = str(error)
                    rejected_rows.append((original, reason))
                    counts["rejected"] += 1
                    logger.warning("Data error on row %s: %s", counts["records_read"], reason)
                    continue

                seen_ids.add(request["request_id"])
                counts["valid"] += 1
                status_name = {
                    "Aprovado": "approved", "Pendente": "pending", "Cancelado": "canceled"
                }[request["status"]]
                counts[status_name] += 1

                area = request["area"]
                area_totals.setdefault(area, Decimal("0"))
                if request["status"] == "Aprovado":
                    area_totals[area] += request["amount"]

                connection.execute(
                    "INSERT INTO requests (request_id, date, area, description, amount, status) "
                    "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(request_id) DO NOTHING",
                    (request["request_id"], request["date"], area, request["description"],
                     f"{request['amount']:.2f}", request["status"]),
                )

        write_rejections(rejections, rejected_rows)
        write_report(report, counts, area_totals)

    logger.info(
        "Run end: records read=%s valid=%s rejected=%s approved=%s pending=%s canceled=%s",
        *(counts[name] for name in counts),
    )
