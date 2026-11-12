# SPDX-License-Identifier: MIT
{
  description = "Locked, Nix-resolved dependencies for Nimble";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier/v0.1.63";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        nimble-purifier = final.lib.makeScope final.newScope (scope: {
          nativeNimble = scope.callPackage ./pkgs/build-nimble-project/nimble.nix { };
          nativeNimlangserver = scope.callPackage ./pkgs/build-nimble-project/nimlangserver.nix { };
          toolchain = scope.callPackage ./pkgs/build-nimble-project/toolchain.nix { };
          cli = scope.callPackage ./pkgs/cli/default.nix {
            nixpkgsSrc = nixpkgs;
            purifierSrc = purifier;
          };
          buildNimbleProject = scope.callPackage ./pkgs/build-nimble-project/default.nix {
            purifier = import (purifier + "/nix/lib") { inherit (final) lib; };
          };
        });
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (system: {
        native = (pkgsFor system).nimble-purifier.nativeNimble;
        default = (pkgsFor system).nimble-purifier.cli;
        cli = self.packages.${system}.default;
      });
      lib.nimble-purifier = (nixpkgs.lib.extend (import ./lib-overlays/default)).nimble-purifier;
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/nimble-purifier";
          meta.description = "Lock and prefetch Nimble dependencies";
        };
      });
      checks = forAll (
        system:
        import ./tests {
          pkgs = pkgsFor system;
          inherit self;
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}
