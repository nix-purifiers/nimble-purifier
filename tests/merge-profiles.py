#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Merge actual native profiles captured on another platform."""

import json, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from nimble_purifier import lock

root = REPO / "examples/minimal"
companion = root / "nimble-purifier.lock.json"
native = root / "nimble.lock"
data = json.loads(companion.read_text())
assert not lock.problems(root, native, data)
for argument in sys.argv[1:]:
    incoming = json.loads(Path(argument).read_text())
    assert (
        incoming["inputs"] == data["inputs"]
        and incoming["manifests"] == data["manifests"]
    )
    with tempfile.TemporaryDirectory() as temporary:
        check = Path(temporary) / "nimble.lock"
        check.write_text(incoming["nativeLock"])
        assert not lock.problems(root, check, incoming)
    data["profiles"].update(incoming["profiles"])
data = lock.seal(data)
assert not lock.problems(root, native, data)
companion.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
