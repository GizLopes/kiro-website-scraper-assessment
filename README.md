# Websites Assessment — LLM-Powered Product Scraper

Pipeline de extração de dados de produtos que combina um agente LLM com controle de browser para coletar, mapear e exportar catálogos de 7 sites de tecnologia educacional que usa impressoras 3D.

---

## Visão geral

```
Prompt Builder  →  Runner (LLM/browser)  →  Schema Mapper  →  Output Builder
     ↓                     ↓                      ↓                  ↓
Carrega o YAML       Envia o prompt         Mapeia os dicts      Grava JSON,
do site e monta      ao agente e           brutos p/ Pydantic    CSV e HTML
o prompt final       recebe os dados        com confidence        por site
```

O pipeline é acionado por `scraper/main.py` e percorre três estágios para cada site:

1. **Stage 1 — Runner**: envia o prompt de extração ao agente LLM (mock, BrowserUse ou AgentCore/Bedrock) e recebe uma lista de dicts brutos.
2. **Stage 2 — Mapper**: mapeia cada dict ao schema Pydantic do site, anotando cada campo com um nível de confiança (`high`, `low`, `missing`).
3. **Stage 3 — Output**: serializa os produtos mapeados em `.json`, `.csv` e `_report.html` dentro de `scraper/outputs/`.

---

## Sites cobertos

| ID | Site | URL |
|----|------|-----|
| `active_floor` | ActiveFloor | https://activefloor.com |
| `smart_tech` | SMART Technologies | https://smarttech.com |
| `play_lu` | Play-Lu | https://play-lu.com |
| `ultimaker` | Ultimaker | https://ultimaker.com |
| `makerbot` | MakerBot | https://makerbot.com |
| `bambulab` | Bambu Lab | https://bambulab.com/en-us |
| `formlabs` | Formlabs | https://formlabs.com/store |

---

## Estrutura do projeto

```
websites-assessment/
└── scraper/                           # Pacote principal
    ├── main.py                        # Entry point da CLI
    ├── descriptors/                   # Configuração por site (YAML)
    │   ├── bambulab.yaml
    │   ├── formlabs.yaml
    │   └── ... (7 arquivos)
    ├── schemas/
    │   ├── core.py                   # ProductBase + FieldConfidence
    │   └── sites.py                  # Schemas por site + SITE_SCHEMA_MAP
    ├── prompts/
    │   └── prompt_builder.py         # Carrega YAML e monta o prompt final
    ├── runner/
    │   ├── base_runner.py            # ABC BrowserAgentRunner + RunnerResult
    │   ├── mock_runner.py            # Runner sem browser (usa fixtures JSON)
    │   ├── browseruse_runner.py      # Runner com browser-use + Bedrock
    │   ├── agentcore_runner.py       # Runner com Bedrock Converse API
    │   └── fixtures/                 # Dados de teste para os 7 sites
    ├── mapper/
    │   └── schema_mapper.py          # Mapeamento fuzzy dict → Pydantic
    ├── output/
    │   └── output_builder.py         # Serialização JSON / CSV / HTML
    ├── pipeline/
    │   └── pipeline.py               # Orquestra os 3 estágios
    ├── outputs/                      # Arquivos gerados (ignorados pelo git)
    └── tests/
        ├── test_pipeline.py           # Pytest suite — pipeline (136 testes)
        ├── test_runner.py             # Pytest suite — runners
        ├── test_mapper.py             # Pytest suite — schema mapper
        ├── test_output_builder.py     # Pytest suite — output builder
        ├── test_prompt_builder.py     # Pytest suite — prompt builder
        ├── test_schemas.py            # Pytest suite — schemas Pydantic
        ├── run_pipeline_check.py      # Smoke script — pipeline (sem pytest)
        ├── run_runner_check.py        # Smoke script — runners
        ├── run_mapper_check.py        # Smoke script — mapper
        ├── run_output_builder_check.py
        └── run_prompt_builder_check.py
```

---

## Como executar

### Pré-requisitos

```powershell
# Instalar dependências base (Pydantic, PyYAML, etc.)
pip install pydantic pyyaml
```

### Executar com MockRunner (padrão — sem browser, sem API)

```powershell
# Todos os 7 sites
python scraper/main.py

# Um site específico
python scraper/main.py --sites bambulab

# Múltiplos sites
python scraper/main.py --sites bambulab formlabs ultimaker

# Sem gravar arquivos (dry-run)
python scraper/main.py --dry-run

# Diretório de saída customizado
python scraper/main.py --output-dir C:\tmp\outputs
```

O MockRunner serve dados das fixtures em `scraper/runner/fixtures/` sem abrir nenhum browser. Útil para desenvolvimento, testes e CI.

### Executar com BrowserUse Runner (browser real + Bedrock)

```powershell
pip install "browser-use[aws]" boto3
playwright install chromium

$env:AWS_PROFILE        = "meu-perfil"
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:BEDROCK_MODEL_ID   = "anthropic.claude-sonnet-4-6"

python scraper/main.py --runner browseruse --sites bambulab
```

O BrowserUseRunner abre um Chromium real controlado pelo LLM. O agente navega no site, extrai os dados e retorna um JSON array.

### Executar com AgentCore Runner (Bedrock Converse API, sem browser)

```powershell
pip install boto3

$env:AWS_ACCESS_KEY_ID     = "..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_DEFAULT_REGION    = "us-east-1"

python scraper/main.py --runner agentcore --sites bambulab
```

