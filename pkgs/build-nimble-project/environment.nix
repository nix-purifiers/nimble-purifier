# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  fetchgit,
  python3,
  writeText,
  nativeNimble,
  toolchain,
  nim,
  stdenv,
  purifier,
}:
{
  lock,
  fetchers ? { },
  nativeBuildInputs ? [ ],
}:
let
  checked = purifier.checkLock lock;
  profile =
    checked.data.profiles.${stdenv.hostPlatform.system}
      or (throw "nimble-purifier: generate a native profile on ${stdenv.hostPlatform.system}");
  sources = purifier.tree (
    {
      name = "locked-nimble-sources";
      entries = profile.entries;
      inherit
        runCommand
        fetchgit
        python3
        writeText
        ;
    }
    // fetchers
  );
  metadata = writeText "nimble-build-inputs.json" (
    builtins.toJSON {
      inherit profile;
      inherit (checked.data) manifests inputs;
    }
  );
in
assert lib.assertMsg (
  profile.toolVersions.nim == nim.version
  && profile.toolVersions.nimble == nativeNimble.version
  && profile.toolVersions.sdk == builtins.hashFile "sha256" ./nimble.patch
) "nimble-purifier: native SDK changed; run nimble-purifier lock";
runCommand "purified-nimble-environment"
  {
    nativeBuildInputs = [
      toolchain
      python3
    ]
    ++ nativeBuildInputs;
  }
  ''
    export PYTHONDONTWRITEBYTECODE=1
    python3 ${../../nimble_purifier}/build.py ${metadata} ${sources} "$out"
    ln -s ${toolchain} "$out/sdk"
    ln -s ${sources} "$out/sources"
  ''
