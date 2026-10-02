from backend.ingestion import collect_files, supported_text_path


def test_targeted_text_files_are_indexed_without_admitting_arbitrary_files(tmp_path):
    paths = {
        "src/pkg/api.pyi": "def request(url: str) -> str: ...\n",
        "assets/site.css": "body { color: red; }\n",
        "Dockerfile": "FROM scratch\n",
        "src/test/resources/mockito-extensions/org.mockito.plugins.MockMaker": "mock-maker-inline\n",
        "fixture.bin": "not a supported file\n",
    }
    for name, content in paths.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    files, coverage, summary = collect_files(tmp_path, with_coverage=True)
    assert len(files) == 4
    assert summary["skipped_files"] == 1
    assert next(row for row in coverage if row["path"] == "fixture.bin")["reason"] == (
        "unsupported_extension"
    )
    assert supported_text_path("other/secret.dat") is False