O AgentCoreRunner chama a Bedrock Converse API diretamente (sem browser local). Envia o prompt de extração e analisa o JSON retornado pelo modelo.

### Opções completas da CLI

```
python scraper/main.py --help

  --sites SITE_ID [...]    Sites a processar (padrão: todos os 7)
  --runner {mock,browseruse,agentcore}
  --output-dir PATH        Diretório de saída (padrão: scraper/outputs/)
  --dry-run                Pula Stage 3 (não grava arquivos)
  --quiet                  Suprime linhas de progresso por site
  --llm-provider STR       Provedor LLM para browseruse: 'bedrock'
  --model STR              Model ID (browseruse / agentcore)
  --headless / --no-headless  Modo headless do browser (browseruse)
```

---

## Arquivos de saída

Para cada site, três arquivos são gerados em `scraper/outputs/`:

| Arquivo | Conteúdo |
|---------|----------|
| `07_bambulab_products.json` | Array JSON com todos os campos + metadado `_field_confidence` |
| `07_bambulab_products.csv` | Tabela flat; campos inferidos marcados com `*`, ausentes como `N/A` |
| `07_bambulab_products_report.html` | Tabela HTML com células coloridas por confiança |

**Escala de cores do HTML:**

| Cor | Significado |
|-----|-------------|
| 🟢 Verde | Campo extraído com correspondência exata (`high`) |
| 🟡 Amarelo | Campo inferido por similaridade semântica (`low`) |
| 🔴 Vermelho | Campo ausente no retorno do LLM (`missing`) |

---

## Componentes em detalhe

### Descriptors (YAML)

Cada site tem um arquivo YAML em `scraper/descriptors/` com três seções:

```yaml
site: bambulab
base_url: "https://bambulab.com/en-us/"
output_prefix: "07_bambulab_products"

schema_fields:
  - product_name
  - category
  - price
  - product_url
  - details
  - specifications

instructions: |
  Instruções detalhadas de navegação e extração para o agente LLM...
```

O `PromptBuilder` carrega esse YAML e monta o prompt final incluindo as instruções, um JSON Schema dos campos esperados e o contrato de saída (somente JSON array).

### Schemas Pydantic

`ProductBase` define os campos comuns a todos os sites. Cada site herda e adiciona campos específicos:

```python
# Campos base (todos os sites)
product_name, category, subcategory, price,
product_url, source_url, specifications, scraped_at

# Exemplos de campos específicos
ActiveFloorProduct  → height_metric, width_metric, weight_metric, projector, brightness
SmartTechProduct    → display_size, resolution, touch_points, connectivity
BambulabProduct     → details
FormlabsProduct     → product_details
UltimakerProduct    → specs (lista de objetos {spec_name, type, spec_value})
MakerbotProduct     → price_current
PlayLuProduct       → item_type, description, target_age, technical_specifications
```

### Schema Mapper

O `SchemaMapper` resolve incompatibilidades entre os nomes de chave retornados pelo LLM e os campos do schema Pydantic usando três estratégias em cascata:

1. **Correspondência exata** (case-insensitive, normalizada) → confiança `high`
2. **Aliases explícitos** (ex.: `"cost"` → `price`, `"title"` → `product_name`) → confiança `high`
3. **Similaridade fuzzy** via `difflib.SequenceMatcher` com threshold 0.72 → confiança `low`

Se nenhuma estratégia encontrar correspondência, o campo recebe `None` e confiança `missing`.

### Runners

| Runner | Uso | Dependências |
|--------|-----|--------------|
| `MockRunner` | Testes e CI — serve fixtures locais | Nenhuma |
| `BrowserUseRunner` | Extração real com browser Chromium | `browser-use[aws]`, `boto3`, `playwright` |
| `AgentCoreRunner` | Extração via Bedrock Converse API (sem browser) | `boto3` |

Todos herdam `BrowserAgentRunner` e implementam o método `run(prompt, site) → RunnerResult`. O pipeline só fala com essa interface, permitindo trocar o runner sem alterar nenhum outro módulo.

---

## Testes

### Pytest (suite completa)

```powershell
# Todos os módulos
python -m pytest scraper/tests/ -v

# Só o pipeline
python -m pytest scraper/tests/test_pipeline.py -v

# Com relatório de cobertura (requer pytest-cov)
python -m pytest scraper/tests/ --cov=scraper --cov-report=term-missing
```

### Smoke scripts (sem pytest)

```powershell
python scraper/tests/run_pipeline_check.py      # 160 checks
python scraper/tests/run_runner_check.py
python scraper/tests/run_mapper_check.py
python scraper/tests/run_output_builder_check.py
python scraper/tests/run_prompt_builder_check.py
```

Os smoke scripts são úteis em ambientes sem pytest instalado ou para diagnóstico rápido. Saem com código 0 se tudo passou, 1 se algum check falhou.

---

## Variáveis de ambiente

| Variável | Usado por | Padrão |
|----------|-----------|--------|
| `BEDROCK_MODEL_ID` | AgentCoreRunner, BrowserUseRunner | `anthropic.claude-sonnet-4-6` |
| `AWS_DEFAULT_REGION` | AgentCoreRunner, BrowserUseRunner | `us-east-1` |
| `AWS_ACCESS_KEY_ID` | AgentCoreRunner | — |
| `AWS_SECRET_ACCESS_KEY` | AgentCoreRunner | — |
| `AWS_PROFILE` | BrowserUseRunner | — |
