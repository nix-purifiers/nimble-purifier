{
  lib,
  stdenv,
  runCommand,
  writeText,
  python3,
  nim,
  toolchain,
  binutils,
  purifier,
}:
{
  nativeProducts,
  source,
  environment,
  nativeBuildInputs ? [ ],
}:
let
  symbol = value: builtins.isString value && builtins.match "[A-Za-z_][A-Za-z0-9_]*" value != null;
  label =
    value: builtins.isString value && builtins.match "[A-Za-z0-9_][A-Za-z0-9_.+-]*" value != null;
  relative =
    path:
    builtins.isString path
    && path != ""
    && !(lib.hasPrefix "/" path)
    && !(lib.hasInfix "\\" path)
    && builtins.all (part: part != "" && part != "." && part != "..") (lib.splitString "/" path);
  valid =
    p:
    builtins.isAttrs p
    && builtins.all (
      key:
      builtins.elem key [
        "module"
        "abi"
        "backend"
        "exports"
        "memoryManager"
      ]
    ) (builtins.attrNames p)
    && (p.abi or null) == "c"
    && relative (p.module or null)
    && lib.hasSuffix ".nim" p.module
    && builtins.elem (p.backend or "c") [
      "c"
      "cpp"
    ]
    && builtins.elem (p.memoryManager or "orc") [
      "orc"
      "arc"
      "refc"
    ]
    && builtins.isList (p.exports or null)
    && p.exports != [ ]
    && lib.unique p.exports == p.exports
    && builtins.all symbol p.exports;
  validated =
    builtins.isAttrs nativeProducts
    && nativeProducts != { }
    && builtins.all (name: label name && valid nativeProducts.${name}) (
      builtins.attrNames nativeProducts
    );
  products = lib.mapAttrs (name: p: {
    inherit (p) module exports;
    abi = "c";
    backend = p.backend or "c";
    memoryManager = p.memoryManager or "orc";
    prefix = "nimble_${
      builtins.substring 0 32 (
        builtins.hashString "sha256" "${source}:${environment}:${nim}:${name}:${builtins.toJSON p}"
      )
    }_";
  }) nativeProducts;
  spec = writeText "nimble-native-products.json" (builtins.toJSON products);
  producer =
    runCommand "nimble-native-products"
      {
        nativeBuildInputs = [
          toolchain
          python3
          binutils
        ]
        ++ nativeBuildInputs;
      }
      ''
        export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/cache" XDG_CONFIG_HOME="$TMPDIR/config"
        export NIMBLE_DIR="$TMPDIR/nimble" NIMBLE_PURIFIER_DIR="$TMPDIR/nimble" NIMBLE_PURIFIER_SYNC_FILE="$TMPDIR/sync.json"
        export PYTHONDONTWRITEBYTECODE=1 SOURCE_DATE_EPOCH=1
        export NIMBLE_PURIFIER_ENVIRONMENT=${environment}
        mkdir -p "$HOME" "$NIMBLE_DIR" "$out/project"
        ln -s ${environment}/pkgs2 "$NIMBLE_DIR/pkgs2"
        ln -s ${environment}/bin "$NIMBLE_DIR/bin"
        cp ${environment}/packages_official.json "$NIMBLE_DIR/packages_official.json"
        cp -r ${source}/. "$out/project/"
        chmod -R u+w "$out/project"
        python3 -c 'import json,sys; sys.stdout.write(json.load(open(sys.argv[1]))["profile"]["nativeLock"])' ${environment}/metadata.json > "$NIMBLE_DIR/nimble.lock"
        export NIMBLE_PURIFIER_NATIVE_LOCKFILE="$NIMBLE_DIR/nimble.lock"
        cd "$out/project"
        nimble -y setup
        python3 ${./native-products.py} "$out" ${environment} ${spec} ${nim}/bin/nim ${binutils}/bin/nm ${stdenv.cc}/bin/cc
      '';
  projections = purifier.nativeProjections {
    inherit producer runCommand python3;
    system = stdenv.hostPlatform.system;
    libraries = lib.mapAttrs (name: _: "lib/lib${name}.so") products;
    includeDirectories = [ "include" ];
    pkgConfigDirectories = [ "lib/pkgconfig" ];
    targetMetadata = lib.mapAttrs (
      _: p:
      p
      // {
        type = "shared-library";
        nativeModel = "${producer}/native-products.json";
        runtime = {
          kind = "nim";
          init = "${p.prefix}NimMain";
          lifecycle = "process-once";
          threading = "single-foreign-thread";
          termination = "process-lifetime";
        };
      }
    ) products;
  };
in
assert lib.assertMsg validated
  "nimble-purifier: nativeProducts requires owned .nim modules, explicit C ABI exports, c/cpp backend and orc/arc/refc memory manager";
assert lib.assertMsg (
  stdenv.hostPlatform.isLinux && stdenv.buildPlatform == stdenv.hostPlatform
) "nimble-purifier: nativeProducts requires native Linux";
{
  inherit producer projections;
  validated = true;
}
