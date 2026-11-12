# SPDX-License-Identifier: MIT
{ lib, runCommand, writeText, python3, nim, toolchain, purifier }:
{ browserProducts, source, environment, nativeBuildInputs ? [ ] }:
let
  relative = p: builtins.isString p && p != "" && !(lib.hasPrefix "/" p)
    && !(lib.hasInfix "\\" p) && builtins.all (s: s != "" && s != "." && s != "..") (lib.splitString "/" p);
  valid = p: builtins.isAttrs p && builtins.attrNames (removeAttrs p [ "module" "webjar" ]) == [ ]
    && relative (p.module or null) && lib.hasSuffix ".nim" p.module
    && (!(p ? webjar) || (builtins.isAttrs p.webjar && p.webjar ? artifactId && p.webjar ? version
      && builtins.attrNames (removeAttrs p.webjar [ "groupId" "artifactId" "version" ]) == [ ]));
  validated = builtins.isAttrs browserProducts && browserProducts != { }
    && builtins.all (name: builtins.match "[A-Za-z0-9_][A-Za-z0-9_.+-]*" name != null
      && valid browserProducts.${name}) (builtins.attrNames browserProducts);
  spec = writeText "nimble-browser-products.json" (builtins.toJSON browserProducts);
  producer = runCommand "nimble-browser-products" {
    nativeBuildInputs = [ toolchain python3 ] ++ nativeBuildInputs;
  } ''
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
    python3 ${./build.py} "$out" ${environment} ${spec} ${nim}/bin/nim
  '';
  projections = lib.mapAttrs (name: p:
    purifier.resourceProjections {
      inherit producer runCommand python3;
      name = "nimble-${name}-browser-resources";
      roots."." = "assets/${name}";
    } // (if p ? webjar then purifier.webjarProjections ({
      inherit producer runCommand python3;
      name = "nimble-${name}-browser-webjar";
      assets = "${producer}/assets/${name}";
    } // p.webjar) else { })
  ) browserProducts;
in
assert lib.assertMsg validated "nimble-purifier: browserProducts requires owned .nim modules and optional WebJar coordinates";
{ inherit producer projections; validated = true; }
