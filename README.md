# Dataform Forge CLI 🔨

O **Dataform Forge** é um framework (CLI) desenhado para acelerar, padronizar e automatizar a criação de pipelines e documentações dentro do ecossistema Google Cloud Dataform / BigQuery.

Ele lê de arquivos **Parquet** brutos (locais ou no GCS), extrai schemas de forma instantânea e "forja" as camadas Bronze e Silver do Dataform, aplicando **Taxonomias** de engenharia de dados (ex: `CD_`, `DT_`, `VL_`) e enriquecendo as descrições de negócio usando **Inteligência Artificial (OpenRouter)**.

---

## 📦 Como Instalar (Uso Global)

Como este framework foi refatorado para ser distribuído como um pacote Python nativo (`pip`), você não precisa mais rodar via script local.

1. Clone o repositório ou navegue até a pasta base onde o `setup.py` se encontra.
2. Execute o comando de instalação no modo "editável" (ou instale diretamente via pip):

```bash
pip install -e .
```

A partir deste momento, o comando global **`sqlx_gen`** estará disponível em qualquer pasta do seu terminal!

---

## 🚀 Como Utilizar (Passo a Passo)

### 1. Inicializando um novo projeto (Scaffolding)
Navegue até a pasta do seu repositório de dados/Dataform no terminal e rode o comando de inicialização. Ele irá criar toda a estrutura de pastas necessária (`config/`, `generated/`, `parquet/`), além dos arquivos `.env`, `tabelas.json` e do principal `generator.yaml` de forma automática.

```bash
sqlx_gen init
```

*Nota: não se esqueça de preencher sua chave de API no arquivo `.env`.*

### 2. Configurando o `tabelas.json`
O arquivo `tabelas.json` na raiz atua como a sua fila de processamento em batch. Ele é simplesmente um *Array* de caminhos. O framework entende perfeitamente caminhos do Google Cloud Storage.

```json
[
  "gs://vml_stg_gcp/omie/contas_a_pagar/date=2026-01-23/contas_a_pagar.parquet",
  "gs://vml_stg_gcp/erp_xpto/clientes/date=2026-01-23/clientes.parquet",
  "./parquet/arquivo_local.parquet"
]
```

### 3. Rodando o Gerador (Modo Interativo)
Basta chamar o comando principal vazio para abrir o **Menu Guiado**:

```bash
sqlx_gen
```

Isso mostrará opções coloridas e fáceis de usar:
1. **Gerar arquivos SQLX (Bronze/Silver):** Lê o(s) arquivo(s) Parquet, infere colunas, e cria as lógicas SQLX nas pastas `generated/`. Ele perguntará se você quer rodar a Inteligência Artificial para enriquecer a taxonomia.
2. **Inferir Schemas de Parquet:** Útil apenas para visualizar rapidamente o dicionário de dados da origem (salva em JSON).
3. **Gerar Documentação Markdown (AI):** Usa as tabelas extraídas e a inteligência artificial para montar uma documentação limpa em formato `.md`.

---

## 💻 3. Modo Automação (CLI para CI/CD)

Se você preferir executar as rotinas de forma programática via scripts em pipelines, utilize as flags diretas do CLI:

### Gerar Camadas (Com IA)
```bash
# Processa todos os arquivos do tabelas.json na camada Silver com IA ligada
sqlx_gen generate --layer silver --ai

# Passa múltiplos caminhos direto via argumento (ignorando tabelas.json) e desativa a IA
sqlx_gen generate -i gs://bucket/a.parquet -i gs://bucket/b.parquet --layer both --no-ai
```

### Documentação e Schemas
```bash
# Cria o esquema estático (dicionário bruto) de um diretório
sqlx_gen infer-schema --input gs://bucket/dados/ --output ./generated/metadata

# Gera os Markdowns de Data Cataloging usando Inteligência Artificial
sqlx_gen generate-docs --ai
```

---

## 🛠️ Entendendo a Taxonomia e GCS

1. **Magia do GCS**: Ao passar um path GCS (`gs://.../omie/tabela_x/...`), o extrator faz download *apenas do footer* do Parquet. É muito mais rápido e não exige tráfego do arquivo inteiro. Ele inferirá o nome do banco (`omie`) e da tabela (`tabela_x`) pelas quebras de pasta do storage.
2. **Taxonomia Automática**: A camada Silver formatará as colunas de origem de acordo com padrões de arquitetura corporativa:
   - `codigo_...` vira `CD_...`
   - `data_...` vira `DT_...`
   - `valor_...` vira `VL_...`
   - ...e o restante se transforma em maiúsculas (`UPPERCASE`) para fácil leitura, com o prefixo `DE_` para campos de texto/descrição (fallback).
