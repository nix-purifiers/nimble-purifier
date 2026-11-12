# SPDX-License-Identifier: MIT
import json, shutil, sys
from pathlib import Path

metadata = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
destination = out / ("share/nimble-js" if metadata["profile"].get("backend", "c") == "js" else "bin")
destination.mkdir(parents=True)
for binary in metadata["profile"]["binaries"]:
    source = Path(binary)
    if not source.is_file():
        raise ValueError("native binary missing: " + binary)
    shutil.copyfile(source, destination / source.name)
    (destination / source.name).chmod(0o644 if metadata["profile"].get("backend", "c") == "js" else 0o755)
