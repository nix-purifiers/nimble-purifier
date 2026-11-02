#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json, os, shutil, subprocess, sys, tarfile, tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    result = subprocess.run(list(map(str, args)), text=True, **kwargs)
    if result.returncode:
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        result.check_returncode()
    return result


case = sys.argv[1]
with tempfile.TemporaryDirectory(prefix="nimble-conformance-") as temporary:
    temp = Path(temporary)
    cli = temp / "cli"
    raw = temp / "sdk"
    run(["nix", "build", str(REPO) + "#cli", "--out-link", cli])
    run(["nix", "build", str(REPO) + "#native", "--out-link", raw])
    helper = cli / "bin/nimble-purifier"
    nimble = cli / "bin/nimble"
    native_sdk = raw / "bin/nimble"
    root = temp / "project"
    shutil.copytree(
        REPO / "examples/minimal",
        root,
        ignore=shutil.ignore_patterns(
            ".nimble-purifier",
            "*.lock",
            "*.json",
            "nimble.paths",
            "config.nims",
            "example",
            "test",
        ),
    )
    # Preserve test.nim while excluding compiled extensionless outputs.
    recipe = root / "example.nimble"
    if case == "update":
        recipe.write_text(
            recipe.read_text().replace("results == 0.5.1", "results == 0.5.0")
        )
    if case == "tasks":
        recipe.write_text(
            recipe.read_text().replace(', "results == 0.5.1"', "")
            + '\ntaskRequires "test", "results == 0.5.1"\n'
        )
        (root / "src/example.nim").write_text('echo "locked Nimble 42"\n')
        with recipe.open("a") as f:
            f.write(
                'task child, "Verify child selectors":\n  exec "nimble --nimbleDir:'
                + str(temp / "decoy")
                + ' --silent path results"\n'
            )
    env = {k: v for k, v in os.environ.items() if not k.startswith("NIMBLE_PURIFIER_")}
    env["NIMBLE_DIR"] = str(temp / "ordinary-cache")
    args = [helper, "--project", root]
    run([*args, "lock"], env=env)
    companion = root / "nimble-purifier.lock.json"
    tool = root / "nimble.lock"
    initial = companion.read_bytes()
    native_initial = tool.read_bytes()
    run([*args, "lock"], env=env)
    assert companion.read_bytes() == initial and tool.read_bytes() == native_initial
    if case == "update":
        recipe.write_text(
            recipe.read_text().replace("results == 0.5.0", "results >= 0.5.0")
        )
        run([*args, "lock"], env=env)
        assert json.loads(tool.read_text())["packages"]["results"]["version"] == "0.5.0"
        run([*args, "update", "results"], env=env)
        assert json.loads(tool.read_text())["packages"]["results"]["version"] != "0.5.0"
        run([*args, "update"], env=env)
    elif case == "relock":
        damaged = json.loads(initial)
        damaged["contentHash"] = "bad"
        companion.write_text(json.dumps(damaged))
        run([*args, "lock"], env=env)
        assert tool.read_bytes() == native_initial
        tool.write_text("invalid native JSON")
        run([*args, "lock"], env=env)
        assert tool.read_bytes() == native_initial
    elif case == "external":
        directory = temp / "external"
        directory.mkdir()
        selected = directory / "companion.json"
        selected_native = directory / "native.lock"
        args = [
            helper,
            "--project",
            root,
            "--lockfile",
            selected,
            "--tool-lockfile",
            selected_native,
        ]
        run([*args, "lock"], env=env)
        assert companion.read_bytes() == initial and tool.read_bytes() == native_initial
        companion.unlink()
        tool.write_text("intentionally invalid working native lock\n")
        env.update(
            NIMBLE_PURIFIER_LOCKFILE=str(selected),
            NIMBLE_PURIFIER_TOOL_LOCKFILE=str(selected_native),
        )
    elif case == "tasks":
        data = json.loads(tool.read_text())
        assert data["tasks"]["test"]["results"] and not data["packages"], data
    elif case != "native":
        raise ValueError(case)
    environment = Path(
        run([*args, "prefetch"], env=env, capture_output=True).stdout.strip()
    )
    offline = {
        **env,
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "XDG_CACHE_HOME": str(temp / "compiler-cache"),
    }
    path = Path(
        run(
            [nimble, "--silent", "path", "results"],
            cwd=root,
            env=offline,
            capture_output=True,
        ).stdout.strip()
    ).resolve()
    assert str(path).startswith(str(environment / "pkgs2")), path
    assert not Path(env["NIMBLE_DIR"]).exists()
    poisoned = None
    if case == "native":
        ordinary = Path(env["NIMBLE_DIR"])
        shutil.copytree(environment / "pkgs2", ordinary / "pkgs2")
        shutil.copyfile(
            environment / "packages_official.json", ordinary / "packages_official.json"
        )
        poisoned = next((ordinary / "pkgs2").glob("results-*/results.nim"))
        poisoned.chmod(0o644)
        poisoned.write_text("this is not a valid Nim module\n")
    run([nimble, "build"], cwd=root, env=offline)
    assert (
        run([root / "example"], capture_output=True).stdout.strip()
        == "locked Nimble 42"
    )
    run([nimble, "test"], cwd=root, env=offline)
    run([cli / "bin/nim", "check", root / "tests/test.nim"], cwd=root, env=offline)
    assert (
        poisoned is None or poisoned.read_text() == "this is not a valid Nim module\n"
    )
    if case == "external":
        assert tool.read_text() == "intentionally invalid working native lock\n"
    if case == "tasks":
        child = run([nimble, "child"], cwd=root, env=offline, capture_output=True)
        assert (
            str(environment / "pkgs2")
            in str(
                Path(
                    next(
                        line
                        for line in reversed(child.stdout.splitlines())
                        if line.startswith("/")
                    )
                ).resolve()
            )
            and not (temp / "decoy").exists()
        ), child.stdout
    if case == "native":
        from editor import check as editor_check

        editor_check(cli, root, environment, offline)
        source = root / "src/example.nim"
        source.write_text(source.read_text() + "# application edit\n")
        assert (
            Path(
                run(
                    [*args, "prefetch"], env=offline, capture_output=True
                ).stdout.strip()
            )
            == environment
        )
        run([nimble, "build"], cwd=root, env=offline)
        invalid = subprocess.run(
            [str(nimble), "--nimbleDir:" + str(temp / "decoy"), "build"],
            cwd=root,
            env=offline,
            text=True,
            capture_output=True,
        )
        assert invalid.returncode and "configuration overrides" in invalid.stderr, (
            invalid.stderr
        )
        recipe.write_text(recipe.read_text() + "\n# stale\n")
        stale = subprocess.run(
            [str(nimble), "build"],
            cwd=root,
            env=offline,
            text=True,
            capture_output=True,
        )
        assert stale.returncode and "manifest changed" in stale.stderr, stale.stderr
        recipe.write_bytes((REPO / "examples/minimal/example.nimble").read_bytes())
        fake = temp / "gh"
        record = temp / "calls"
        fake.write_text(
            "#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\np=Path("
            + repr(str(record))
            + ')\na=sys.argv[1:]\nwith p.open("a") as f:f.write(json.dumps(a)+"\\n")\nif a[:2]==["release","view"]:sys.exit(0 if len(p.read_text().splitlines())>2 else 1)\n'
        )
        fake.chmod(0o755)
        for _ in range(2):
            run(
                [*args, "publish", "--repo", "fixture/project", "--tag", "v0.1.0"],
                env={**env, "NIMBLE_PURIFIER_GH": str(fake)},
            )
        calls = [json.loads(line) for line in record.read_text().splitlines()]
        assert calls[1][:2] == ["release", "create"] and calls[3][:2] == [
            "release",
            "upload",
        ], calls
        with tarfile.open(
            next(v for v in calls[1] if v.endswith("/project.tar.gz"))
        ) as release:
            files = set(release.getnames())
            assert {
                "./nimble.lock",
                "./nimble-purifier.lock.json",
                "./example.nimble",
            } <= files
            assert "./example" not in files and "./tests/test" not in files, files
        empty_project = temp / "empty-project"
        empty_project.mkdir()
        (empty_project / "empty.nimble").write_text(
            'version = "0.1.0"\nauthor = "the nix-purifier developers"\ndescription = "Empty graph"\nlicense = "MIT"\nrequires "nim >= 2.2.0"\n'
        )
        run([helper, "--project", empty_project, "lock"], env=env)
        empty_environment = Path(
            run(
                [helper, "--project", empty_project, "prefetch"],
                env=offline,
                capture_output=True,
            ).stdout.strip()
        )
        assert list((empty_environment / "pkgs2").iterdir()) == []
        empty = temp / "unlocked"
        empty.mkdir()
        baseline = run(
            [native_sdk, "--version"], cwd=empty, env=env, capture_output=True
        )
        fallback = run([nimble, "--version"], cwd=empty, env=env, capture_output=True)
        assert (
            baseline.stdout == fallback.stdout
            and "ordinary impure nimble" in fallback.stderr
        )
    if case == "native":
        (empty / "unlocked.nimble").write_text(
            'version = "0.1.0"\nauthor = "the nix-purifier developers"\ndescription = "Native fallback"\nlicense = "MIT"\nrequires "nim >= 2.2.0"\n'
        )
        command = ["shell", "sh", "-c", "cat; printf native-stderr >&2; exit 7"]
        baseline = subprocess.run(
            [str(native_sdk), *command],
            cwd=empty,
            env=env,
            input="native-stdin\n",
            text=True,
            capture_output=True,
        )
        fallback = subprocess.run(
            [str(nimble), *command],
            cwd=empty,
            env=env,
            input="native-stdin\n",
            text=True,
            capture_output=True,
        )
        assert baseline.returncode == fallback.returncode == 7, (baseline, fallback)
        assert (
            "native-stdin" in baseline.stdout and "native-stdin" in fallback.stdout
        ), (baseline, fallback)
        assert (
            "native-stderr" in baseline.stderr and "native-stderr" in fallback.stderr
        ), (baseline, fallback)
        assert "ordinary impure nimble" in fallback.stderr
    print("Nimble native conformance passed:", case)
