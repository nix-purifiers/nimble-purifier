# SPDX-License-Identifier: MIT
{
  project,
  nativeLock,
  companion,
  target,
}:
let
  pkgs = import (/. + "@nixpkgs@") { };
  purifier = import (/. + "@purifier@/nix/lib") { inherit (pkgs) lib; };
  nativeNimble = pkgs.callPackage ./nimble.nix { };
  nativeNimlangserver = pkgs.callPackage ./nimlangserver.nix { };
  toolchain = pkgs.callPackage ./toolchain.nix { inherit nativeNimble nativeNimlangserver; };
  args = {
    src = /. + project;
    lockFile = /. + companion;
    nimbleLock = /. + nativeLock;
  };
  lock = import ./read-lock.nix { inherit (pkgs) lib; } args;
in
if target == "environment" then
  pkgs.callPackage ./environment.nix { inherit purifier nativeNimble toolchain; } { inherit lock; }
else if target == "release" then
  (pkgs.callPackage ./build-project.nix { inherit purifier nativeNimble toolchain; } args).release
else
  throw "nimble-purifier: unknown target"
