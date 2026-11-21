"""Exercise the public Sol command with a local field and a stubbed Codex session."""
import sys

import pytest
from PIL import Image

from pathology_tools import free_session, reviewed_hybrid
from sols_hammer.hybrid_entry import main


@pytest.mark.parametrize(("mode", "engine"), [
    ("tool-guided", "tools"), ("model-guided", "raw"), ("hybrid", "hybrid")
])
def test_sol_cli_prepares_and_routes_field(tmp_path, monkeypatch, mode, engine):
    source = tmp_path / "input.png"
    field = tmp_path / "F01"
    Image.new("RGB", (64, 64), "pink").save(source)
    monkeypatch.setattr(sys, "argv", ["sols-hammer", "prepare", "--image", str(source), "--field", str(field)])
    main()
    assert (field / "field.json").is_file()
    called = []

    def record(host, individual, args):
        called.append((host, individual, args.mode, args.fields))

    backend = reviewed_hybrid if mode == "hybrid" else free_session
    monkeypatch.setattr(backend, "run", record)
    monkeypatch.setattr(sys, "argv", [
        "sols-hammer", "workbench", "--mode", mode, "--fields", str(field),
        "--output", str(tmp_path / "result")
    ])
    main()
    assert called == [("sol", False, engine, [field])]
