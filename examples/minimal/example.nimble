version = "0.1.0"
author = "the nix-purifier developers"
description = "Locked Nimble example"
license = "MIT"
srcDir = "src"
bin = @["example"]
requires "nim >= 2.2.0", "results == 0.5.1"

task test, "Test the locked dependency":
  exec "nim c -r tests/test.nim"
