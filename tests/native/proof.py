import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

spec = json.loads(Path(sys.argv[1]).read_text()); out = Path(sys.argv[2]); out.mkdir()
source = Path(__file__).parent
subprocess.run(["javac", str(source / "Consumer.java"), "-d", "."], check=True)
rows = []
for version, item in enumerate(spec["versions"]):
    producer = Path(item["producer"])
    models = json.loads((producer / "native-products.json").read_text())
    catalog = json.loads((Path(item["native"]) / "catalog.json").read_text())
    assert item["native"] == item["python"] == item["java"]
    assert len(models) == 6 and len(catalog["libraries"]) == 6
    assert {(m["backend"], m["memoryManager"]) for m in models.values()} == {
        (backend, memory) for backend in ["c", "cpp"] for memory in ["orc", "arc", "refc"]}
    python_results = {}
    for method in ["ctypes", "cffi"]:
        result = subprocess.run([sys.executable, str(source / "python-consumer.py"), item["python"],
            str(item["value"]), method], capture_output=True, text=True, check=True, timeout=30)
        assert not result.stderr, result.stderr
        python_results[method] = json.loads(result.stdout)
    per_library = []
    for name, model in models.items():
        library = producer / model["library"]
        assert Path(catalog["libraries"][name]).resolve() == library.resolve()
        assert hashlib.sha256(library.read_bytes()).hexdigest() == model["librarySha256"]
        assert hashlib.sha256((producer / model["header"]).read_bytes()).hexdigest() == model["headerSha256"]
        assert hashlib.sha256((producer / model["nativeHeader"]).read_bytes()).hexdigest() == model["nativeHeaderSha256"]
        assert any(s["kind"] == "project" for s in model["sources"].values())
        assert any(s["kind"] == "dependency" and s["package"] == "results" for s in model["sources"].values())
        assert any(s["kind"] == "sdk" for s in model["sources"].values())
        assert any(s["kind"] == "project" and s["path"] == "src/owned-helper.c" for s in model["compileSources"])
        assert model["runtime"]["lifecycle"] == "process-once" and model["runtime"]["termination"] == "process-lifetime"
        expected_header = model["header"].removeprefix("include/")
        program_source = Path.cwd() / (name + ".c")
        program_source.write_text('''#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "'''+expected_header+'''"
int main(int argc, char **argv) {
  '''+model["init"]+'''();
  int value = atoi(argv[2]);
  if(nimAnswer(0) != value || nimAnswer(1) != value + 2) return 1;
  Dl_info info;
  if(!dladdr((void*)nimAnswer, &info)) return 2;
  char *actual = realpath(info.dli_fname, NULL), *expected = realpath(argv[1], NULL);
  if(!actual || !expected || strcmp(actual, expected)) return 3;
  printf("[%d, %d]\\n", value, value + 2);
  return 0;
}
''')
        env = dict(os.environ, PKG_CONFIG_PATH=":".join(catalog["pkgConfigDirectories"]))
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", name], env=env, text=True))
        compiled = {}
        for compiler in ["cc", "c++"]:
            program = Path.cwd() / (name + "-" + compiler.replace("+", "p"))
            subprocess.run([compiler, str(program_source), *flags, "-Wl,-rpath," + str(library.parent), "-ldl", "-o", str(program)], check=True)
            result = subprocess.check_output([str(program), str(library), str(item["value"])], text=True)
            assert json.loads(result) == [item["value"], item["value"] + 2]
            compiled[compiler] = json.loads(result)
        java = subprocess.check_output(["java", "@" + str(Path(item["java"]) / "java.args"),
            "--enable-native-access=ALL-UNNAMED", "Consumer", str(library), model["init"], str(item["value"])], text=True)
        assert json.loads(java) == [item["value"], item["value"] + 2]
        per_library.append({"name": name, "backend": model["backend"], "init": model["init"],
            "librarySha256": model["librarySha256"], "C": compiled, "JavaFFM": json.loads(java)})
    failed = subprocess.run([sys.executable, str(source / "python-consumer.py"), item["python"],
        str(item["value"]), "no-init"], capture_output=True, text=True, timeout=15)
    assert failed.returncode != 0
    sys.stderr.write(failed.stderr)
    rows.append({"value": item["value"], "producerIdentity": catalog["producer"], "libraries": per_library,
        "Python": python_results, "noInitExitCode": failed.returncode})
assert rows[0]["producerIdentity"] != rows[1]["producerIdentity"]
assert len({l["init"] for r in rows for l in r["libraries"]}) == 12
assert all(a["librarySha256"] != b["librarySha256"] for a, b in zip(rows[0]["libraries"], rows[1]["libraries"]))
(out / "proof.json").write_text(json.dumps({"versions": rows, "controls": {
    "missingInit": "native managed module cannot execute before its initializer",
    "changedSource": "independent native43/45 library bytes and identities differ from42/44"}}, sort_keys=True, indent=2) + "\n")
print("Native Nim C/C++ / C+pkg-config / ctypes+CFFI / Java FFM consumers and initialization controls passed")
