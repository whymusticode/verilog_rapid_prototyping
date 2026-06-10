{
  description = "py2v dev environment (Python + Anthropic SDK)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python3.withPackages (ps: with ps; [
          anthropic
          pyyaml
          numpy
        ]);
      in {
        devShells.default = pkgs.mkShell {
          packages = [ python ];
        };
      });
}
