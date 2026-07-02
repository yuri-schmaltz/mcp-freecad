# Plano de Melhorias, Correção de Bugs e Robustecimento — mcp-freecad

> Documento vivo. Atualizar à medida que itens forem tratados.
> Versão da análise: baseada no commit `2c48d3e` (HEAD de `main`).
> Versão do projeto: `0.1.18`.

---

## 0. Mapa arquitetural

```
┌────────────────────────────────────────────┐
│  LLM client (Claude Desktop, ADK, …)       │
└──────────────────┬─────────────────────────┘
                   │ MCP over stdio
┌──────────────────▼─────────────────────────┐
│  MCP Server   src/freecad_mcp/             │
│  ├ server.py        FastMCP + lifespan     │
│  ├ operations/      11 tools               │
│  ├ guidelines.py    bloqueio de prompts    │
│  ├ responses.py     prefixo de diretriz    │
│  └ utils.py         safe_operation         │
└──────────────────┬─────────────────────────┘
                   │ XML-RPC (sem TLS, allow_none=True)
                   │ porta 9875, host validado
┌──────────────────▼─────────────────────────┐
│  RPC Server   addon/FreeCADMCP/rpc_server/ │
│  ├ rpc_server.py     XMLRPCServer          │
│  │                   + FilteredXMLRPCServer│
│  │                   + QTimer 500ms GUI    │
│  ├ serialize.py      serialização defensiva│
│  └ parts_library.py  path traversal?       │
└──────────────────┬─────────────────────────┘
                   │ in-process
┌──────────────────▼─────────────────────────┐
│  FreeCAD (App + Gui + Fem)                 │
└────────────────────────────────────────────┘
```

---

## 1. Bugs e fragilidades

### 🔴 Críticos (segurança / corretude)

| # | Local | Problema | Impacto |
|---|---|---|---|
| **C1** | `parts_library.insert_part_from_library` (addon) | `relative_path` é concatenado sem normalização. `../../etc/passwd` ou qualquer FCStd/arquivo fora de `parts_library` é aberto. | **Path traversal**. Combinado com C2 vira leitura arbitrária de arquivos no host do FreeCAD. |
| **C2** | `execute_code` no RPC | Executa Python arbitrário no processo FreeCAD com acesso total (FS, network, `os.system`). Sem sandbox/whitelist. | **RCE** quando exposto remotamente. Mesmo localmente é um vetor se um agente externo for autorizado. |
| **C3** | `check_prompt_conflict` em `guidelines.py` | Matching por substring (`"eval(" in p`). Bypass trivial: `ev al(`, `os .system`, `\x65val(`. Falsos positivos: nome `"eval test"` é bloqueado. | **Filtro de segurança ineficaz** e barulhento. |
| **C4** | `operations/core.py` | `check_prompt_conflict` é aplicado em **todos** os parâmetros: `obj_name`, `doc_name`, `relative_path`. Nomes legítimos como `"eval_part"` disparam bloqueio. | UX ruim + incentiva o agente a renomear para evitar filtros (anti-padrão). |

### 🟠 Altos (robustez / disponibilidade)

| # | Local | Problema | Impacto |
|---|---|---|---|
| **A1** | `freecad_client.FreeCADConnection` | XML-RPC sem timeout. Todas as chamadas (exceto `run_fem_analysis`) penduram indefinidamente se o RPC server travar. | DoS fácil do agente: uma chamada trava a sessão MCP inteira até o cliente matar o processo. |
| **A2** | `rpc_server.process_gui_tasks` | Se uma exceção escapar fora do `try/except task()`, o `QTimer.singleShot(500, …)` final não dispara. Resiliência boa para `task()` mas não para o próprio dispatcher. | Loop silenciosamente morre; RPC começa a devolver `queue.Empty` para tudo. |
| **A3** | `rpc_server.run_fem_analysis` | `work_dir = tempfile.mkdtemp(...)` não é limpo em caso de erro nem em caso de sucesso. | Leak cumulativo de `/tmp/freecad_mcp_fem_*` (CCX gera centenas de MB). |
| **A4** | `rpc_server.execute_code` | `output_buffer = io.StringIO()` é criado **fora** do `task()`. Em chamadas concorrentes, o buffer do request N pode capturar `print()` do request M. | Saída cruzada, debug confuso. |
| **A5** | `rpc_server.FreeCADRPC.TIMEOUT = 10` | Hardcoded curto. `create_object` com mesh grande ou import pesado estoura timeout → `queue.Empty` → exceção no cliente sem diagnóstico. | Falhas intermitentes em modelos reais. |
| **A6** | `get_active_screenshot` | Faz **duas** chamadas RPC (verificação de view + captura). A view pode mudar entre elas (race com usuário trocando de workbench). | Screenshots em branco ou de view errada. |
| **A7** | `parts_library.get_parts_list` | `@cache` por toda a vida do processo. Adicionar arquivos novos em `~/.FreeCAD/Mod/parts_library/` exige reiniciar FreeCAD. | Funcionalidade "razoável" mas não documentada, pegadinha. |
| **A8** | `rpc_server_thread` / `rpc_server_instance` | Globais mutáveis sem lock. `start_rpc_server` chamado em duas threads cria dois servers. | Race em ambientes com auto-start + clique manual simultâneo. |
| **A9** | `configure_logging` em `server.py` | Adiciona handlers ao **root logger** toda vez que o módulo é importado. Em testes ou reload (ex.: Jupyter, `importlib.reload`) acumula handlers e duplica logs. | Logs inflados; rotação de arquivo fica confusa. |

