"""Cliente de LLM independente de fornecedor (API compatível com OpenAI)."""

from __future__ import annotations

from typing import Protocol


class LLMConfigurationError(RuntimeError):
    """Configuração ausente ou inválida para o provedor de LLM."""


class LLMClient(Protocol):
    """Contrato mínimo usado pelo agente (facilita testes e troca de provedor)."""

    def complete(self, system: str, user: str) -> str:
        """Recebe um prompt de sistema e um de usuário e devolve o texto gerado."""


class OpenAICompatibleLLM:
    """Cliente para OpenAI, Groq, Gemini (endpoint compatível), Ollama, OpenRouter etc."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        temperature: float = 0.0,
        timeout: float = 90.0,
    ) -> None:
        if not model:
            raise LLMConfigurationError("Defina o modelo em LLM_MODEL (veja .env.example).")
        if not api_key:
            raise LLMConfigurationError(
                "Defina LLM_API_KEY no arquivo .env. Para Ollama local, use qualquer "
                "valor (ex.: ollama). Veja o README para exemplos por provedor."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depende do ambiente
            raise LLMConfigurationError(
                "Pacote 'openai' não instalado. Rode: pip install -r requirements.txt"
            ) from exc

        self.model = model
        self.temperature = temperature
        self._client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout)

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or ""
        return content.strip()
