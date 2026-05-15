# Dataform Forge CLI 🔨

O **Dataform Forge** é um framework de linha de comando (CLI) premium desenhado para acelerar, padronizar e automatizar a criação de pipelines e documentações dentro do ecossistema Google Cloud Dataform / BigQuery.

Ele ingere arquivos brutos (**Parquet, CSV, JSON, NDJSON**) locais ou no GCS, extrai schemas instantaneamente e "forja" as camadas Bronze e Silver do Dataform, aplicando **Taxonomias** rigorosas de engenharia de dados (ex: `CD_`, `DT_`, `VL_`) e enriquecendo metadados usando **Inteligência Artificial (OpenRouter)**.

---

## 📦 Como Instalar (Uso Global)

Este framework é distribuído como um pacote Python nativo.

### Opção 1: Instalação direta via Git (Recomendado para usuários)
Escolha uma das opções abaixo para instalar ou atualizar:

**Versão estável específica (v1.1.1):**
```bash
pip install git+https://github.com/nick-vml/sqlx-gen-cli.git@v1.1.1
```

**Versão mais recente da branch principal (Main):**
```bash
pip install --upgrade git+https://github.com/nick-vml/sqlx-gen-cli.git@main
```

**Forçar atualização completa (Reinstala tudo):**
```bash
pip install --upgrade --force-reinstall git+https://github.com/nick-vml/sqlx-gen-cli.git@main
```

**Atualização rápida (Apenas código, muito mais rápido):**
```bash
pip install --upgrade --no-deps git+https://github.com/nick-vml/sqlx-gen-cli.git@main
```

### Opção 2: Instalação local (Para desenvolvimento)
Navegue até a pasta do repositório e instale no modo editável:
```bash
pip install -e .
```

---

## 🚀 Como Utilizar (Guia Rápido)

### 1. Inicializar estrutura
Entre na pasta do seu projeto Dataform e execute:
```bash
sqlx_gen init
```
O CLI solicitará seu token do **OpenRouter** e criará automaticamente a estrutura de pastas e arquivos de configuração (`.env`, `api_key.txt`, `tabelas.json`).

### 2. Configurar fontes
Edite o arquivo `tabelas.json` com os caminhos dos arquivos de origem (Locais ou GCS `gs://...`). O gerador detectará automaticamente se o arquivo é Parquet, CSV ou JSON.

### 3. Rodar o Modo Interativo
Basta digitar:
```bash
sqlx_gen
```
Isso abrirá um menu visual onde você poderá:
- **Gerar SQLX:** Cria os arquivos `.sqlx` para as camadas Bronze e Silver, com opção de enriquecimento por IA.
- **Sair:** Encerra a ferramenta.

---

## 🛠️ Comandos Disponíveis

- **`sqlx_gen`**: Abre o menu interativo principal.
- **`sqlx_gen init`**: Prepara o diretório de trabalho.
- **`sqlx_gen generate`**: Comando direto para geração de arquivos (ver `--help`).
- **`sqlx_gen generate-docs`**: Gera documentação técnica em Markdown baseada nos metadados extraídos.

---

## 🧠 Inteligência Artificial & Taxonomia

O Dataform Forge não apenas renomeia colunas, ele entende os dados:
1. **Limpeza de Redundância**: Se uma coluna se chama `DATA_NASCIMENTO`, o sistema remove o prefixo redundante e aplica a taxonomia correta, resultando em `DT_NASCIMENTO` (em vez de `DT_DATA_NASCIMENTO`).
2. **OpenRouter Integration**: Utiliza modelos de ponta (como Claude 3.5 Sonnet) para inferir descrições de negócio, detectar dados sensíveis (LGPD) e sugerir casts de tipos complexos.
3. **Fallback Seguro**: Caso não existam variáveis de ambiente, o sistema busca a chave de API no arquivo `api_key.txt` gerado no `init`.

---

## ❓ FAQ

**1. Comando não encontrado?**
Certifique-se de que a pasta de Scripts do Python está no seu PATH do sistema.

**2. Como atualizar o glossário?**
O arquivo `glossario.json` é atualizado automaticamente a cada execução com IA bem-sucedida, permitindo que o framework "aprenda" com o tempo e economize tokens.

**3. Suporte a GCS?**
Sim! Ao usar caminhos `gs://`, o extrator realiza o download inteligente (no caso de Parquet, apenas do footer) para máxima performance.

---
*Desenvolvido com ❤️ pela equipe de Engenharia de Dados VML.*
