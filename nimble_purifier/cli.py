# SPDX-License-Identifier: MIT
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from . import lock, sources

NATIVE = os.environ.get("NIMBLE_PURIFIER_NATIVE", "nimble")
SYSTEM = os.environ.get("NIMBLE_PURIFIER_SYSTEM", "x86_64-linux")
HERE = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    result = subprocess.run(list(map(str, args)), text=True, **kwargs)
    if result.returncode and result.stderr:
        print(result.stderr, file=sys.stderr)
    result.check_returncode()
    return result


def clean_environment():
    return {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("NIMBLE_PURIFIER_") and k != "NIMBLE_DIR"
    }


def versions():
    return {
        "nim": os.environ["NIMBLE_PURIFIER_NIM_VERSION"],
        "nimble": os.environ["NIMBLE_PURIFIER_NIMBLE_VERSION"],
        "sdk": hashlib.sha256((HERE / "pkgs/build-nimble-project/nimble.patch").read_bytes()).hexdigest(),
        "resolver": hashlib.sha256(
            b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))
        ).hexdigest(),
    }


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.read_text() == text:
        return
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def resolve(root, native, companion, update=False, names=()):
    declarations = lock.inputs(root)
    if len(declarations) != 1:
        raise ValueError("expected exactly one .nimble manifest")
    if (root / "nimble.develop").exists():
        raise ValueError("local develop bindings are not yet supported")
    previous = None
    try:
        candidate = json.loads(companion.read_text())
        if candidate.get("contentHash") == lock.seal(candidate)["contentHash"]:
            previous = candidate
        if (
            not update
            and not lock.problems(root, native, candidate, SYSTEM)
            and candidate["profiles"][SYSTEM]["toolVersions"] == versions()
        ):
            print("Existing native Nimble selections retained", file=sys.stderr)
            return
    except (ValueError, KeyError, TypeError, OSError):
        pass
    with tempfile.TemporaryDirectory(prefix="nimble-purifier-lock-") as temporary:
        temp = Path(temporary)
        stage = temp / "project"
        stage.mkdir()
        home = temp / "home"
        home.mkdir()
        for item in declarations:
            shutil.copyfile(root / item["path"], stage / item["path"])
        selected = stage / "nimble.lock"
        try:
            seed = json.loads(native.read_text())
            selected.write_text(json.dumps(seed))
        except (ValueError, OSError):
            if previous:
                seed = json.loads(
                    previous["profiles"]
                    .get(SYSTEM, {})
                    .get("nativeLock", previous["nativeLock"])
                )
                selected.write_text(json.dumps(seed))
        if names:
            if not selected.is_file() or not set(names) <= set(
                sources.packages(json.loads(selected.read_text()))
            ):
                raise ValueError("named updates require existing locked package names")
        env = clean_environment()
        env.update(
            HOME=str(home),
            XDG_CONFIG_HOME=str(home / "config"),
            XDG_CACHE_HOME=str(home / "cache"),
            NIMBLE_DIR=str(temp / "cache"),
            NIMBLE_PURIFIER_SYNC_FILE=str(temp / "sync.json"),
        )
        arguments = [NATIVE, "--nimbleDir:" + str(temp / "cache"), "-y", "lock"]
        if update:
            arguments.extend(["--refresh", *names])
        run(arguments, cwd=stage, env=env)
        package = json.loads(
            run(
                [
                    NATIVE,
                    "--nimbleDir:" + str(temp / "cache"),
                    "--silent",
                    "dump",
                    "--json",
                ],
                cwd=stage,
                env=env,
                capture_output=True,
            ).stdout
        )
        if package.get("backend", "c") not in ("c", "cpp"):
            raise ValueError("the supplied SDK currently supports C and C++ backends")
        binaries = [
            str(Path(package.get("binDir", "")) / name)
            for name in package.get("bin", [])
        ]
        if any(not lock.relative(name) for name in binaries) or len(
            {Path(name).name for name in binaries}
        ) != len(binaries):
            raise ValueError(
                "native binary output paths must be distinct and inside the project"
            )
        text = selected.read_text()
        native_data = json.loads(text)
        dependencies, entries = sources.capture(
            native_data, temp / "cache", temp / "trees", SYSTEM, NATIVE, env
        )
        profiles = (
            dict(previous["profiles"])
            if previous and previous["inputs"] == declarations
            else {}
        )
        profiles[SYSTEM] = {
            "system": SYSTEM,
            "binaries": binaries,
            "nativeLock": text,
            "dependencies": dependencies,
            "entries": entries,
            "toolVersions": versions(),
        }
        data = lock.seal(
            {
                "version": 1,
                "inputs": declarations,
                "manifests": {
                    v["path"]: (root / v["path"]).read_bytes().decode()
                    for v in declarations
                },
                "profiles": profiles,
                "nativeLock": text,
                "nativeHash": hashlib.sha256(text.encode()).hexdigest(),
            }
        )
        if problems := lock.problems(root, selected, data, SYSTEM):
            raise ValueError("\n".join(problems))
        write(native, text)
        write(companion, json.dumps(data, sort_keys=True, indent=2) + "\n")
        print("Locked native Nimble graph for " + SYSTEM, file=sys.stderr)


