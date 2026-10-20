from pathlib import Path
import re
import sqlite3
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeliverablesTestCase(unittest.TestCase):
    def test_dependencies_are_declared(self):
        self.assertTrue(
            (ROOT / "requirements.txt").is_file() or (ROOT / "pyproject.toml").is_file(),
            "Declare dependencies in requirements.txt or pyproject.toml",
        )

    def test_sql_script_creates_table_with_unique_identifier(self):
        script = ROOT / "schema.sql"
        self.assertTrue(script.is_file(), "Provide the schema.sql creation script")

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "test.sqlite"
            with sqlite3.connect(database) as connection:
                connection.executescript(script.read_text(encoding="utf-8"))
                columns = {item[1] for item in connection.execute(
                    "PRAGMA table_info(requests)"
                )}
                self.assertTrue({
                    "request_id", "date", "area", "description", "amount", "status"
                }.issubset(columns))

                connection.execute(
                    "INSERT INTO requests "
                    "(request_id, date, area, description, amount, status) "
                    "VALUES ('A', '2026-10-01', 'Peças', 'Test', 10, 'Aprovado')"
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO requests "
                        "(request_id, date, area, description, amount, status) "
                        "VALUES ('A', '2026-10-02', 'Peças', 'Other', 20, 'Aprovado')"
                    )

    def test_readme_explains_installation_execution_tests_and_decisions(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for concept in ("instal", "execut", "test", "regras", "python"):
            with self.subTest(concept=concept):
                self.assertIn(concept, readme)

    def test_readme_answers_five_technical_questions(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for concept in ("idempot", "infraestrutura", "api", "credenciais", "indicadores"):
            with self.subTest(concept=concept):
                self.assertIn(concept, readme)

    def test_readme_describes_current_and_future_flows_with_decisions(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for concept in ("as-is", "to-be", "manual", "valid", "erro"):
            with self.subTest(concept=concept):
                self.assertIn(concept, readme)
        self.assertRegex(readme, r"(?:```mermaid|bpmn|draw\.io)")

    def test_readme_discusses_portal_outages_and_scheduling(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for concept in ("portal", "indisponibilidade", "agendador"):
            with self.subTest(concept=concept):
                self.assertIn(concept, readme)

        discussion = re.search(r"(?im)^#{1,3}.*discussão técnica.*$", readme)
        self.assertIsNotNone(discussion, "Include a technical discussion section in README")
        section = readme[discussion.end():].split("\n#", 1)[0]
        self.assertLessEqual(len(section.split()), 500, "Technical discussion must fit on one page")

    def test_readme_discloses_ai_usage(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        self.assertRegex(readme, r"(?:inteligência artificial|\bia\b)")
        self.assertIn("test", readme)

    def test_execution_evidence_is_available(self):
        folder = ROOT / "evidence"
        files = [path for path in folder.glob("*")
                 if path.suffix.lower() in {".txt", ".log", ".png", ".jpg", ".jpeg"}]
        self.assertTrue(files, "Include a screenshot or log in evidence/")

        for evidence in files:
            if evidence.suffix.lower() in {".txt", ".log"}:
                content = evidence.read_text(encoding="utf-8").lower()
                self.assertIn("start", content)
                self.assertIn("end", content)
                self.assertIn("records read", content)


if __name__ == "__main__":
    unittest.main()
