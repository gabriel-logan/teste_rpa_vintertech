import csv
from decimal import Decimal
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "dados_teste_rpa.csv"
SOURCE_FIELDS = ("id_solicitacao", "data", "area", "descricao", "valor", "status")
FIELD_NAMES = {
    "request_id": "id_solicitacao",
    "date": "data",
    "area": "area",
    "description": "descricao",
    "amount": "valor",
    "status": "status",
}


def row(**changes):
    result = {
        "id_solicitacao": "SOL-100",
        "data": "2026-10-01",
        "area": "Peças",
        "descricao": "Material purchase",
        "valor": "100,50",
        "status": "Aprovado",
    }
    for name, value in changes.items():
        result[FIELD_NAMES[name]] = value
    return result


class AutomationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.source = self.base / "input.csv"
        self.database = self.base / "requests.sqlite"
        self.rejections = self.base / "rejections.csv"
        self.report = self.base / "report.csv"
        self.log = self.base / "execution.log"

    def write_rows(self, rows, fieldnames=SOURCE_FIELDS):
        with self.source.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    def run_batch(self, source=None):
        command = [
            sys.executable,
            "-m",
            "rpa",
            "--input",
            str(source or self.source),
            "--db",
            str(self.database),
            "--rejections",
            str(self.rejections),
            "--report",
            str(self.report),
            "--log",
            str(self.log),
        ]
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)

    def run_successfully(self, source=None):
        result = self.run_batch(source)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def read_csv(self, path):
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return list(csv.DictReader(stream, delimiter=";"))

    def stored_rows(self):
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(record) for record in connection.execute(
                "SELECT * FROM requests ORDER BY request_id"
            )]

    def assert_counts(self, **expected):
        report = self.read_csv(self.report)
        totals = [item for item in report if item["type"] == "TOTAL"]
        self.assertEqual(len(totals), 1)
        for name, value in expected.items():
            self.assertEqual(int(totals[0][name]), value, name)

    def test_sample_csv_has_bom_delimiter_and_challenge_cases(self):
        self.assertTrue(SAMPLE.read_bytes().startswith(b"\xef\xbb\xbf"))
        with SAMPLE.open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.DictReader(stream, delimiter=";"))

        self.assertEqual(len(records), 12)
        self.assertEqual(set(records[0]), set(SOURCE_FIELDS))
        self.assertEqual(records[1]["valor"], "1.250,50")
        self.assertEqual(records[0]["area"], "Peças")

    def test_sample_csv_produces_counts_rejections_and_area_totals(self):
        self.run_successfully(SAMPLE)

        self.assert_counts(
            records_read=12, valid=8, rejected=4, approved=5,
            pending=2, canceled=1,
        )
        self.assertEqual(len(self.stored_rows()), 8)
        self.assertEqual(len(self.read_csv(self.rejections)), 4)

        area_totals = {item["area"]: Decimal(item["approved_total"])
                 for item in self.read_csv(self.report) if item["type"] == "AREA"}
        self.assertEqual(area_totals["Peças"], Decimal("3200.00"))
        self.assertEqual(area_totals["Vendas"], Decimal("270.00"))
        self.assertEqual(area_totals.get("Oficina", Decimal("0")), Decimal("0"))

    def test_rejections_preserve_original_record_and_specific_reason(self):
        self.run_successfully(SAMPLE)
        rejected = self.read_csv(self.rejections)

        self.assertTrue(set(SOURCE_FIELDS).issubset(rejected[0]))
        self.assertIn("reason", rejected[0])
        by_id = {item["id_solicitacao"]: item for item in rejected
                 if item["id_solicitacao"] != "SOL-009"}
        self.assertEqual(by_id["SOL-005"]["valor"], "-50,00")
        self.assertIn("amount", by_id["SOL-005"]["reason"].lower())
        self.assertEqual(by_id["SOL-008"]["valor"], "abc")
        self.assertIn("amount", by_id["SOL-008"]["reason"].lower())
        self.assertEqual(by_id["SOL-010"]["area"], "")
        self.assertIn("area", by_id["SOL-010"]["reason"].lower())
        duplicate = next(item for item in rejected if item["id_solicitacao"] == "SOL-009")
        self.assertIn("duplic", duplicate["reason"].lower())

    def test_brazilian_amount_and_date_are_normalized_without_losing_cents(self):
        self.write_rows([row(amount="1.250,50", date="2026-10-02")])
        self.run_successfully()

        stored = self.stored_rows()[0]
        self.assertEqual(stored["date"], "2026-10-02")
        self.assertEqual(Decimal(str(stored["amount"])), Decimal("1250.50"))
        self.assertEqual(stored["area"], "Peças")
        self.assertEqual(stored["description"], "Material purchase")

    def test_valid_statuses_are_stored_and_only_approved_amounts_are_summed(self):
        self.write_rows([
            row(request_id="A", amount="10,01", status="Aprovado"),
            row(request_id="P", amount="900,00", status="Pendente"),
            row(request_id="C", amount="700,00", status="Cancelado"),
        ])
        self.run_successfully()

        self.assertEqual({item["status"] for item in self.stored_rows()},
                         {"Aprovado", "Pendente", "Cancelado"})
        self.assert_counts(records_read=3, valid=3, rejected=0,
                           approved=1, pending=1, canceled=1)
        area = next(item for item in self.read_csv(self.report) if item["type"] == "AREA")
        self.assertEqual(Decimal(area["approved_total"]), Decimal("10.01"))

    def test_empty_input_produces_zero_counts(self):
        self.write_rows([])
        self.run_successfully()

        self.assertEqual(self.stored_rows(), [])
        self.assertEqual(self.read_csv(self.rejections), [])
        self.assert_counts(records_read=0, valid=0, rejected=0,
                           approved=0, pending=0, canceled=0)

    def test_zero_negative_and_invalid_amounts_do_not_stop_batch(self):
        values = ("0,00", "-0,01", "abc", "", "1.2,30")
        self.write_rows([row(request_id=f"I-{index}", amount=value)
                         for index, value in enumerate(values)] + [row()])
        self.run_successfully()

        self.assert_counts(records_read=6, valid=1, rejected=5, approved=1)
        self.assertEqual([item["request_id"] for item in self.stored_rows()],
                         ["SOL-100"])
        self.assertTrue(all("amount" in item["reason"].lower()
                            for item in self.read_csv(self.rejections)))

    def test_invalid_dates_do_not_stop_batch(self):
        dates = ("2026-02-30", "2026-13-01", "", "yesterday")
        self.write_rows([row(request_id=f"I-{index}", date=value)
                         for index, value in enumerate(dates)] + [row()])
        self.run_successfully()

        self.assert_counts(records_read=5, valid=1, rejected=4)
        self.assertTrue(all("date" in item["reason"].lower()
                            for item in self.read_csv(self.rejections)))

    def test_valid_leap_day_is_accepted(self):
        self.write_rows([row(date="2028-02-29")])
        self.run_successfully()

        self.assert_counts(records_read=1, valid=1, rejected=0)
        self.assertEqual(self.stored_rows()[0]["date"], "2028-02-29")

    def test_each_blank_required_field_is_rejected(self):
        invalid = []
        for index, field in enumerate(SOURCE_FIELDS):
            candidate = row(request_id=f"I-{index}")
            candidate[field] = " "
            invalid.append(candidate)
        self.write_rows(invalid + [row()])
        self.run_successfully()

        self.assert_counts(records_read=7, valid=1, rejected=6)
        rejected = self.read_csv(self.rejections)
        for field, original in zip(SOURCE_FIELDS, invalid):
            match = next(item for item in rejected
                         if item["descricao"] == original["descricao"]
                         and item["id_solicitacao"] == original["id_solicitacao"])
            self.assertEqual(match[field], " ")
            self.assertIn(next(name for name, source in FIELD_NAMES.items() if source == field),
                          match["reason"].lower())

    def test_unknown_status_is_rejected_without_stopping_batch(self):
        self.write_rows([row(status="Under review"), row(request_id="SOL-101")])
        self.run_successfully()

        self.assert_counts(records_read=2, valid=1, rejected=1)
        self.assertIn("status", self.read_csv(self.rejections)[0]["reason"].lower())

    def test_first_valid_occurrence_wins_over_duplicates(self):
        self.write_rows([
            row(amount="10,00"),
            row(amount="20,00"),
            row(amount="30,00"),
        ])
        self.run_successfully()

        self.assert_counts(records_read=3, valid=1, rejected=2, approved=1)
        self.assertEqual(Decimal(str(self.stored_rows()[0]["amount"])), Decimal("10.00"))
        self.assertEqual([item["valor"] for item in self.read_csv(self.rejections)],
                         ["20,00", "30,00"])
        self.assertTrue(all("duplic" in item["reason"].lower()
                            for item in self.read_csv(self.rejections)))

    def test_invalid_occurrence_does_not_reserve_identifier(self):
        self.write_rows([row(amount="abc"), row(amount="10,00")])
        self.run_successfully()

        self.assert_counts(records_read=2, valid=1, rejected=1)
        self.assertEqual(Decimal(str(self.stored_rows()[0]["amount"])), Decimal("10.00"))
        self.assertIn("amount", self.read_csv(self.rejections)[0]["reason"].lower())

    def test_repeated_run_does_not_duplicate_or_change_rows(self):
        self.run_successfully(SAMPLE)
        first_rows = self.stored_rows()

        self.run_successfully(SAMPLE)

        self.assertEqual(self.stored_rows(), first_rows)
        self.assertEqual(len(first_rows), 8)
        self.assert_counts(records_read=12, valid=8, rejected=4)

    def test_successive_batches_keep_existing_rows_and_insert_new_ones(self):
        self.write_rows([row(amount="10,00")])
        self.run_successfully()

        self.write_rows([row(amount="99,00"), row(request_id="SOL-101")])
        self.run_successfully()

        stored = {item["request_id"]: item for item in self.stored_rows()}
        self.assertEqual(set(stored), {"SOL-100", "SOL-101"})
        self.assertEqual(Decimal(str(stored["SOL-100"]["amount"])), Decimal("10.00"))

    def test_areas_receive_independent_approved_totals(self):
        self.write_rows([
            row(request_id="A", area="Peças", amount="0,01"),
            row(request_id="B", area="Peças", amount="0,02"),
            row(request_id="C", area="Vendas", amount="10,00"),
            row(request_id="D", area="Vendas", amount="99,00", status="Pendente"),
        ])
        self.run_successfully()

        area_totals = {item["area"]: Decimal(item["approved_total"])
                 for item in self.read_csv(self.report) if item["type"] == "AREA"}
        self.assertEqual(area_totals, {"Peças": Decimal("0.03"),
                                 "Vendas": Decimal("10.00")})

    def test_database_enforces_unique_request_identifier(self):
        self.write_rows([row()])
        self.run_successfully()

        with sqlite3.connect(self.database) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO requests "
                    "(request_id, date, area, description, amount, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("SOL-100", "2026-10-02", "Peças", "Other", 20, "Aprovado"),
                )

    def test_missing_input_fails_with_clear_error(self):
        result = self.run_batch()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("input.csv", result.stdout + result.stderr +
                      (self.log.read_text() if self.log.exists() else ""))

    def test_missing_required_headers_fail_with_clear_error(self):
        self.write_rows([], fieldnames=("id_solicitacao", "data"))
        result = self.run_batch()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("area", (result.stdout + result.stderr +
                       (self.log.read_text() if self.log.exists() else "")).lower())

    def test_unavailable_database_is_an_infrastructure_error(self):
        self.write_rows([row()])
        self.database.mkdir()
        result = self.run_batch()

        self.assertNotEqual(result.returncode, 0)
        if self.rejections.exists():
            self.assertEqual(self.read_csv(self.rejections), [],
                             "Infrastructure failures are not data rejections")
        self.assertIn("error", (result.stdout + result.stderr +
                       (self.log.read_text() if self.log.exists() else "")).lower())

    def test_logs_record_start_end_counts_and_hide_sensitive_description(self):
        sensitive = "SENSITIVE_DESCRIPTION_123"
        self.write_rows([row(description=sensitive),
                         row(request_id="SOL-101", amount="abc")])
        self.run_successfully()

        content = self.log.read_text(encoding="utf-8").lower()
        self.assertIn("start", content)
        self.assertIn("end", content)
        self.assertIn("records read", content)
        self.assertIn("valid", content)
        self.assertIn("rejected", content)
        self.assertIn("error", content)
        self.assertNotIn(sensitive.lower(), content)


if __name__ == "__main__":
    unittest.main()
