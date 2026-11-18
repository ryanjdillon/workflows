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

      # The path of a check's script in this repo.
      script = name: "${self}/${name}/${name}.py";

      package =
        pkgs: name:
        pkgs.writeShellApplication {
          inherit name;
          runtimeInputs = [ pkgs.python3 ];
          text = ''
            exec python3 ${script name} "$@"
          '';
        };

      # A flake check that runs a check's script on the given arguments.
      flakeCheck =
        name:
        { pkgs, arguments }:
        pkgs.runCommand name { nativeBuildInputs = [ pkgs.python3 ]; } ''
          python3 ${script name} ${pkgs.lib.escapeShellArgs arguments}
          touch "$out"
        '';
    in
    {
      packages = forAllSystems (pkgs: {
        check-instructions = package pkgs "check-instructions";
        check-process-noise = package pkgs "check-process-noise";
        check-commit-facts = package pkgs "check-commit-facts";
        check-skills = package pkgs "check-skills";
        check-conventional-commits = package pkgs "check-conventional-commits";
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
        flakeCheck "check-instructions" {
          inherit pkgs;
          arguments = args ++ files;
        };

      # Give the files: the Nix sandbox has no git, so the script cannot list
      # the tracked files.
      #   processNoise = workflows.lib.checkProcessNoise {
      #     inherit pkgs; files = [ ./src/main.py ];
      #   };
      lib.checkProcessNoise =
        {
          pkgs,
          files,
          args ? [ ],
        }:
        flakeCheck "check-process-noise" {
          inherit pkgs;
          arguments = args ++ files;
        };

      # Checks commit message files. The Nix sandbox has no git history. To
      # check the commits of a branch, use the action or the prek hook.
      lib.checkCommitFacts =
        {
          pkgs,
          files,
          args ? [ ],
        }:
        flakeCheck "check-commit-facts" {
          inherit pkgs;
          arguments = args ++ files;
        };

      #   skills = workflows.lib.checkSkills {
      #     inherit pkgs; roots = [ ./skills ];
      #   };
      lib.checkSkills =
        {
          pkgs,
          roots,
          args ? [ ],
        }:
        flakeCheck "check-skills" {
          inherit pkgs;
          arguments = args ++ roots;
        };

      # Checks commit message files, and a PR title with
      # `args = [ "--title" title ]`. The Nix sandbox has no git history. To
      # check the commits of a branch, use the action or the prek hook.
      lib.checkConventionalCommits =
        {
          pkgs,
          files ? [ ],
          args ? [ ],
        }:
        flakeCheck "check-conventional-commits" {
          inherit pkgs;
          arguments = args ++ files;
        };

      checks = forAllSystems (pkgs: {
        check-instructions-adapter = self.lib.checkInstructions {
          inherit pkgs;
          files = [ ./check-instructions/testdata/pass/AGENTS.md ];
        };
        check-process-noise-adapter = self.lib.checkProcessNoise {
          inherit pkgs;
          files = [ ./check-process-noise/testdata/pass/clean.py ];
        };
        check-commit-facts-adapter = self.lib.checkCommitFacts {
          inherit pkgs;
          files = [
            ./check-commit-facts/testdata/pass/no-part.txt
            ./check-commit-facts/testdata/pass/sourced.txt
          ];
        };
        check-skills-adapter = self.lib.checkSkills {
          inherit pkgs;
          roots = [ ./check-skills/testdata/pass/skills ];
        };
        check-conventional-commits-adapter = self.lib.checkConventionalCommits {
          inherit pkgs;
          files = [
            ./check-conventional-commits/testdata/pass/breaking.txt
            ./check-conventional-commits/testdata/pass/comments.txt
            ./check-conventional-commits/testdata/pass/scope.txt
          ];
        };
      });

      # Only the toolchain and the hook runner. CI pins the other tools.
      # nix.yml tests nix-devshell-check.yml in this shell.
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.python3
            pkgs.prek
          ];
        };
      });

      formatter = forAllSystems (pkgs: pkgs.nixfmt);
    };
}
