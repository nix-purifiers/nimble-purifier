# SPDX-License-Identifier: MIT
{
  lib,
  callPackage,
  runCommand,
  fetchgit,
  python3,
  writeText,
  nativeNimble,
  toolchain,
  nim,
  stdenv,
  purifier,
  gnutar,
  gzip,
}:
{
  src,
  lockFile ? src + "/nimble-purifier.lock.json",
  nimbleLock ? src + "/nimble.lock",
  fetchers ? { },
  nativeBuildInputs ? [ ],
  nativeProducts ? { },
  doCheck ? true,
  buildCommand ? ''
    nimble -y build
  '',
  installCommand ? ''
    python3 ${./install-binaries.py} "$NIMBLE_PURIFIER_ENVIRONMENT/metadata.json" "$out"
  '',
  srcFilter ?
    path: type:
    !(builtins.elem (baseNameOf path) [
      ".git"
      ".nimble-purifier"
      "nimbledeps"
      "nimble.paths"
      "nimcache"
      "result"
      "__pycache__"
    ]),
}:
let
  lock = purifier.checkLock (
    import ./read-lock.nix { inherit lib; } { inherit src lockFile nimbleLock; }
  );
  environment = import ./environment.nix {
    inherit
      lib
      runCommand
      fetchgit
      python3
      writeText
      nativeNimble
      toolchain
      nim
      stdenv
      purifier
      ;
  } { inherit lock fetchers nativeBuildInputs; };
  binaryPaths = lib.unique (lib.concatMap (p: p.binaries) (builtins.attrValues lock.data.profiles));
  source = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      srcFilter path type
      && !(type == "regular" && builtins.pathExists (path + ".nim"))
      && !(builtins.elem (lib.removePrefix ((toString src) + "/") path) binaryPaths);
  };
  rawProject =
    runCommand "purified-nimble-project"
      {
        nativeBuildInputs = [
          toolchain
          python3
        ]
        ++ nativeBuildInputs;
      }
      ''
        export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/cache" XDG_CONFIG_HOME="$TMPDIR/config"
        export NIMBLE_DIR="$TMPDIR/nimble" NIMBLE_PURIFIER_DIR="$TMPDIR/nimble" NIMBLE_PURIFIER_SYNC_FILE="$TMPDIR/sync.json"
        export PYTHONDONTWRITEBYTECODE=1 SOURCE_DATE_EPOCH=1
        export NIMBLE_PURIFIER_ENVIRONMENT=${environment}
        mkdir -p "$HOME" "$NIMBLE_DIR" project
        ln -s ${environment}/pkgs2 "$NIMBLE_DIR/pkgs2"
        ln -s ${environment}/bin "$NIMBLE_DIR/bin"
        cp ${environment}/packages_official.json "$NIMBLE_DIR/packages_official.json"
        cp -r ${source}/. project/
        chmod -R u+w project
        cd project
        python3 -c 'import json,sys; sys.stdout.write(json.load(open(sys.argv[1]))["profile"]["nativeLock"])' ${environment}/metadata.json > "$NIMBLE_DIR/nimble.lock"
        chmod u+w "$NIMBLE_DIR/nimble.lock"
        export NIMBLE_PURIFIER_NATIVE_LOCKFILE="$NIMBLE_DIR/nimble.lock"
        nimble -y setup
        ${buildCommand}
        ${lib.optionalString doCheck "nimble -y test"}
        ${installCommand}
      '';
  native = callPackage ./build-native-products.nix { inherit purifier nim toolchain; } {
    inherit nativeProducts source environment nativeBuildInputs;
  };
  projections = if nativeProducts == { } then { } else native.projections;
  project = rawProject // { inherit projections; };
  release =
    runCommand "nimble-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        mkdir source "$out"
        cp -r ${source}/. source/
        chmod -R u+w source
        cp ${lockFile} source/nimble-purifier.lock.json
        cp ${nimbleLock} source/nimble.lock
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -C source -cf - . | gzip -n > "$out/project.tar.gz"
      '';
in
assert nativeProducts == { } || native.validated;
{
  packages = {
    inherit environment project;
    default = project;
  } // lib.optionalAttrs (nativeProducts != { }) { native = native.producer; };
  inherit projections;
  tests = project;
  inherit release;
  fetches = lock.entries;
}