### 🟡 Médios (qualidade / manutenção)

| # | Local | Problema | Impacto |
|---|---|---|---|
| M1 | `operations/core.py` | `create_document_operation` e `get_view_operation` **não** usam `@safe_operation`. Inconsistência. | Exceção bruta vaza ao cliente; perda de prefixo de diretriz; resposta malformada em alguns casos. |
| M2 | `_save_active_screenshot` | Não captura `KeyboardInterrupt`/`SystemExit`; pode deixar seleção suja se interrompido. | Estado inconsistente do FreeCAD após Ctrl+C. |
| M3 | `set_object_property` | Erros por propriedade são **silenciados** (`FreeCAD.Console.PrintError`). Caller não recebe sinal de falha parcial. | "edit succeeded" reportado quando metade falhou. |
| M4 | `serialize_object` | Para ViewObject ausente deixa `{}` em vez de `None` ou chave omitida. | JSON inconsistente entre objetos com/sem view. |
| M5 | `_get_settings_path` | `os.path.join(getUserAppDataDir(), …)` sem validação. Em FreeCAD portátil o dir pode ser read-only. | Falha silenciosa em auto-start ou salvamento de config. |
| M6 | `start_rpc_server` | Não chama `server_close()`; só `shutdown()`. Socket pode permanecer em TIME_WAIT. | Em re-starts rápidos, "Address already in use". |
| M7 | `validate_allowed_ips` | Aceita `0.0.0.0/0` sem aviso. Permite **toda a internet** se o usuário ativar remote_enabled. | Backdoor involuntário. |
| M8 | `pyproject.toml` | `description = "Add your description here"` placeholder. | PyPI/readme feios. |
| M9 | `responses._ensure_prefix` | Adiciona prefixo a **toda** resposta, incluindo erros. Polui logs e pode ser redundante após a primeira chamada. | UX da resposta do tool fica verbosa. |
| M10 | `mcp_instructions` | Carrega `gabarito_ia_extracted.txt` na inicialização e concatena `ASSET_CREATION_STRATEGY`. Tamanho final >2KB; entra em todas as chamadas do LLM. | Custo de tokens crescente. |
| M11 | `examples/langchain/react.py` | Caminho `path/to/freecad-mcp` é placeholder literal — não roda sem edição manual. | Onboarding friction. |
| M12 | CI (`.github/workflows/ci.yml`) | Roda apenas `tests/run_guidelines_tests.py` (e esse arquivo só chama **2 dos 5** testes no `__main__`). | Cobertura efetiva ≈ 0. |

### 🔵 Baixos (cosméticos / DX)

| # | Local | Problema |
|---|---|---|
| L1 | `server_state.ServerState` | `dataclass` sem mecanismo para reset/concorrência. |
| L2 | `serialize_object` | Não serializa `Label2`, `Description`, etc. |
| L3 | `parts_library.insert_part_from_library` | Não retorna nome do objeto importado. |
| L4 | `run_fem_analysis_operation` | Não expõe `min_displacement_mm`. |
| L5 | README | Não menciona o gabarito_ia.pdf — quem chega pelo PyPI não entende o prefixo. |

---

## 2. Plano de ação priorizado

### Fase 1 — Segurança & estabilidade básica (1-2 sprints)
**Objetivo**: fechar vetores críticos e DoS.

