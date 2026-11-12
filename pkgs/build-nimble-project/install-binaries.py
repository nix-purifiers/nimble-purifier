# SPDX-License-Identifier: MIT
import json, shutil, sys
from pathlib import Path

metadata = json.loads(Path(sys.argv[1]).read_text())
out = Path(sys.argv[2])
(out / "bin").mkdir(parents=True)
for binary in metadata["profile"]["binaries"]:
    source = Path(binary)
    if not source.is_file():
        raise ValueError("native binary missing: " + binary)
    shutil.copyfile(source, out / "bin" / source.name)
    (out / "bin" / source.name).chmod(0o755)
