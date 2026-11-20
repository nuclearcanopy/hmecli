{
  description = "hmecli: generate iCloud Hide My Email aliases from the CLI";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      overlays.default = final: _prev: { hmecli = final.callPackage ./package.nix { }; };

      packages = forAllSystems (pkgs: rec {
        hmecli = pkgs.callPackage ./package.nix { };
        default = hmecli;
      });

      apps = forAllSystems (pkgs: {
        default = {
          type = "app";
          program = nixpkgs.lib.getExe self.packages.${pkgs.stdenv.hostPlatform.system}.hmecli;
          meta.description = "Generate iCloud Hide My Email aliases";
        };
      });

      checks = forAllSystems (pkgs: {
        inherit (self.packages.${pkgs.stdenv.hostPlatform.system}) hmecli;
      });

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [ (pkgs.python3.withPackages (ps: [ ps.browser-cookie3 ])) ];
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
