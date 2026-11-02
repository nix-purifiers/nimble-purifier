#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import copy, json, shutil, subprocess, sys, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from nimble_purifier import lock

with tempfile.TemporaryDirectory(prefix="nimble-eval-") as temporary:
    root = Path(temporary) / "project"
    shutil.copytree(
        REPO / "examples/minimal",
        root,
        ignore=shutil.ignore_patterns(
            ".nimble-purifier", "nimble.paths", "config.nims", "example", "test"
        ),
    )
    companion = root / "nimble-purifier.lock.json"
    native = root / "nimble.lock"
    recipe = root / "example.nimble"
    original = json.loads(companion.read_text())
    native_text = native.read_text()
    manifest = recipe.read_bytes()
    expression = (
        "let f=builtins.getFlake "
        + json.dumps(str(REPO))
        + "; r=f.lib.nimble-purifier.readLock {src=/. + "
        + json.dumps(str(root))
        + ";}; in {inherit (r) problems outputs entries;}"
    )

    def evaluate():
        value = subprocess.run(
            ["nix", "eval", "--impure", "--json", "--expr", expression],
            text=True,
            capture_output=True,
        )
        value.check_returncode()
        return json.loads(value.stdout)

    assert evaluate()["problems"] == []
    for mutation in (
        "seal",
        "path",
        "hash",
        "native-pin",
        "checksum",
        "rawcommit",
        "sdk",
        "registry",
        "alias",
        "native",
        "missing",
        "manifest",
    ):
        data = copy.deepcopy(original)
        native.write_text(native_text)
        recipe.write_bytes(manifest)
        profile = next(iter(data["profiles"].values()))
        dep = profile["dependencies"][0]
        entry = profile["entries"][0]
        if mutation == "seal":
            data["contentHash"] = "bad"
        elif mutation == "path":
            entry["path"] = "../escape"
        elif mutation == "hash":
            entry["hash"] = "bad"
        elif mutation == "native-pin":
            entry["git"]["rev"] = "0" * 40
        elif mutation == "checksum":
            dep["native"]["checksums"]["sha1"] = "0" * 40
        elif mutation == "rawcommit":
            entry["git"]["commitObject"]["object"] = "not base64!"
        elif mutation == "sdk":
            profile["toolVersions"]["sdk"] = "invalid"
        elif mutation == "registry":
            dep["registry"]["url"] = "https://example.com/wrong"
        elif mutation == "alias":
            dep["aliases"] = ["refs/tags/../escape"]
        elif mutation == "native":
            native.write_text('{"version":2,"packages":{},"tasks":{}}\n')
        elif mutation == "missing":
            recipe.unlink()
        elif mutation == "manifest":
            recipe.write_text("changed")
        if mutation != "seal":
            data = lock.seal(data)
        companion.write_text(json.dumps(data))
        assert evaluate()["problems"], mutation
print("Nimble evaluation rejects invalid lock declarations")
