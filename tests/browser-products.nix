# SPDX-License-Identifier: MIT
{ pkgs }:
let
  build = src: version: pkgs.nimble-purifier.buildNimbleProject {
    inherit src;
    browserProducts.answer = {
      module = "src/browser.nim";
      webjar = { artifactId = "nim-answer"; inherit version; };
    };
  };
  a = build ./fixtures/js42 "0.1.0";
  b = build ./fixtures/js43 "0.2.0";
  nativeOnly = pkgs.nimble-purifier.buildNimbleProject {
    src = ./fixtures/js42;
    nativeProducts.browser = { module="src/api.nim";abi="c";exports=["nimAnswer"]; };
  };
  combined = pkgs.nimble-purifier.buildNimbleProject {
    src = ./fixtures/js42;
    nativeProducts.browser = { module="src/api.nim";abi="c";exports=["nimAnswer"]; };
    browserProducts.answer = { module="src/browser.nim";webjar={artifactId="nim-answer";version="0.1.0";}; };
  };
  nativeJs = pkgs.nimble-purifier.buildNimbleProject {
    src = ./fixtures/native-js42; doCheck = false;
  };
  reject = product: !(builtins.tryEval (pkgs.nimble-purifier.buildNimbleProject {
    src = ./fixtures/js42; browserProducts.answer = product;
  }).packages.browser.drvPath).success;
  consume = built: value: ''
    cat > index.html <<'HTML'
    <script src="${built.projections.browser.answer.web.documentRoot}/main.js"></script>
    <script>document.documentElement.setAttribute("data-answer", String(globalThis.nimAnswer(1)))</script>
HTML
    chromium --headless --user-data-dir="$TMPDIR/chromium-${toString value}" --no-sandbox --disable-dev-shm-usage --disable-gpu --dump-dom "file://$PWD/index.html" > browser.html
    grep -q 'data-answer="${toString (value+2)}"' browser.html
    node -e 'require("${built.packages.browser}/assets/answer/main.js"); if(globalThis.nimAnswer(0)!==${toString value} || globalThis.nimAnswer(1)!==${toString (value+2)}) process.exit(1);'
    java Resources ${built.projections.browser.answer.java-resources.classPath} ${built.packages.browser}/assets/answer
    for jar in $(find ${built.projections.browser.answer.maven} -name '*.jar'); do
      prefix=$(jar tf "$jar" | sed -n 's@/main.js$@/@p')
      test -n "$prefix"
      java Resources "$jar" ${built.packages.browser}/assets/answer "$prefix"
    done
  '';
in
assert builtins.attrNames combined.projections == ["browser" "java-ffi" "native" "python-ffi"];
assert combined.projections.native.drvPath == nativeOnly.projections.native.drvPath;
assert combined.projections.browser.answer.web.drvPath == a.projections.browser.answer.web.drvPath;
assert reject { module = "../browser.nim"; };
assert reject { module = "/tmp/browser.nim"; };
assert reject { module = "src/browser.nim"; flags = [ "--danger" ]; };
assert reject { module = "src/browser.nim"; webjar = { artifactId="answer"; version="1"; producer="other"; }; };
assert a.packages.project.drvPath == (pkgs.nimble-purifier.buildNimbleProject {src=./fixtures/js42;}).packages.project.drvPath;
pkgs.runCommand "nimble-browser-consumers" {
  nativeBuildInputs = [ pkgs.nodejs pkgs.jdk pkgs.python3 pkgs.chromium ];
} ''
  export HOME="$TMPDIR/home"
  mkdir -p "$HOME"
  cp ${../pkgs/nimble-browser-products/Resources.java} Resources.java
  javac Resources.java -d .
  ${consume a 42}
  ${consume b 43}
  ${pkgs.lib.optionalString (pkgs.stdenv.hostPlatform.system == "x86_64-linux") ''
    test "$(node ${nativeJs.packages.project}/share/nimble-js/example.js)" = "locked Nimble 42"
  ''}
  mkdir "$out"
  cp ${a.packages.browser}/browser-products.json "$out/source42.json"
  cp ${b.packages.browser}/browser-products.json "$out/source43.json"
  python3 - ${a.packages.browser} ${b.packages.browser} <<'PY'
import json,sys
from pathlib import Path
models=[json.loads((Path(p)/'browser-products.json').read_text())['answer'] for p in sys.argv[1:]]
assert models[0]['sha256'] != models[1]['sha256']
for m in models:
    assert any(s['kind']=='dependency' and s['package']=='results' for s in m['sources'])
    assert any(s['kind']=='sdk' for s in m['sources'])
PY
''
