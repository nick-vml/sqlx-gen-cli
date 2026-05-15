# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-05-15

### Adicionado
- **Interface Interativa (Rich UI):** Novo menu principal colorido usando as bibliotecas `rich` e `pyfiglet`.
- **Suporte Multi-formato:** O extrator agora suporta arquivos `.csv`, `.json`, `.jsonl` e `.ndjson` além do `.parquet`.
- **Fluxo de Inicialização Inteligente:** O comando `sqlx_gen init` agora solicita o token do OpenRouter interativamente e configura os arquivos `.env` e `api_key.txt`.
- **Fallback de Autenticação AI:** Possibilidade de usar um arquivo `api_key.txt` local como alternativa às variáveis de ambiente para o token do OpenRouter.
- **Log de Progresso Elegante:** Substituição de logs verbosos por barras de progresso (`console.status`) e indicadores de conclusão (`✓`).

### Alterado
- **Renomeação de Módulo:** Pasta `src/parquet` renomeada para `src/extractor` para refletir o suporte a múltiplos formatos.
- **Taxonomia de Nomes:** Melhoria na lógica de prefixos para evitar redundâncias (ex: `DATA_DE_CADASTRO` agora vira `DT_DE_CADASTRO` em vez de `DT_DATA_DE_CADASTRO`).
- **Limpeza de UI:** Remoção de banners duplicados durante a execução de subcomandos via menu.

### Removido
- Logs de nível `INFO` das bibliotecas base para reduzir ruído no terminal.

---

## [1.0.0] - 2026-05-12

### Adicionado
- Versão inicial do framework Dataform SQLX Generator.
- Geração de camadas Bronze e Silver.
- Integração com OpenRouter para enriquecimento de metadados via IA.
- Extração de schema de arquivos Parquet locais e no GCS.
