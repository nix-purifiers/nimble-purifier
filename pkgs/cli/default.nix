# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  stdenv,
  makeWrapper,
  python3,
  nix,
  gh,
  nativeNimble,
  toolchain,
  cacert,
  nim,
  nixpkgsSrc,
  purifierSrc,
}:
let
  python = python3;
in
stdenvNoCC.mkDerivation {
  pname = "nimble-purifier";
  version = "0.1.0";
  src = ../..;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/nimble-purifier"
    cp -r nimble_purifier pkgs lib-overlays "$out/lib/nimble-purifier/"
    install -m755 bin/nimble-purifier "$out/bin/nimble-purifier"
    substituteInPlace "$out/lib/nimble-purifier/pkgs/build-nimble-project/realize.nix" \
      --replace-fail '@nixpkgs@' '${nixpkgsSrc}' \
      --replace-fail '@purifier@' '${purifierSrc}'
    wrapProgram "$out/bin/nimble-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python
          nix
          gh
          toolchain
        ]
      } \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set NIMBLE_PURIFIER_NATIVE ${nativeNimble}/bin/nimble \
      --set NIMBLE_PURIFIER_SYSTEM ${stdenv.hostPlatform.system} \
      --set NIMBLE_PURIFIER_NIM_VERSION ${nim.version} \
      --set NIMBLE_PURIFIER_NIMBLE_VERSION ${nativeNimble.version}
    makeWrapper "$out/bin/nimble-purifier" "$out/bin/nimble" --add-flags '--native --'
    for program in ${toolchain}/bin/*; do
      name=$(basename "$program")
      if [ ! -e "$out/bin/$name" ]; then ln -s "$program" "$out/bin/$name"; fi
    done
  '';
  meta = {
    description = "Native Nimble workflow with locked Nix-resolved dependencies";
    homepage = "https://nix-purifiers.github.io/";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    mainProgram = "nimble-purifier";
  };
}
