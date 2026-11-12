# SPDX-License-Identifier: MIT
{ pkgs, self }:
let
  built = pkgs.nimble-purifier.buildNimbleProject { src = ../examples/minimal; };
in
{
  cli = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
  environment = built.packages.environment;
  project = built.tests;
  release = built.release;
  browser-products = import ./browser-products.nix { inherit pkgs; };
  native-products = import ./native-products.nix { inherit pkgs; };
}
