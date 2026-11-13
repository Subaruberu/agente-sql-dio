from __future__ import annotations

from types import SimpleNamespace

from sql_agent.llm import OpenAICompatibleLLM


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content

    def create(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def _fake_llm(content: str) -> OpenAICompatibleLLM:
    llm = object.__new__(OpenAICompatibleLLM)
    llm.model = "modelo-de-teste"
    llm.temperature = 0.0
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions(content)))
    return llm


def test_complete_normaliza_espacos_unicode_devolvidos_pelo_modelo() -> None:
    llm = _fake_llm("  R$ 45\u202f775,45\u00a0gastos  ")

    assert llm.complete("sistema", "usuário") == "R$ 45 775,45 gastos"
