"""Clean provider contracts backed by the existing configured HTTP transport."""

from typing import Protocol


class LLMProvider(Protocol):
    def generate(self, messages: list[dict], **options) -> dict: ...
    def structured_generate(self, messages: list[dict], schema: dict, **options) -> dict: ...


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class ConfiguredLLMProvider:
    def generate(self, messages, **options):
        from .config import provider_settings
        from .providers import request

        payload = {"model": provider_settings()["model"], "messages": messages, **options}
        return request("chat/completions", payload)

    def structured_generate(self, messages, schema, **options):
        return self.generate(
            messages, response_format={"type": "json_object"}, _ollama_schema=schema, **options
        )


class ConfiguredEmbeddingProvider:
    def embed(self, text):
        return self.embed_batch([text])[0]

    def embed_batch(self, texts):
        from .providers import embed

        return embed(texts)
