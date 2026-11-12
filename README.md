# nimble-purifier

Locked, Nix-resolved dependencies for Nimble.

## Quickstart

From the project root:

```sh
nix shell 'github:nix-purifiers/nimble-purifier'
nimble-purifier lock
nimble-purifier prefetch
nimble build
nimble test
```

Prefetch prepares Nimble's normal `config.nims` and `nimble.paths`
integration, including task dependencies. The shell supplies Nim, Nimble,
the C/C++ compiler and nimlangserver. You can install the wrapper through
your usual Nix configuration.

Commit `nimble.lock` and `nimble-purifier.lock.json`; ignore
`.nimble-purifier/`, `nimble.paths` and generated executables.
Without a companion lock, the wrapper warns on standard error and runs
ordinary, impure Nimble with its normal configuration. Invalid or stale
locks fail with a repair instruction.

## Lock and update

```sh
nimble-purifier lock
nimble-purifier update results
nimble-purifier update
```

Native Nimble selects versions, exact Git revisions, checksums and task
requirements. The companion records those selections and source-tree
hashes. Host-built packages are excluded. Nix fetches the pinned Git trees
and runs native Nimble offline to prepare the complete dependency graph.

`lock` retains compatible native selections. Named updates use Nimble's
native `lock --refresh NAME`; an unnamed update refreshes the graph within
the manifest's requirements.

Development commands use a private native directory backed by immutable
Nix packages. Existing global caches and local `nimbledeps` directories
cannot replace them. Task subprocesses inherit the same lock, directory
and offline mode. Application source edits do not rebuild dependencies;
manifest changes require relocking.

## Editor and compiler

After prefetch, use the normal compiler and editor commands:

```sh
nim check src/example.nim
nimlangserver
```

Nim reads the native project configuration and locked dependency paths.
The setup preserves custom content in an existing `config.nims`.

## External locks

```sh
nimble-purifier \
  --project ./app \
  --lockfile ./locks/companion.json \
  --tool-lockfile ./locks/nimble.lock \
  lock

export NIMBLE_PURIFIER_LOCKFILE="$PWD/locks/companion.json"
export NIMBLE_PURIFIER_TOOL_LOCKFILE="$PWD/locks/nimble.lock"
cd app
nimble build
```

The working tree's native lock remains untouched. `--native-lock` and
`NIMBLE_PURIFIER_NATIVE_LOCKFILE` are equivalent native-lock selectors.
Compatible platform profiles are retained in one companion; run `lock`
on each platform you use.

## Nix builds

The overlay exposes `pkgs.nimble-purifier.buildNimbleProject`:

```nix
pkgs.nimble-purifier.buildNimbleProject {
  src = ./.;
}
```

It returns `packages`, `tests`, `release` and `fetches`.
`packages.environment` prepares dependencies; `packages.project` builds,
tests and installs declared executables. `lockFile`, `nimbleLock`,
`nativeBuildInputs`, `fetchers`, `srcFilter`, `doCheck`, `buildCommand` and
`installCommand` customize the build. Output names are available during
evaluation without building dependencies.

### Native libraries for C, Python and Java

Select explicit C ABI modules from the native package's source directory:

```nix
pkgs.nimble-purifier.buildNimbleProject {
  src = ./.;
  nativeProducts.answer = {
    module = "src/api.nim";
    abi = "c";
    exports = [ "nimAnswer" ];
    backend = "c"; # or "cpp"
    memoryManager = "orc"; # also "arc" or "refc"
  };
}
```

Declare the functions' C ABI in the project, for example:

```nim
proc nimAnswer(input: cint): cint {.cdecl, exportc, dynlib.} =
  input + 42
```

`packages.native` contains the compiled libraries, headers, pkg-config files
and `native-products.json`. The compiler uses the captured Nimble paths and
the pinned native SDK. Project-owned C/C++ helpers compiled by Nim remain part
of that native build. Imported Nim sources and backend units are checked
against project, captured-package and SDK ownership.

`projections.native`, `projections.python-ffi` and `projections.java-ffi` expose
the native libraries through the shared catalog. The Python view supplies
`purifier_native.load(name)`; the Java view supplies `java.args`. Callers use
compatible ctypes/CFFI or JNI/FFM signatures for the project's exported API.
Include `nimble/answer.h`, or use the generated `answer.pc` with pkg-config.
The companion header preserves native declaration types while namespacing its
guard and expressing C linkage for C and C++ callers. Original compiler headers
and generated backend source remain under `native-proof`.

Initialize each library once before calling its API. Its namespaced initializer
is recorded as `targets.<name>.runtime.init` in `catalog.json`; it takes no
arguments and returns void. Keep initialization and calls on the same foreign
thread, and keep the library loaded for the process lifetime. The catalog
records that lifecycle; loading the Python view does not initialize the runtime.
Distinct source revisions and products receive distinct initializer names.
The current native-library projection supports native Linux builds.

## Releases

```sh
nimble-purifier publish \
  --repo OWNER/REPOSITORY \
  --tag v0.1.0
```

This creates or updates a GitHub release with a deterministic Nix-built
source archive containing both locks. It uses normal `gh` authentication.
Declared binaries and compiler outputs beside their `.nim` sources are
excluded from the archive.

## Scope

Supports public HTTPS Git dependencies with native Nimble 0.26.0 locks,
including task graphs, and the supplied Nim 2.2.12 Linux SDK with C/C++
backends. Project paths must stay inside the working tree. Explicit Nim
compiler lock entries, local/develop dependencies, Mercurial, repository
subdirectories and Git submodules are not yet supported. Manifest-local
NimScript imports and VCS-derived project metadata are also outside the
initial scope.

Dependency-changing flags and native mutation commands such as `install`,
`add`, `develop`, `refresh` and `publish` are guarded in locked sessions.
Use the helper for lock updates and source releases. Native build, test,
run, shell, setup and inspection commands use the prepared environment.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).

### JavaScript products

`buildNimbleProject` can compile an owned production module with the Nim SDK's
JavaScript backend, using the same captured Nimble dependencies:

```nix
browserProducts.answer = {
  module = "src/browser.nim";
  webjar = { artifactId = "nim-answer"; version = "0.1.0"; };
};
```

`packages.browser` retains the project, generated `assets/answer/main.js`, and
`browser-products.json` with the compiler's actual source graph and hashes.
`projections.browser.answer` exposes `web.documentRoot`,
`java-resources.classPath`, and, when WebJar coordinates are supplied, Maven and
Ivy repositories. Ordinary Nim products keep their existing build identity.
The application controls its JavaScript exports through native Nim declarations
and `emit`; the adapter does not invent JavaScript entry points. Nimble manifests declaring `backend = "js"` can also be captured and built
normally; their native JavaScript binaries install under `share/nimble-js`.
The caller chooses its JavaScript runtime. The pure conformance check supplies
Node and Chromium explicitly.
