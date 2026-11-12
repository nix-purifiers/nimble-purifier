#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Real native builds reject borrowed entries, missing exports and non-C APIs."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="nimble-native-reject-") as scratch:
    scratch = Path(scratch)
    expression = f'''let f=builtins.getFlake {json.dumps('git+file://'+str(repo))};
      p=import f.inputs.nixpkgs {{system=builtins.currentSystem;}};
      in "${{p.nim}}/bin/nim"'''
    nim = subprocess.check_output(["nix", "eval", "--impure", "--raw", "--expr", expression], text=True).strip()
    dummy = scratch / "sdk.nim"; dummy.write_text("discard\n")
    sdk = json.loads(subprocess.check_output([nim, "dump", "--dump.format:json", "--verbosity:0", str(dummy)],
                                           cwd=scratch, text=True))
    for label, module, exports, expected in [
        ("test-entry", "tests/test.nim", ["nimAnswer"], "not a project production source"),
        ("sdk-symlink-entry", "src/borrowed.nim", ["nimAnswer"], "not a project production source"),
        ("missing-export", "src/api.nim", ["absentAnswer"], "absent from native ELF"),
        ("non-cdecl-export", "src/api.nim", ["nimAnswer"], "no native cdecl header declaration"),
    ]:
        source = scratch / label
        shutil.copytree(repo / "tests/fixtures/ffi42", source)
        if label == "sdk-symlink-entry":
            (source / "src/borrowed.nim").symlink_to(Path(sdk["libpath"]) / "system.nim")
        if label == "non-cdecl-export":
            path = source / "src/api.nim"
            path.write_text(path.read_text().replace("cdecl, exportc", "nimcall, exportc"))
        product = {"module": module, "abi": "c", "exports": exports}
        expression = f'''let f=builtins.getFlake {json.dumps('git+file://'+str(repo))};
          p=import f.inputs.nixpkgs {{system=builtins.currentSystem;overlays=[f.overlays.default];}};
          in (p.nimble-purifier.buildNimbleProject {{
            src=builtins.path {{path=builtins.toPath {json.dumps(str(source))};name="native-negative-source";}};
            nativeProducts.bad=builtins.fromJSON {json.dumps(json.dumps(product))};
          }}).packages.native'''
        result = subprocess.run(["nix", "build", "--impure", "--no-link", "-L", "--expr", expression],
                                capture_output=True, text=True, timeout=180)
        assert result.returncode != 0 and expected in result.stderr, (label, result.stdout, result.stderr)
        print(json.dumps({"case": label, "exitCode": result.returncode, "expectedDiagnostic": expected}), flush=True)
print("Native production-entry, SDK ownership and explicit C ABI controls passed")
