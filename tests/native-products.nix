{ pkgs }:
let
  build =
    src:
    pkgs.nimble-purifier.buildNimbleProject {
      inherit src;
      nativeProducts = {
        answerC = {
          module = "src/api.nim";
          abi = "c";
          exports = [ "nimAnswer" ];
        };
        answerCpp = {
          module = "src/api.nim";
          abi = "c";
          backend = "cpp";
          exports = [ "nimAnswer" ];
        };
        answerArc = {
          module = "src/api.nim";
          abi = "c";
          memoryManager = "arc";
          exports = [ "nimAnswer" ];
        };
        answerArcCpp = {
          module = "src/api.nim";
          abi = "c";
          backend = "cpp";
          memoryManager = "arc";
          exports = [ "nimAnswer" ];
        };
        answerRefc = {
          module = "src/api.nim";
          abi = "c";
          memoryManager = "refc";
          exports = [ "nimAnswer" ];
        };
        answerRefcCpp = {
          module = "src/api.nim";
          abi = "c";
          backend = "cpp";
          memoryManager = "refc";
          exports = [ "nimAnswer" ];
        };
      };
    };
  record =
    src: value:
    let
      built = build src;
    in
    {
      inherit value;
      producer = toString built.packages.native;
      native = toString built.projections.native;
      python = toString built.projections.python-ffi;
      java = toString built.projections.java-ffi;
    };
  reject =
    product:
    !(builtins.tryEval
      (pkgs.nimble-purifier.buildNimbleProject {
        src = ./fixtures/ffi42;
        nativeProducts.answer = product;
      }).packages.native.drvPath
    ).success;
in
assert (pkgs.nimble-purifier.buildNimbleProject { src = ./fixtures/ffi42; }).projections == { };
assert reject {
  module = "../api.nim";
  abi = "c";
  exports = [ "nimAnswer" ];
};
assert reject {
  module = "src/api.nim";
  abi = "nim";
  exports = [ "nimAnswer" ];
};
assert reject {
  module = "src/api.nim";
  abi = "c";
  exports = [ ];
};
assert reject {
  module = "src/api.nim";
  abi = "c";
  exports = [
    "nimAnswer"
    "nimAnswer"
  ];
};
assert reject {
  module = "src/api.nim";
  abi = "c";
  backend = "js";
  exports = [ "nimAnswer" ];
};
pkgs.runCommand "nimble-native-consumers"
  {
    nativeBuildInputs = [
      pkgs.stdenv.cc
      pkgs.pkg-config
      pkgs.jdk25
      (pkgs.python3.withPackages (ps: [ ps.cffi ]))
    ];
    spec = builtins.toJSON {
      versions = [
        (record ./fixtures/ffi42 42)
        (record ./fixtures/ffi43 43)
      ];
    };
    passAsFile = [ "spec" ];
  }
  ''
    python3 ${./native}/proof.py "$specPath" "$out"
  ''
