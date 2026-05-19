# Design: ai_settings.json + Onboarding + Testes

**Data:** 2026-05-19  
**Status:** Aprovado  
**Projeto:** sqlx-gen-cli

---

## Contexto

O projeto usa três fontes para a API key do OpenRouter: `api_key.txt`, variável de ambiente `OPENROUTER_API_KEY` e bloco `ai:` no `generator.yaml`. Isso é confuso e dificulta onboarding. O objetivo é consolidar toda configuração de IA em `config/ai_settings.json`, remover `api_key.txt`, e adicionar um wizard interativo de primeira execução.

---

## Escopo

- Criar `config/ai_settings.json` como única fonte de configuração de IA
- Remover completamente `api_key.txt` do projeto
- Adicionar wizard de onboarding disparado automaticamente na primeira execução
- Remover seção `ai:` do `generator.yaml`
- Simplificar `OpenRouterClient` para receber config diretamente
- Adicionar suite de testes unitários para módulos críticos

Fora do escopo: refactor dos geradores Bronze/Silver, mudanças na extração de schema, alterações no `generator.yaml` além da remoção da seção `ai:`.

---

## Arquitetura

### Novos arquivos

**`config/ai_settings.json`** (adicionado ao `.gitignore`)
```json
{
  "api_key": "sk-or-v1-...",
  "model": "openai/gpt-4o-mini",
  "fallback_models": ["google/gemma-4-31b-it:free"],
  "enabled": true,
  "max_retries": 3,
  "timeout_seconds": 60,
  "max_parallel": 3,
  "detect_pii": true,
  "classify_sensitivity": true
}
```

**`src/utils/ai_settings.py`**
- `AISettings` — modelo Pydantic com todos os campos de IA; `api_key` tem `repr=False` para não vazar em logs
- `AI_SETTINGS_PATH = Path("config/ai_settings.json")` — constante
- `load_ai_settings(path) -> AISettings` — lê e valida; se arquivo ausente retorna defaults com `enabled=False`
- `save_ai_settings(settings, path)` — salva com indent=2, ensure_ascii=False

**`src/cli/__init__.py`** (vazio)

**`src/cli/onboarding.py`**
- `is_first_run() -> bool` — verifica se `AI_SETTINGS_PATH` não existe
- `run_onboarding_wizard() -> AISettings` — wizard Rich interativo:
  1. Banner de boas-vindas
  2. Solicita API key (Enter = skip, desativa IA)
  3. Seleciona modelo de lista pré-definida (5 opções + "digitar manualmente")
  4. Salva `config/ai_settings.json`
  5. Adiciona `config/ai_settings.json` ao `.gitignore` se não estiver lá
  6. Retorna `AISettings` configurado
- `ensure_gitignore_entry(entry: str)` — helper para atualizar `.gitignore`

**`tests/`** — diretório com `conftest.py` e testes (detalhado abaixo)

### Arquivos modificados

**`config/generator.yaml`** — remove seção `ai:` inteira

**`src/utils/config_loader.py`**
- Remove import e classe `AIConfig`
- Remove campo `ai: AIConfig` de `GeneratorConfig`
- Sem outras mudanças

**`src/ai/openrouter_client.py`**
- Remove fallback `api_key.txt`
- Mantém leitura de `OPENROUTER_API_KEY` como fallback secundário
- Prioridade: `api_key` passado diretamente (de `ai_settings.json`) > `OPENROUTER_API_KEY` (env var) > vazio (IA desabilitada)
- Construtor: `__init__(self, api_key: str | None, primary_model: str, fallback_models, max_retries, timeout)`
- Se `api_key` for vazio/None após resolver todas as fontes, retorna `AIResponse` vazio imediatamente sem logar erro

**`main.py`**
- Mantém `load_dotenv()` para suporte à variável `OPENROUTER_API_KEY` via `.env`
- Remove todo o código de `api_key.txt` no `init_project()`
- Adiciona `_check_first_run()` chamado no início de qualquer comando que precise de config
- `init_project()` chama `run_onboarding_wizard()` ao invés de criar `api_key.txt`
- `MetadataManager` recebe `AISettings` separadamente de `GeneratorConfig`

**`.gitignore`** — adiciona `config/ai_settings.json`

### Arquivos removidos

- `api_key.txt` — eliminado; referências removidas de todo o código

---

## Fluxo de execução

