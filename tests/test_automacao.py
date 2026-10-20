"""Contrato de aceitação para o desafio RPA (fase vermelha do TDD).

Interface acordada para a implementação: ``python -m rpa --input ARQUIVO
--db BANCO --rejections CSV --report CSV --log LOG``. Os caminhos de saída
são arquivos, e suas pastas já existem. Cada execução relata apenas o lote
atual; o banco conserva solicitações válidas de execuções anteriores.
"""

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
FIELDS = ("id_solicitacao", "data", "area", "descricao", "valor", "status")


def row(**changes):
    result = {
        "id_solicitacao": "SOL-100",
        "data": "2026-10-01",
        "area": "Peças",
        "descricao": "Compra de material",
        "valor": "100,50",
        "status": "Aprovado",
    }
    result.update(changes)
    return result


class AutomacaoTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.source = self.base / "entrada.csv"
        self.database = self.base / "solicitacoes.sqlite"
        self.rejections = self.base / "rejeicoes.csv"
        self.report = self.base / "relatorio.csv"
        self.log = self.base / "execucao.log"

    def write_rows(self, rows, fieldnames=FIELDS):
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
                "SELECT * FROM solicitacoes ORDER BY id_solicitacao"
            )]

    def assert_counts(self, **expected):
        report = self.read_csv(self.report)
        totals = [item for item in report if item["tipo"] == "TOTAL"]
        self.assertEqual(len(totals), 1)
        for name, value in expected.items():
            self.assertEqual(int(totals[0][name]), value, name)

    def test_csv_fornecido_tem_bom_delimitador_e_casos_do_desafio(self):
        self.assertTrue(SAMPLE.read_bytes().startswith(b"\xef\xbb\xbf"))
        with SAMPLE.open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.DictReader(stream, delimiter=";"))

        self.assertEqual(len(records), 12)
        self.assertEqual(set(records[0]), set(FIELDS))
        self.assertEqual(records[1]["valor"], "1.250,50")
        self.assertEqual(records[0]["area"], "Peças")

    def test_csv_fornecido_gera_contagens_rejeicoes_e_totais_por_area(self):
        self.run_successfully(SAMPLE)

        self.assert_counts(
            lidos=12, validos=8, rejeitados=4, aprovados=5,
            pendentes=2, cancelados=1,
        )
        self.assertEqual(len(self.stored_rows()), 8)
        self.assertEqual(len(self.read_csv(self.rejections)), 4)

        areas = {item["area"]: Decimal(item["total_aprovado"])
                 for item in self.read_csv(self.report) if item["tipo"] == "AREA"}
        self.assertEqual(areas["Peças"], Decimal("3200.00"))
        self.assertEqual(areas["Vendas"], Decimal("270.00"))
        self.assertEqual(areas.get("Oficina", Decimal("0")), Decimal("0"))

    def test_rejeicoes_preservam_registro_original_e_motivo_especifico(self):
        self.run_successfully(SAMPLE)
        rejected = self.read_csv(self.rejections)

        self.assertTrue(set(FIELDS).issubset(rejected[0]))
        self.assertIn("motivo", rejected[0])
        by_id = {item["id_solicitacao"]: item for item in rejected
                 if item["id_solicitacao"] != "SOL-009"}
        self.assertEqual(by_id["SOL-005"]["valor"], "-50,00")
        self.assertIn("valor", by_id["SOL-005"]["motivo"].lower())
        self.assertEqual(by_id["SOL-008"]["valor"], "abc")
        self.assertIn("valor", by_id["SOL-008"]["motivo"].lower())
        self.assertEqual(by_id["SOL-010"]["area"], "")
        self.assertIn("area", by_id["SOL-010"]["motivo"].lower())
        duplicate = next(item for item in rejected if item["id_solicitacao"] == "SOL-009")
        self.assertIn("duplic", duplicate["motivo"].lower())

    def test_valor_brasileiro_e_data_sao_normalizados_sem_perda_de_centavos(self):
        self.write_rows([row(valor="1.250,50", data="2026-10-02")])
        self.run_successfully()

        stored = self.stored_rows()[0]
        self.assertEqual(stored["data"], "2026-10-02")
        self.assertEqual(Decimal(str(stored["valor"])), Decimal("1250.50"))
        self.assertEqual(stored["area"], "Peças")
        self.assertEqual(stored["descricao"], "Compra de material")

    def test_status_validos_sao_persistidos_e_so_aprovado_soma(self):
        self.write_rows([
            row(id_solicitacao="A", valor="10,01", status="Aprovado"),
            row(id_solicitacao="P", valor="900,00", status="Pendente"),
            row(id_solicitacao="C", valor="700,00", status="Cancelado"),
        ])
        self.run_successfully()

        self.assertEqual({item["status"] for item in self.stored_rows()},
                         {"Aprovado", "Pendente", "Cancelado"})
        self.assert_counts(lidos=3, validos=3, rejeitados=0,
                           aprovados=1, pendentes=1, cancelados=1)
        area = next(item for item in self.read_csv(self.report) if item["tipo"] == "AREA")
        self.assertEqual(Decimal(area["total_aprovado"]), Decimal("10.01"))

    def test_arquivo_sem_registros_gera_saidas_com_contagens_zero(self):
        self.write_rows([])
        self.run_successfully()

        self.assertEqual(self.stored_rows(), [])
        self.assertEqual(self.read_csv(self.rejections), [])
        self.assert_counts(lidos=0, validos=0, rejeitados=0,
                           aprovados=0, pendentes=0, cancelados=0)

    def test_valores_nulos_negativos_e_invalidos_nao_interrompem_lote(self):
        values = ("0,00", "-0,01", "abc", "", "1.2,30")
        self.write_rows([row(id_solicitacao=f"I-{index}", valor=value)
                         for index, value in enumerate(values)] + [row()])
        self.run_successfully()

        self.assert_counts(lidos=6, validos=1, rejeitados=5, aprovados=1)
        self.assertEqual([item["id_solicitacao"] for item in self.stored_rows()],
                         ["SOL-100"])
        self.assertTrue(all("valor" in item["motivo"].lower()
                            for item in self.read_csv(self.rejections)))

    def test_datas_invalidas_nao_interrompem_lote(self):
        dates = ("2026-02-30", "2026-13-01", "", "ontem")
        self.write_rows([row(id_solicitacao=f"I-{index}", data=value)
                         for index, value in enumerate(dates)] + [row()])
        self.run_successfully()

        self.assert_counts(lidos=5, validos=1, rejeitados=4)
        self.assertTrue(all("data" in item["motivo"].lower()
                            for item in self.read_csv(self.rejections)))

    def test_data_bissexta_valida_e_aceita(self):
        self.write_rows([row(data="2028-02-29")])
        self.run_successfully()

        self.assert_counts(lidos=1, validos=1, rejeitados=0)
        self.assertEqual(self.stored_rows()[0]["data"], "2028-02-29")

    def test_cada_campo_obrigatorio_vazio_e_rejeitado(self):
        invalid = []
        for index, field in enumerate(FIELDS):
            candidate = row(id_solicitacao=f"I-{index}")
            candidate[field] = " "
            invalid.append(candidate)
        self.write_rows(invalid + [row()])
        self.run_successfully()

        self.assert_counts(lidos=7, validos=1, rejeitados=6)
        rejected = self.read_csv(self.rejections)
        for field, original in zip(FIELDS, invalid):
            match = next(item for item in rejected
                         if item["descricao"] == original["descricao"]
                         and item["id_solicitacao"] == original["id_solicitacao"])
            self.assertEqual(match[field], " ")
            self.assertIn(field, match["motivo"].lower())

    def test_status_desconhecido_e_rejeitado_sem_parar_lote(self):
        self.write_rows([row(status="Em análise"), row(id_solicitacao="SOL-101")])
        self.run_successfully()

        self.assert_counts(lidos=2, validos=1, rejeitados=1)
        self.assertIn("status", self.read_csv(self.rejections)[0]["motivo"].lower())

    def test_primeira_ocorrencia_valida_prevalece_sobre_duplicadas(self):
        self.write_rows([
            row(valor="10,00"),
            row(valor="20,00"),
            row(valor="30,00"),
        ])
        self.run_successfully()

        self.assert_counts(lidos=3, validos=1, rejeitados=2, aprovados=1)
        self.assertEqual(Decimal(str(self.stored_rows()[0]["valor"])), Decimal("10.00"))
        self.assertEqual([item["valor"] for item in self.read_csv(self.rejections)],
                         ["20,00", "30,00"])
        self.assertTrue(all("duplic" in item["motivo"].lower()
                            for item in self.read_csv(self.rejections)))

    def test_ocorrencia_invalida_nao_reserva_identificador(self):
        self.write_rows([row(valor="abc"), row(valor="10,00")])
        self.run_successfully()

        self.assert_counts(lidos=2, validos=1, rejeitados=1)
        self.assertEqual(Decimal(str(self.stored_rows()[0]["valor"])), Decimal("10.00"))
        self.assertIn("valor", self.read_csv(self.rejections)[0]["motivo"].lower())

    def test_reexecucao_do_mesmo_arquivo_nao_duplica_nem_altera_linhas(self):
        self.run_successfully(SAMPLE)
        first_rows = self.stored_rows()

        self.run_successfully(SAMPLE)

        self.assertEqual(self.stored_rows(), first_rows)
        self.assertEqual(len(first_rows), 8)
        self.assert_counts(lidos=12, validos=8, rejeitados=4)

    def test_lotes_sucessivos_preservam_dados_existentes_e_inserem_novos(self):
        self.write_rows([row(valor="10,00")])
        self.run_successfully()

        self.write_rows([row(valor="99,00"), row(id_solicitacao="SOL-101")])
        self.run_successfully()

        stored = {item["id_solicitacao"]: item for item in self.stored_rows()}
        self.assertEqual(set(stored), {"SOL-100", "SOL-101"})
        self.assertEqual(Decimal(str(stored["SOL-100"]["valor"])), Decimal("10.00"))

    def test_areas_diferentes_recebem_somas_independentes(self):
        self.write_rows([
            row(id_solicitacao="A", area="Peças", valor="0,01"),
            row(id_solicitacao="B", area="Peças", valor="0,02"),
            row(id_solicitacao="C", area="Vendas", valor="10,00"),
            row(id_solicitacao="D", area="Vendas", valor="99,00", status="Pendente"),
        ])
        self.run_successfully()

        areas = {item["area"]: Decimal(item["total_aprovado"])
                 for item in self.read_csv(self.report) if item["tipo"] == "AREA"}
        self.assertEqual(areas, {"Peças": Decimal("0.03"),
                                 "Vendas": Decimal("10.00")})

    def test_banco_tem_chave_unica_para_id_solicitacao(self):
        self.write_rows([row()])
        self.run_successfully()

        with sqlite3.connect(self.database) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO solicitacoes "
                    "(id_solicitacao, data, area, descricao, valor, status) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    ("SOL-100", "2026-10-02", "Peças", "Outra", 20, "Aprovado"),
                )

    def test_arquivo_ausente_falha_com_erro_claro(self):
        result = self.run_batch()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("entrada.csv", result.stdout + result.stderr +
                      (self.log.read_text() if self.log.exists() else ""))

    def test_cabecalho_sem_campos_obrigatorios_falha_com_erro_claro(self):
        self.write_rows([], fieldnames=("id_solicitacao", "data"))
        result = self.run_batch()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("area", (result.stdout + result.stderr +
                       (self.log.read_text() if self.log.exists() else "")).lower())

    def test_banco_indisponivel_falha_como_erro_de_infraestrutura(self):
        self.write_rows([row()])
        self.database.mkdir()
        result = self.run_batch()

        self.assertNotEqual(result.returncode, 0)
        if self.rejections.exists():
            self.assertEqual(self.read_csv(self.rejections), [],
                             "Falha de infraestrutura não é rejeição de dado")
        self.assertIn("erro", (result.stdout + result.stderr +
                       (self.log.read_text() if self.log.exists() else "")).lower())

    def test_logs_registram_inicio_fim_contagens_sem_descricao_sensivel(self):
        sensitive = "DESCRICAO_SIGILOSA_123"
        self.write_rows([row(descricao=sensitive),
                         row(id_solicitacao="SOL-101", valor="abc")])
        self.run_successfully()

        content = self.log.read_text(encoding="utf-8").lower()
        self.assertIn("início", content)
        self.assertIn("fim", content)
        self.assertIn("lidos", content)
        self.assertIn("válidos", content)
        self.assertIn("rejeitados", content)
        self.assertIn("erro", content)
        self.assertNotIn(sensitive.lower(), content)


if __name__ == "__main__":
    unittest.main()
