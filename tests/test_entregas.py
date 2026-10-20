"""Critérios verificáveis das entregas não funcionais do desafio."""

from pathlib import Path
import re
import sqlite3
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EntregasTestCase(unittest.TestCase):
    def test_dependencias_sao_declaradas(self):
        self.assertTrue(
            (ROOT / "requirements.txt").is_file() or (ROOT / "pyproject.toml").is_file(),
            "Declare as dependências em requirements.txt ou pyproject.toml",
        )

    def test_script_sql_cria_tabela_com_identificador_unico(self):
        script = ROOT / "schema.sql"
        self.assertTrue(script.is_file(), "Entregue o script de criação schema.sql")

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "teste.sqlite"
            with sqlite3.connect(database) as connection:
                connection.executescript(script.read_text(encoding="utf-8"))
                columns = {item[1] for item in connection.execute(
                    "PRAGMA table_info(solicitacoes)"
                )}
                self.assertTrue({
                    "id_solicitacao", "data", "area", "descricao", "valor", "status"
                }.issubset(columns))

                connection.execute(
                    "INSERT INTO solicitacoes "
                    "(id_solicitacao, data, area, descricao, valor, status) "
                    "VALUES ('A', '2026-10-01', 'Peças', 'Teste', 10, 'Aprovado')"
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO solicitacoes "
                        "(id_solicitacao, data, area, descricao, valor, status) "
                        "VALUES ('A', '2026-10-02', 'Peças', 'Outro', 20, 'Aprovado')"
                    )

    def test_readme_explica_instalacao_execucao_testes_e_decisoes(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for concept in ("instala", "execu", "test", "decis", "python"):
            with self.subTest(concept=concept):
                self.assertIn(concept, readme)

    def test_readme_responde_cinco_perguntas_tecnicas(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for concept in ("idempot", "infraestrutura", "api", "credenciais", "indicadores"):
            with self.subTest(concept=concept):
                self.assertIn(concept, readme)

    def test_readme_descreve_fluxo_atual_e_futuro_com_decisoes(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for concept in ("as-is", "to-be", "manual", "valida", "exce"):
            with self.subTest(concept=concept):
                self.assertIn(concept, readme)
        self.assertRegex(readme, r"(?:```mermaid|bpmn|draw\.io)")

    def test_readme_discute_portal_indisponibilidade_e_agendamento(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        for concept in ("portal", "indispon", "agend"):
            with self.subTest(concept=concept):
                self.assertIn(concept, readme)

        discussion = re.search(r"(?im)^#{1,3}.*discussão técnica.*$", readme)
        self.assertIsNotNone(discussion, "Inclua seção de discussão técnica no README")
        section = readme[discussion.end():].split("\n#", 1)[0]
        self.assertLessEqual(len(section.split()), 500, "Discussão técnica: até uma página")

    def test_readme_informa_uso_de_ia(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        self.assertRegex(readme, r"(?:inteligência artificial|\bia\b)")
        self.assertIn("teste", readme)

    def test_evidencia_de_execucao_esta_versionada(self):
        folder = ROOT / "evidencias"
        files = [path for path in folder.glob("*")
                 if path.suffix.lower() in {".txt", ".log", ".png", ".jpg", ".jpeg"}]
        self.assertTrue(files, "Inclua captura de tela ou log em evidencias/")

        for evidence in files:
            if evidence.suffix.lower() in {".txt", ".log"}:
                content = evidence.read_text(encoding="utf-8").lower()
                self.assertIn("início", content)
                self.assertIn("fim", content)
                self.assertIn("lidos", content)


if __name__ == "__main__":
    unittest.main()
