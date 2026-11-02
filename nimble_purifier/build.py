# SPDX-License-Identifier: MIT
"""Build the native Nimble dependency environment from pinned Git trees."""

import json, os, shutil, subprocess, sys
from pathlib import Path

try:
    from .sources import packages, registry
except ImportError:
    from sources import packages, registry


def main():
    metadata_file, sources, out = map(Path, sys.argv[1:4])
    metadata = json.loads(metadata_file.read_text())
    profile = metadata["profile"]
    original = json.loads(profile["nativeLock"])
    pins = packages(original)
    out.mkdir()
    (out / "pkgcache").mkdir()
    for dep in profile["dependencies"]:
        target = out / "pkgcache" / dep["cacheName"]
        shutil.copytree(sources / dep["source"], target, symlinks=True)
        for directory, dirs, files in os.walk(target):
            os.chmod(directory, 0o755)
            for name in files:
                path = Path(directory) / name
                if not path.is_symlink():
                    path.chmod(path.stat().st_mode | 0o200)
        for alias in dep["aliases"]:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(target),
                    "update-ref",
                    alias,
                    dep["native"]["vcsRevision"],
                ],
                check=True,
            )
    (out / "packages_official.json").write_text(
        json.dumps(registry(profile["dependencies"]), sort_keys=True)
    )
    project = Path.cwd() / "project"
    project.mkdir()
    for name, text in metadata["manifests"].items():
        (project / name).write_text(text)
    native = project / "nimble.lock"
    native.write_text(profile["nativeLock"])
    home = Path.cwd() / "home"
    home.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_CACHE_HOME": str(home / "cache"),
        "NIMBLE_DIR": str(out),
        "NIMBLE_PURIFIER_DIR": str(out),
        "NIMBLE_PURIFIER_NATIVE_LOCKFILE": str(native),
        "NIMBLE_PURIFIER_SYNC_FILE": str(home / "sync.json"),
        "SOURCE_DATE_EPOCH": "1",
    }
    # Native lock includes task requirements in the solve and installs that
    # complete graph; install --depsOnly alone omits task-only packages.
    subprocess.run(
        ["nimble", "-y", "--offline", "lock"], cwd=project, env=env, check=True
    )
    selected = json.loads(native.read_text())
    if packages(selected) != pins or {
        k: set(v) for k, v in selected.get("tasks", {}).items()
    } != {k: set(v) for k, v in original.get("tasks", {}).items()}:
        raise ValueError(
            "native Nimble changed locked selections during the offline build"
        )
    for child in out.iterdir():
        if child.name not in ("pkgs2", "bin", "packages_official.json"):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    (out / "pkgs2").mkdir(exist_ok=True)
    (out / "bin").mkdir(exist_ok=True)
    (out / "metadata.json").write_text(json.dumps(metadata, sort_keys=True))


if __name__ == "__main__":
    main()
