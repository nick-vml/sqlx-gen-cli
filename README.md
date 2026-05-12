# Dataform Forge CLI 🔨

O **Dataform Forge** é um framework (CLI) desenhado para acelerar, padronizar e automatizar a criação de pipelines e documentações dentro do ecossistema Google Cloud Dataform / BigQuery.

Ele lê de arquivos brutos (**Parquet, CSV, JSON**) locais ou no GCS, extrai schemas de forma instantânea e "forja" as camadas Bronze e Silver do Dataform, aplicando **Taxonomias** de engenharia de dados (ex: `CD_`, `DT_`, `VL_`) e enriquecendo as descrições de negócio usando **Inteligência Artificial (OpenRouter)**.

---

## 📦 Como Instalar (Uso Global)

Como este framework foi refatorado para ser distribuído como um pacote Python nativo (`pip`), você não precisa mais rodar via script local.

### Opção 1: Instalação direta via Git (Recomendado para usuários)
Você pode instalar o CLI diretamente a partir do repositório remoto sem precisar baixar os arquivos manualmente. Execute o seguinte comando no seu terminal:

```bash
pip install git+https://github.com/nick-vml/sqlx-gen-cli.git
```

### Opção 2: Instalação local (Para desenvolvimento)
Se você for modificar o código, clone o repositório ou navegue até a pasta base onde o `setup.py` se encontra. Em seguida, instale no modo "editável":

```bash
pip install -e .
```

A partir deste momento, o comando global **`sqlx_gen`** estará disponível em qualquer pasta do seu terminal!

---

## 🚀 Como Utilizar (Guia Rápido)

### 1. Inicializar estrutura
Entre na pasta do seu projeto e rode:
```bash
# Cria as pastas config, files, generated e arquivos base
sqlx_gen init
```

### 2. Configurar fontes
Adicione seus arquivos de origem na pasta `files/` (suporta `.parquet`, `.csv`, `.json`, `.jsonl`, `.ndjson`) ou edite o arquivo `tabelas.json` com caminhos locais ou do GCS utilizando o formato **gsutil URI** (`gs://bucket/path/`). O gerador detectará o formato automaticamente pela extensão.

### 3. Rodar o menu interativo
```bash
sqlx_gen
```

---


Isso mostrará opções coloridas e fáceis de usar:
1. **Gerar arquivos SQLX (Bronze/Silver):** Lê o(s) arquivo(s) de origem, infere colunas, e cria as lógicas SQLX nas pastas `generated/`. Ele perguntará se você quer rodar a Inteligência Artificial para enriquecer a taxonomia.
2. **Inferir Schemas:** Útil apenas para visualizar rapidamente o dicionário de dados da origem (salva em JSON).
3. **Gerar Documentação Markdown (AI):** Usa as tabelas extraídas e a inteligência artificial para montar uma documentação limpa em formato `.md`.

---

---

## 🛠️ Detalhamento dos Comandos

- **`sqlx_gen init`**: Cria a estrutura base.
- **`sqlx_gen generate`**: Processa Parquets e cria `.sqlx`.
- **`sqlx_gen generate-docs`**: Cria o portal de documentação em Markdown.

## ❓ Perguntas Frequentes (FAQ)

**1. Comando não encontrado?**
Certifique-se de que o Python Scripts está no seu PATH ou use `python main.py` como alternativa.

**2. Onde estão os arquivos?**
Tudo é gerado dentro da pasta `generated/`.

**3. Preciso de chave de IA?**
Opcional, mas recomendado para melhores descrições na camada Silver.


---

## 🛠️ Entendendo a Taxonomia e GCS

1. **Magia do GCS**: Ao passar um path GCS (`gs://.../omie/tabela_x/...`), o extrator faz download *apenas do footer* do Parquet. É muito mais rápido e não exige tráfego do arquivo inteiro. Ele inferirá o nome do banco (`omie`) e da tabela (`tabela_x`) pelas quebras de pasta do storage.
2. **Taxonomia Automática**: A camada Silver formatará as colunas de origem de acordo com padrões de arquitetura corporativa:
   - `codigo_...` vira `CD_...`
   - `data_...` vira `DT_...`
   - `valor_...` vira `VL_...`
   - ...e o restante se transforma em maiúsculas (`UPPERCASE`) para fácil leitura, com o prefixo `DE_` para campos de texto/descrição (fallback).