- [x] **P1.1** ✅ Corrigir `parts_library.insert_part_from_library` — branch `chore/quick-wins` commit `9aadd02`
- [x] **P1.2** ✅ Timeout no XML-RPC client — branch `chore/quick-wins` commit `6d22319`
- [x] **P1.3** ✅ Regex no `check_prompt_conflict`, scope por tipo — branch `fix/guidelines-regex` commit `6b4b085`
- [x] **P1.4** ✅ Idempotência + cancel via `request_id` — branch `feat/request-id-and-cancellation` commit `178e9d5`
- [x] **P1.5** ✅ Limpar `work_dir` FEM + opt-out — branch `chore/quick-wins` commit `902d1a6`

### Fase 2 — Robustez do RPC server (1 sprint)

- [x] **P2.1** ✅ `output_buffer` movido para dentro do `task()` — `chore/quick-wins` `dc596d6`
- [x] **P2.2** ✅ `process_gui_tasks` reschedule garantido — `chore/quick-wins` `e57e638`
- [x] **P2.3** ✅ Timeout por operação + env vars — `feat/per-call-timeout` `89d5a37`
- [x] **P2.4** ✅ `get_active_screenshot` em uma chamada — `feat/screenshot-single-call` `2827a06`
- [x] **P2.5** ✅ `start`/`stop` thread-safe — `fix/rpc-server-thread-safety` `5ffc9b8`
- [x] **P2.6** ✅ `parts_library.get_parts_list` cache por mtime — `fix/parts-list-cache-invalidation` `8c9f138`
- [x] **P2.7** ✅ `configure_logging` idempotente — `chore/quick-wins` `eaafae3`
- [x] **P2.8** ✅ `_get_settings_path` fallback chain — `fix/settings-path-fallback` `b71a00a`

### Fase 3 — Consistência e DX (1 sprint)

- [ ] **P3.1** Aplicar `@safe_operation` em **todas** as 11 operações (corrige M1).
- [ ] **P3.2** `_save_active_screenshot`: `try/finally` para limpar seleção mesmo em erro.
- [ ] **P3.3** `set_object_property`: coletar erros em lista, retornar como `warnings` no dict de resposta.
- [ ] **P3.4** `validate_allowed_ips`: bloquear `0.0.0.0/0` (e equivalentes IPv6) com warning explícito ao usuário.
- [ ] **P3.5** `pyproject.toml`: description real + keywords + URLs (homepage, repo, issues).
- [ ] **P3.6** Tornar o prefixo do gabarito opcional via `FREECAD_MCP_NO_DIRECTIVE_PREFIX=1`.
- [ ] **P3.7** `mcp_instructions`: truncar ou comprimir; medir tokens.
- [ ] **P3.8** Adicionar `make_toycar`/`cantilever_fem` ao CI como **integration tests skipped** (marcados com `pytest.mark.freecad`).

### Fase 4 — Testes & CI (1 sprint)

- [ ] **P4.1** Migrar CI para `pytest` com matriz Python 3.11 / 3.12 / 3.13.
- [ ] **P4.2** Estrutura de testes:
  ```
  tests/
    unit/
      test_guidelines.py
      test_responses.py
      test_utils.py
      test_freecad_client.py   (mock ServerProxy)
      test_validate_allowed_ips.py
      test_parts_library.py    (mock os.path)
      test_serialize.py        (existente)
    integration/
      test_rpc_flow.py         (requer FreeCAD rodando, skip por padrão)
    conftest.py
  ```
- [ ] **P4.3** Cobertura mínima alvo: **70%** em `src/`, **50%** em `addon/`.
- [ ] **P4.4** Adicionar `pytest --cov` ao CI com badge.
- [ ] **P4.5** Adicionar `ruff` (lint) e `mypy` (tipos) ao CI.

### Fase 5 — Features & observabilidade (2 sprints)

- [ ] **P5.1** Métricas expostas via novo tool `health_check`:
  - uptime, contadores por operação, latência p50/p95, tamanho de filas.
- [ ] **P5.2** Suporte a **TLS** opcional no XML-RPC:
  - Detectar via `FREECAD_MCP_TLS_CERT` env, usar `ssl.wrap_socket` no server.
- [ ] **P5.3** Autenticação simples via token:
  - Header HTTP custom `Authorization: Bearer <token>` validado em `FilteredXMLRPCServer.verify_request`.
