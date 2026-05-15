# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.2] - 2026-05-15

### Corrigido
- **Erro de Referência:** Correção de `NameError` ao tentar executar a extração de schemas devido a um import ausente no comando `generate`.

## [1.1.1] - 2026-05-15

### Adicionado
- **Validação de API Key:** O menu interativo agora verifica proativamente se a chave do OpenRouter está configurada antes de iniciar a geração com IA.
- **Feedback de Inicialização:** Novo prompt interativo no comando `init` para inserção imediata do token de IA.

### Corrigido
- **Filtro de Placeholder de API:** O sistema agora detecta e ignora chaves de exemplo (como `sk-or-v1-...`) vindas do ambiente, garantindo que o fallback para `api_key.txt` funcione mesmo com arquivos `.env` antigos presentes.
- **Fim do Delay de Processamento:** O status de carregamento agora aparece instantaneamente após a resposta do usuário no menu, eliminando o vácuo de espera.
- **Simplificação de Configuração:** Remoção da dependência de arquivos `.env` para chaves de API, centralizando no `api_key.txt` para maior simplicidade.
- **Silenciamento de Logs:** Redução de ruído visual no terminal através do silenciamento de avisos redundantes do cliente de IA.

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