def checked(root, native, companion):
    data = json.loads(companion.read_text())
    if problems := lock.problems(root, native, data, SYSTEM):
        raise ValueError("\n".join(problems))
    if any(
        data["profiles"][SYSTEM]["toolVersions"][key] != versions()[key]
        for key in ("nim", "nimble", "sdk")
    ):
        raise ValueError("native SDK changed" + lock.FIX)
    if (root / "nimble.develop").exists():
        raise ValueError("local develop bindings are not yet supported")
    return data


def realize(root, native, companion, target="environment"):
    checked(root, native, companion)
    args = {
        "project": str(root),
        "nativeLock": str(native),
        "companion": str(companion),
        "target": target,
    }
    expression = (
        "import "
        + str(HERE / "pkgs/build-nimble-project/realize.nix")
        + " (builtins.fromJSON "
        + json.dumps(lock.canonical(args))
        + ")"
    )
    return Path(
        run(
            [
                "nix",
                "build",
                "--impure",
                "--no-link",
                "--print-out-paths",
                "--expr",
                expression,
            ],
            capture_output=True,
        ).stdout.strip()
    )


def session(root, native, companion):
    data = checked(root, native, companion)
    output = realize(root, native, companion)
    private = root / ".nimble-purifier/sessions" / output.name
    private.mkdir(parents=True, exist_ok=True)
    for name in ("pkgs2", "bin"):
        target = private / name
        if not target.exists():
            target.symlink_to(output / name, target_is_directory=True)
    registry = private / "packages_official.json"
    if not registry.exists():
        shutil.copyfile(output / "packages_official.json", registry)
    selected = private / "nimble.lock"
    write(selected, data["profiles"][SYSTEM]["nativeLock"])
    env = clean_environment()
    env.update(
        NIMBLE_DIR=str(private),
        NIMBLE_PURIFIER_LOCKFILE=str(companion),
        NIMBLE_PURIFIER_TOOL_LOCKFILE=str(native),
        NIMBLE_PURIFIER_DIR=str(private),
        NIMBLE_PURIFIER_NATIVE_LOCKFILE=str(selected),
        NIMBLE_PURIFIER_SYNC_FILE=str(private / "sync.json"),
        XDG_CACHE_HOME=str(private / "cache"),
        XDG_CONFIG_HOME=str(private / "config"),
    )
    return output, env


def prefetch(root, native, companion):
    output, env = session(root, native, companion)
    run([NATIVE, "-y", "setup"], cwd=root, env=env, stdout=sys.stderr)
    gc = root / ".nimble-purifier/gcroots"
    gc.mkdir(parents=True, exist_ok=True)
    run(
        [
            "nix-store",
            "--add-root",
            gc / output.name,
            "--indirect",
            "--realise",
            output,
        ],
        stdout=subprocess.DEVNULL,
    )
    print(output)
    return output


