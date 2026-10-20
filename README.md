# Automação de solicitações — desafio Vintertech

[![CI e entrega](https://github.com/gabriel-logan/teste_rpa_vintertech/actions/workflows/ci.yml/badge.svg)](https://github.com/gabriel-logan/teste_rpa_vintertech/actions/workflows/ci.yml)

Lê o CSV fornecido, valida as solicitações, salva as válidas em SQLite e gera rejeições, relatório e log. Usa apenas a biblioteca padrão do Python; não precisa de credenciais nem de acesso a sistemas externos.

## Como executar

Instale Python **3.10 ou superior**. No terminal, execute:

```bash
git clone https://github.com/gabriel-logan/teste_rpa_vintertech.git
cd teste_rpa_vintertech
python3 -m rpa
```

No Windows, substitua `python3` por `py` nos comandos. Execute dentro da pasta do repositório. Não é necessário instalar pacotes (`pyproject.toml` declara as dependências). Para usar outro CSV: `python3 -m rpa --input caminho/arquivo.csv`. Veja os demais caminhos com `python3 -m rpa --help`.

O arquivo fornecido deve produzir **12 lidos, 8 válidos, 4 rejeitados, 5 aprovados, 2 pendentes e 1 cancelado**, com total aprovado de **3.470,00**. Os arquivos aparecem em `output/`:

| Arquivo | Conteúdo |
|---|---|
| `requests.sqlite` | Solicitações válidas; `schema.sql` define a tabela. |
| `rejections.csv` | Registro original e motivo (`reason`). |
| `report.csv` | Contagens do lote e soma aprovada por área. |
| `execution.log` | Início, fim, contagens e erros, sem descrições dos registros. |

Exemplos gerados com o CSV fornecido estão em `evidence/`.

## Como testar

```bash
python3 -m unittest discover -s tests -v
```

Os testes usam arquivos temporários. Para conferir a idempotência manualmente, rode `python3 -m rpa` duas vezes: o banco continuará com **8** solicitações. O relatório sempre descreve o lote executado; dados já salvos não são sobrescritos.

O GitHub Actions executa os testes automaticamente em cada push e pull request. Após um push em `main` bem-sucedido, o pacote fica disponível na aba **Actions**, em **Artifacts** da execução, por 14 dias.

## Regras e possíveis erros

O CSV precisa ter codificação UTF-8 (BOM aceito), separador `;` e os campos `id_solicitacao`, `data`, `area`, `descricao`, `valor` e `status`. Data deve ser `AAAA-MM-DD`; valor deve usar formato brasileiro, como `1.250,50`, e ser maior que zero. Os status aceitos são `Aprovado`, `Pendente` e `Cancelado`. Só aprovados entram na soma; todos os status válidos são salvos. Apenas a primeira ocorrência válida de cada ID é mantida. Valores monetários são tratados com `Decimal` para preservar centavos.

Linhas com dados incorretos vão para `rejections.csv` e o processamento continua. Arquivo ausente, cabeçalho incompleto, codificação inválida ou falha no banco/saída encerram a execução com erro no terminal e no log, quando possível. Se o comando Python não for reconhecido, confira a instalação. Se houver erro de permissão, execute em uma pasta onde seja possível criar `output/`.

## Fluxo do processo

**AS-IS:** recebimento do CSV, conferência manual, lançamento dos pedidos e montagem do relatório.

**TO-BE:** leitura automática, validação, registro das rejeições, persistência sem duplicação e relatório; exceções de infraestrutura encerram a execução.

```mermaid
flowchart TD
    A[Receber CSV] --> B{Arquivo e cabeçalho válidos?}
    B -- Não --> X[Registrar erro e encerrar]
    B -- Sim --> C[Validar linha]
    C --> D{Dados válidos e ID novo?}
    D -- Não --> E[Registrar rejeição e motivo]
    D -- Sim --> F[Salvar no SQLite]
    E --> G{Há mais linhas?}
    F --> G
    G -- Sim --> C
    G -- Não --> H[Gerar relatório e log]
    H --> I{Falha de infraestrutura?}
    I -- Sim --> X
    I -- Não --> J[Concluir]
```

## Perguntas técnicas

1. **Como evitar lançamento duplicado?** IDs repetidos no lote são identificados; a chave única no SQLite garante idempotência entre execuções.
2. **Dado ou infraestrutura?** Dado inválido rejeita só a linha. Falha de arquivo, codificação ou banco encerra o lote com erro.
3. **API ou interface?** Prefiro API documentada quando disponível; uso RPA pela interface se o processo depender dela.
4. **Credenciais?** Usaria um gerenciador de segredos, acesso mínimo e rotação, nunca código ou logs.
5. **Indicadores?** Sucesso, duração, volume, rejeições, duplicados, valores por área e tempo desde a última execução.

## Discussão técnica

Para buscar dados em um portal, verificaria primeiro uma API autorizada; sem API, usaria automação de navegador para obter o lote e reutilizaria esta validação. Em indisponibilidade, registraria a falha, tentaria novamente com espera crescente e alertaria após tentativas limitadas. A chave única permite reprocessar com segurança. Um agendador, como cron, executaria o comando periodicamente, com alerta por código de saída e controle para evitar execuções simultâneas.

## Uso de IA

IA auxiliou na elaboração dos testes, do código e deste README. O resultado foi conferido com os testes automatizados e com a execução do CSV fornecido.
