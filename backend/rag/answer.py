"""Public custom-RAG answer entry point; no orchestration framework required."""


def answer(*args, **kwargs):
    from .pipeline import answer as run

    return run(*args, **kwargs)
