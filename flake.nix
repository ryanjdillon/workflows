{
  description = "Reusable CI checks, with adapters to run them locally";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: {
        check-instructions = pkgs.writeShellApplication {
          name = "check-instructions";
          runtimeInputs = [ pkgs.python3 ];
          text = ''
            exec python3 ${self}/check-instructions/check-instructions.py "$@"
          '';
        };
      });

      # For a consumer's flake `checks`:
      #   instructions = workflows.lib.checkInstructions {
      #     inherit pkgs; files = [ ./AGENTS.md ];
      #   };
      lib.checkInstructions =
        {
          pkgs,
          files,
          args ? [ ],
        }:
        pkgs.runCommand "check-instructions" { nativeBuildInputs = [ pkgs.python3 ]; } ''
          python3 ${self}/check-instructions/check-instructions.py \
            ${pkgs.lib.escapeShellArgs args} ${pkgs.lib.escapeShellArgs files}
          touch "$out"
        '';

      checks = forAllSystems (pkgs: {
        check-instructions-adapter = self.lib.checkInstructions {
          inherit pkgs;
          files = [ ./check-instructions/testdata/pass/AGENTS.md ];
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
