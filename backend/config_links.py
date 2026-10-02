"""Conservative links from selected text configuration files to indexed symbols."""

from pathlib import PurePosixPath


def configuration_edges(repo_id, files, symbols):
    by_qualified = {}
    documents = {}
    modules = {}
    for symbol in symbols:
        by_qualified.setdefault(symbol["qualified"], []).append(symbol)
        if symbol["kind"] == "document":
            documents[symbol["path"]] = symbol
        elif symbol["kind"] == "module":
            modules[symbol["path"]] = symbol
    edges = []
    for path, content in files.items():
        document = documents.get(path)
        if not document:
            continue
        item = PurePosixPath(path)
        if item.suffix == ".pyi":
            implementation = modules.get(str(item.with_suffix(".py")))
            if implementation:
                edges.append(
                    dict(
                        repo_id=repo_id,
                        source=document["id"],
                        target=implementation["id"],
                        kind="type_stub_for",
                        line=1,
                        confidence="filename",
                        label=implementation["qualified"],
                    )
                )
        if "mockito-extensions" not in item.parts or not item.name.startswith(
            "org.mockito.plugins."
        ):
            continue
        for qualified, kind in (
            (item.name, "configures_interface"),
            (content.strip(), "selects_implementation"),
        ):
            targets = [
                symbol
                for symbol in by_qualified.get(qualified, [])
                if symbol["kind"] in ("class", "interface", "enum", "record")
            ]
            if len(targets) == 1:
                edges.append(
                    dict(
                        repo_id=repo_id,
                        source=document["id"],
                        target=targets[0]["id"],
                        kind=kind,
                        line=1,
                        confidence="static" if kind == "configures_interface" else "configured",
                        label=qualified,
                    )
                )
    return edges
