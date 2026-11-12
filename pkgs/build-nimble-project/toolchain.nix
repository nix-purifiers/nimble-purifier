# SPDX-License-Identifier: MIT
{
  buildEnv,
  nativeNimble,
  nim,
  nativeNimlangserver,
  stdenv,
  gnumake,
  pkg-config,
  git,
  coreutils,
}:
buildEnv {
  name = "nimble-purifier-toolchain";
  paths = [
    nativeNimble
    nim
    nativeNimlangserver
    stdenv.cc
    gnumake
    pkg-config
    git
    coreutils
  ];
  ignoreCollisions = true;
}