def runtime(root, native, companion, arguments):
    checked(root, native, companion)
    head = arguments[: arguments.index("--")] if "--" in arguments else arguments
    protected = (
        "nimbleDir",
        "lockFile",
        "developFile",
        "nim",
        "package",
        "features",
        "requires",
        "localdeps",
        "local",
        "global",
        "disableLockFile",
        "ignoreSubmodules",
        "solver",
        "minver",
    )
    for arg in head:
        if arg in ("-l", "-g") or (
            arg.startswith("--")
            and arg[2:].split(":")[0].split("=")[0].lower()
            in {v.lower() for v in protected}
        ):
            raise ValueError(
                "dependency configuration overrides are not prepared" + lock.FIX
            )
    command = next((v for v in head if not v.startswith("-")), "")
    if command in (
        "install",
        "uninstall",
        "add",
        "remove",
        "lock",
        "upgrade",
        "develop",
        "sync",
        "refresh",
        "init",
        "publish",
    ):
        raise ValueError(
            "this dependency mutation command is not supported in a locked session; use nimble-purifier"
        )
    _, env = session(root, native, companion)
    # Native setup preserves custom config.nims content and supplies all locked
    # task paths for editor/standalone compiler commands.
    run([NATIVE, "--silent", "-y", "setup"], cwd=root, env=env, stdout=sys.stderr)
    os.chdir(root)
    os.execve(NATIVE, [NATIVE, *arguments], env)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path)
    parser.add_argument("--lockfile", type=Path)
    parser.add_argument("--tool-lockfile", "--native-lock", type=Path)
    parser.add_argument("--native", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("command", nargs="?")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    root = (args.project or Path.cwd()).resolve()
    if not args.project:
        while not list(root.glob("*.nimble")) and root != root.parent:
            root = root.parent
    companion = (
        args.lockfile
        or Path(
            os.environ.get(
                "NIMBLE_PURIFIER_LOCKFILE", root / "nimble-purifier.lock.json"
            )
        )
    ).resolve()
    native = (
        args.tool_lockfile
        or Path(
            os.environ.get(
                "NIMBLE_PURIFIER_TOOL_LOCKFILE",
                os.environ.get("NIMBLE_PURIFIER_NATIVE_LOCKFILE", root / "nimble.lock"),
            )
        )
    ).resolve()
    if args.native:
        arguments = ([args.command] if args.command else []) + args.arguments
        if not companion.exists():
            print(
                "nimble-purifier: no lockfile; running ordinary impure nimble",
                file=sys.stderr,
            )
            os.execve(
                NATIVE,
                [NATIVE, *arguments],
                {
                    k: v
                    for k, v in os.environ.items()
                    if not k.startswith("NIMBLE_PURIFIER_")
                },
            )
        runtime(root, native, companion, arguments)
        return
    if args.command in ("lock", "update"):
        resolve(root, native, companion, args.command == "update", args.arguments)
    elif args.command == "prefetch":
        prefetch(root, native, companion)
    elif args.command == "publish":
        publish = argparse.ArgumentParser()
        publish.add_argument("--repo", required=True)
        publish.add_argument("--tag", required=True)
        selected = publish.parse_args(args.arguments)
        output = realize(root, native, companion, "release")
        gh = os.environ.get("NIMBLE_PURIFIER_GH", "gh")
        common = ["--repo", selected.repo]
        exists = (
            subprocess.run(
                [gh, "release", "view", selected.tag, *common],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        run(
            [
                gh,
                "release",
                "upload",
                selected.tag,
                output / "project.tar.gz",
                *common,
                "--clobber",
            ]
            if exists
            else [
                gh,
                "release",
                "create",
                selected.tag,
                output / "project.tar.gz",
                *common,
                "--title",
                selected.tag,
                "--notes",
                "Locked Nimble project sources.",
            ]
        )
    else:
        parser.error("expected lock, update, prefetch or publish")


def entry():
    try:
        main()
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        subprocess.CalledProcessError,
    ) as error:
        print("nimble-purifier: " + str(error), file=sys.stderr)
        raise SystemExit(1)
