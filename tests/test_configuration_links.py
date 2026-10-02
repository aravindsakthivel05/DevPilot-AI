from backend.config_links import configuration_edges


def test_type_stub_and_mockito_plugin_links_are_explicit():
    files = {
        "src/pkg/api.py": "def call(): pass\n",
        "src/pkg/api.pyi": "def call() -> None: ...\n",
        "src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker": (
            "org.mockito.internal.CustomMockMaker\n"
        ),
    }
    symbols = [
        {"id": "py", "path": "src/pkg/api.py", "kind": "module", "qualified": "pkg.api"},
        {
            "id": "stub",
            "path": "src/pkg/api.pyi",
            "kind": "document",
            "qualified": "src/pkg/api.pyi",
        },
        {
            "id": "config",
            "path": "src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker",
            "kind": "document",
            "qualified": "config",
        },
        {
            "id": "interface-module",
            "path": "MockMaker.java",
            "kind": "module",
            "qualified": "org.mockito.plugins.MockMaker",
        },
        {
            "id": "interface",
            "path": "MockMaker.java",
            "kind": "interface",
            "qualified": "org.mockito.plugins.MockMaker",
        },
        {
            "id": "implementation",
            "path": "CustomMockMaker.java",
            "kind": "class",
            "qualified": "org.mockito.internal.CustomMockMaker",
        },
    ]
    edges = configuration_edges("repo", files, symbols)
    assert {(edge["source"], edge["target"], edge["kind"]) for edge in edges} == {
        ("stub", "py", "type_stub_for"),
        ("config", "interface", "configures_interface"),
        ("config", "implementation", "selects_implementation"),
    }