- [ ] **P5.4** Cancelamento cooperativo de operações longas.
- [ ] **P5.5** `screenshot` em formatos diferentes (`jpeg`, `webp`) e DPI configurável.
- [ ] **P5.6** Adicionar tool `undo` / `redo`.
- [ ] **P5.7** Adicionar tool `save_document(path)` e `export_object(obj_name, fmt)`.
- [ ] **P5.8** Suporte a `multipart/streaming` para arquivos grandes (STL export).
- [ ] **P5.9** **Async RPC**: substituir QTimer + queue por `asyncio` rodando no próprio FreeCAD (FreeCADGui tem Qt event loop).

### Fase 6 — Documentação & release (paralelo)

- [ ] **P6.1** Criar `CHANGELOG.md` (formato Keep a Changelog).
- [ ] **P6.2** Atualizar `README.md`:
  - Seção "Security" explicando o gabarito, IP filtering, riscos de `execute_code`.
  - Seção "Troubleshooting" com casos comuns (FreeCAD não inicia, timeout, IP bloqueado).
  - Tabela de compatibilidade FreeCAD 0.21 / 1.0 / 1.1.
- [ ] **P6.3** Adicionar `CONTRIBUTING.md` com setup de dev (venv, lint, test).
- [ ] **P6.4** Adicionar `SECURITY.md` com política de reporte de vulnerabilidades.
- [ ] **P6.5** Exemplo executável: `examples/hello_freecad/` com script que cria um cubo sem editar paths.
- [ ] **P6.6** Release `0.2.0` após Fase 1+2; `0.3.0` após Fase 3+4; `1.0.0` após Fase 5.

---

## 3. Decisões arquiteturais pendentes

| Tema | Opções | Recomendação |
|---|---|---|
| Substituir XML-RPC | (a) manter, (b) JSON-RPC, (c) gRPC | (a) por enquanto — overhead de mudar é alto; investir em **TLS + auth** ao invés. |
| Sandbox de `execute_code` | (a) RestrictedPython, (b) subprocess + IPC, (c) whitelist de módulos | (c) para Fase 1 (rápido, simples); (b) para Fase 5 (robusto). |
| Substituir QTimer por async | (a) QTimer (atual), (b) asyncio + qasync | (b) só vale quando outras melhorias async chegarem (Fase 5). |
| Persistência de settings | (a) JSON em `getUserAppDataDir` (atual), (b) QSettings do FreeCAD | (b) é mais "free-cad-nativo", mas (a) é mais portável. Manter (a) com fallback. |

---

## 4. Métricas de sucesso

- **Bugs críticos**: 0 conhecidos em release 0.3.0.
- **Cobertura de testes**: ≥70% (`src/`), ≥50% (`addon/`).
- **Latência p95** das tools (exceto FEM): < 2s em idle.
- **Tamanho de `mcp_instructions`**: < 1KB.
- **CVEs em deps**: 0 high/critical no CI.
- **Documentação**: README + CHANGELOG + SECURITY + CONTRIBUTING presentes.

---

## 5. Quick wins (≤ 1h cada)

1. Corrigir placeholder em `pyproject.toml` (M8).
2. Adicionar `if root.handlers: return` em `configure_logging` (A9).
3. Aplicar `@safe_operation` nas 2 funções faltantes (M1).
4. Limpar `work_dir` no FEM com `try/finally` (A3).
5. Bloquear `0.0.0.0/0` em `validate_allowed_ips` (M7).
6. Mover `output_buffer` para dentro do `task()` (A4).
7. Envolver `process_gui_tasks` em try/finally (A2).
8. Corrigir path traversal em `parts_library` (C1).
9. Adicionar timeout no XML-RPC client (A1).
10. Adicionar `tests/test_validate_allowed_ips.py` (P4.2).

---

## 6. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| FreeCAD API mudar entre versões | Alta | Alto | Manter `tests/integration` em matriz; documentar versões suportadas. |
| XML-RPC tem limite de payload | Média | Médio | Para FEM results grandes, retornar via arquivo temporário + hash. |
| Quebrar compatibilidade com Claude Desktop config | Baixa | Alto | Manter entry point `freecad-mcp` e CLI args estáveis em minor releases. |
| Agente LLM gerar carga excessiva | Média | Médio | Rate limiting por `request_id` + circuit breaker. |

---

## 7. Próximo passo imediato

Executar os **Quick wins** (#1-10) num único PR `chore/quick-wins`, depois iniciar Fase 1 com PRs focados em segurança (`fix/path-traversal`, `fix/xmlrpc-timeout`, `fix/guidelines-regex`).