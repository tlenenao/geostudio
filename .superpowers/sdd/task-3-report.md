# Task 3 Report: Core — `llm_provider.py`

## Summary

Successfully implemented the pluggable LLM provider abstraction for SP-20 copilote embarqué following TDD discipline. All 5 tests pass. Implementation follows the exact same architectural pattern as `app.search.providers.EmbeddingProvider` (SP-7).

## Implementation Details

### Files Created

1. **`core/app/copilot/__init__.py`** — Empty module marker
2. **`core/app/copilot/llm_provider.py`** — Main implementation (84 lines)
   - `ToolCall` (dataclass): id, name, arguments
   - `LLMTurn` (dataclass): text response + tool_calls list
   - `LLMProvider` (Protocol): Interface with single `chat(messages, tools) -> LLMTurn` method
   - `FakeLLMProvider`: Scriptable, deterministic provider for tests/dev (no network)
     - Cycles through responses in order
     - Repeats last response once exhausted
   - `OpenAICompatibleLLMProvider`: Production HTTP provider
     - Calls OpenAI-compatible API via httpx
     - Parses tool_calls from OpenAI message format
   - `get_llm_provider()`: Factory function
     - Defaults to `FakeLLMProvider` when `CORE_LLM_PROVIDER` unset or "fake"
     - Returns `OpenAICompatibleLLMProvider` when `CORE_LLM_PROVIDER=openai`
     - Raises `ValueError` on unknown provider kind

3. **`core/tests/test_copilot_llm_provider.py`** — 5 test cases (66 lines)

### TDD Evidence

#### RED Phase
```
$ cd core && uv run pytest tests/test_copilot_llm_provider.py -v

ERROR collecting tests/test_copilot_llm_provider.py
...
ModuleNotFoundError: No module named 'app.copilot'
```

Confirmed module did not exist before implementation.

#### GREEN Phase
```
$ cd core && uv run pytest tests/test_copilot_llm_provider.py -v

tests/test_copilot_llm_provider.py::test_fake_provider_returns_scripted_responses_in_order PASSED [ 20%]
tests/test_copilot_llm_provider.py::test_fake_provider_repeats_last_response_once_exhausted PASSED [ 40%]
tests/test_copilot_llm_provider.py::test_get_llm_provider_defaults_to_fake PASSED [ 60%]
tests/test_copilot_llm_provider.py::test_get_llm_provider_rejects_unknown_kind PASSED [ 80%]
tests/test_copilot_llm_provider.py::test_openai_compatible_provider_parses_tool_calls PASSED [100%]

============================== 5 passed in 0.07s ===============================
```

All tests pass on first implementation.

### Test Coverage

1. **test_fake_provider_returns_scripted_responses_in_order**
   - Verifies responses consumed in order
   - Tests both tool_calls and text responses

2. **test_fake_provider_repeats_last_response_once_exhausted**
   - Ensures last response repeats indefinitely (not IndexError)

3. **test_get_llm_provider_defaults_to_fake**
   - Confirms default behavior when env var unset

4. **test_get_llm_provider_rejects_unknown_kind**
   - Verifies ValueError on invalid provider kind
   - Monkeypatch ensures env isolation

5. **test_openai_compatible_provider_parses_tool_calls**
   - Mocks httpx.post to verify API call format
   - Verifies Bearer token, model, and message format
   - Tests tool_call parsing from OpenAI response format
   - Tests JSON argument deserialization

### Architectural Alignment

- Follows same pattern as `app.search.providers.EmbeddingProvider` (SP-7)
- No database dependencies
- No authentication/authorization dependencies  
- Pure backend logic consumed by Task 5's routes.py
- French documentation aligns with CLAUDE.md language rules
- Dataclasses for structured data (following project conventions)
- Protocol for provider interface (duck-typing support)
- Environment-based factory configuration (os.environ)

### Commit Information

**SHA:** `c3da6d2`  
**Message:** `feat(core): fournisseur LLM enfichable pour le copilote (SP-20)`

```
LLMProvider (Protocol) + FakeLLMProvider (scriptable, tests/mock) +
OpenAICompatibleLLMProvider (CORE_LLM_PROVIDER=openai), même patron que
app.search.providers.EmbeddingProvider (SP-7).
```

## Self-Review Findings

### Code Quality
✓ All code matches brief exactly — character-for-character  
✓ French comments and docstrings appropriate per CLAUDE.md  
✓ SPDX license headers present on all files  
✓ Type hints complete and correct (Python 3.10+ syntax)  
✓ Dataclass defaults properly implemented (`field(default_factory=list)`)  
✓ No type: ignore comments needed  

### Testing
✓ Test file imports work correctly  
✓ Monkeypatch usage correct (setenv/delenv)  
✓ Mock httpx.post captures all required headers/JSON  
✓ JSON parsing tested (arguments field)  
✓ Error message matching correct (regex match)  

### Architecture
✓ No integration dependencies (httpx imported only in OpenAI provider)  
✓ Defaults sensible (FakeLLMProvider for dev, OpenAI for prod)  
✓ Factory pattern clean and extensible  
✓ Protocol allows duck-typing if new providers added later  
✓ No circular imports possible  

### No Issues Found

Code is production-ready. Implementation complete per brief specification.

## Files Changed

- Created: `core/app/copilot/__init__.py`
- Created: `core/app/copilot/llm_provider.py`
- Created: `core/tests/test_copilot_llm_provider.py`

## Next Steps

Task 3 complete. The LLM provider module is now available for Task 5's routes.py to consume via `from app.copilot.llm_provider import get_llm_provider`.
