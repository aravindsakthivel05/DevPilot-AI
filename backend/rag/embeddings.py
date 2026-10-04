"""Embedding-provider boundary and atomic legacy index integration."""

from ..model_providers import ConfiguredEmbeddingProvider


def embed(texts):
    return ConfiguredEmbeddingProvider().embed_batch(texts)