```
Usuário executa qualquer comando
         ↓
_check_first_run()
         ↓
config/ai_settings.json existe?
   NÃO → run_onboarding_wizard() → salva ai_settings.json → continua
   SIM → continua
         ↓
load_config(generator.yaml) → GeneratorConfig
load_ai_settings() → AISettings
         ↓
Resolução da API key:
   ai_settings.api_key (se preenchido)
   → senão: os.getenv("OPENROUTER_API_KEY")  ← via .env ou env real
   → senão: IA desabilitada
         ↓
MetadataManager(config, ai_settings)
         ↓
OpenRouterClient(api_key=resolved_key, ...)
```

---

## Wizard de onboarding (UX)

```
╔══════════════════════════════════════════════╗
║  SQLX Gen — Configuração Inicial             ║
║  Vamos configurar a IA em menos de 1 minuto  ║
╚══════════════════════════════════════════════╝

🔑 API Key do OpenRouter (pressione Enter para pular):
   > sk-or-v1-...

🤖 Modelo padrão:
   1. openai/gpt-4o-mini (rápido, econômico)
   2. openai/gpt-4o (mais capaz)
   3. anthropic/claude-3.5-sonnet (recomendado)
   4. google/gemma-4-31b-it:free (gratuito)
   5. openai/gpt-oss-120b:free (gratuito)
   6. Digitar manualmente
   > 3

✅ Configuração salva em config/ai_settings.json
✅ config/ai_settings.json adicionado ao .gitignore
```

Se o usuário pular a API key:
- `enabled: false` no `ai_settings.json`
- A IA fica desativada e pode ser reativada editando o arquivo manualmente

---

## Testes unitários

### `tests/conftest.py`
- Fixture `tmp_config_dir` — tmpdir com estrutura mínima de config
- Fixture `sample_ai_settings` — `AISettings` com dados de teste (api_key fake)

### `tests/test_ai_settings.py`
| Teste | Cenário |
|-------|---------|
| `test_load_valid_settings` | JSON válido → campos corretos |
| `test_load_missing_file_returns_defaults` | Arquivo ausente → defaults, `enabled=False` |
| `test_load_invalid_json_raises` | JSON malformado → `ValueError` com mensagem clara |
| `test_save_and_reload` | Salva e relê → dados idênticos |
| `test_api_key_not_in_repr` | `repr(settings)` não contém a api_key |

### `tests/test_config_loader.py`
| Teste | Cenário |
|-------|---------|
| `test_load_valid_yaml` | YAML completo → `GeneratorConfig` com campos corretos |
| `test_load_missing_yaml_returns_defaults` | Arquivo ausente → defaults funcionais |
| `test_generator_config_has_no_ai_field` | `GeneratorConfig` não tem atributo `ai` |

### `tests/test_openrouter_client.py`
| Teste | Cenário |
|-------|---------|
| `test_chat_success` | Mock OpenAI API → `AIResponse` com `parsed` correto |
| `test_chat_fallback_on_model_failure` | Primeiro modelo lança `APIError` → usa fallback |
| `test_chat_no_api_key_returns_empty` | `api_key=""` → `AIResponse` vazio, sem exception |
| `test_parse_json_from_markdown_block` | Resposta com \`\`\`json...\`\`\` → dict extraído |
| `test_retry_on_rate_limit` | `RateLimitError` na 1ª tentativa → retry, sucesso na 2ª |

### `tests/test_onboarding.py`
| Teste | Cenário |
|-------|---------|
| `test_is_first_run_true_when_no_settings` | Arquivo ausente → `True` |
| `test_is_first_run_false_when_settings_exist` | Arquivo presente → `False` |
| `test_ensure_gitignore_adds_entry` | `.gitignore` sem entrada → linha adicionada |
| `test_ensure_gitignore_no_duplicate` | Entrada já existe → não duplica |

---

## Considerações de segurança

- `api_key` usa `Field(repr=False)` no Pydantic para não aparecer em logs/repr
- `config/ai_settings.json` adicionado ao `.gitignore` no wizard E no `init`
- Se `ai_settings.json` não for encontrado, a IA é desabilitada silenciosamente (sem crash)
- `OPENROUTER_API_KEY` é mantida como fallback; `.env` continua suportado via `load_dotenv()`
- Prioridade explícita e documentada: `ai_settings.json` > `OPENROUTER_API_KEY` > desabilitado

---

## Compatibilidade

Usuários com setup anterior precisam:
1. Executar `sqlx_gen init` ou qualquer outro comando (wizard aparece automaticamente)
2. Inserir a API key no wizard
3. Remover manualmente `api_key.txt` e a seção `ai:` do `generator.yaml` (o CLI avisa se encontrá-los)

O CLI exibe aviso se detectar `api_key.txt` ou seção `ai:` no YAML, orientando a migração.
