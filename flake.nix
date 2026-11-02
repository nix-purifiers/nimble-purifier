# SPDX-License-Identifier: MIT
{
  description = "Locked, Nix-resolved dependencies for Nimble";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
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
          nativeNimble = scope.callPackage ./nix/nimble.nix { };
          nativeNimlangserver = scope.callPackage ./nix/nimlangserver.nix { };
          toolchain = scope.callPackage ./nix/toolchain.nix { };
          cli = scope.callPackage ./nix/cli.nix {
            nixpkgsSrc = nixpkgs;
            purifierSrc = purifier;
          };
          buildNimbleProject = scope.callPackage ./nix/build-project.nix {
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
      lib.nimble-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
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
