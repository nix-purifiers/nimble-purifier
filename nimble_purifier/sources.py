# SPDX-License-Identifier: MIT
"""Capture native Nimble-selected Git trees without transporting host binaries."""

import base64
import hashlib
import json
import re
import subprocess
from urllib.parse import urlsplit


def git(root, *arguments, binary=False):
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], text=not binary
    )


def packages(native):
    if not isinstance(native, dict) or native.get("version") != 2:
        raise ValueError("unsupported native Nimble lock format")
    result = {}
    for graph in [native.get("packages"), *native.get("tasks", {}).values()]:
        if not isinstance(graph, dict):
            raise ValueError("invalid native task graph")
        for name, record in graph.items():
            if name == "nim":
                raise ValueError(
                    "explicit Nim compiler lock entries are not yet supported; use the supplied SDK"
                )
            if name in result and result[name] != record:
                raise ValueError("conflicting native package/task pins")
            result[name] = record
    for name, record in result.items():
        if not re.fullmatch("[A-Za-z0-9_-]+", name) or not isinstance(record, dict):
            raise ValueError("invalid native package identity")
        url = urlsplit(record.get("url", ""))
        if (
            record.get("downloadMethod") != "git"
            or url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "only public HTTPS Git packages without subdirectories are supported"
            )
        if not re.fullmatch(
            "[0-9a-f]{40}", record.get("vcsRevision", "")
        ) or not re.fullmatch(
            "[0-9a-f]{40}", record.get("checksums", {}).get("sha1", "")
        ):
            raise ValueError("native Git revision or checksum is incomplete")
        if (
            not isinstance(record.get("version"), str)
            or not isinstance(record.get("dependencies"), list)
            or not all(
                isinstance(v, str) and (v == "nim" or v in result)
                for v in record["dependencies"]
            )
        ):
            raise ValueError("incomplete native dependency closure")
    return result


def capture(native, home, temporary, system, native_tool, environment):
    repositories = []
    for marker in (home / "pkgcache").glob("*/.git"):
        if marker.is_dir():
            repositories.append(marker.parent)
    dependencies = []
    entries = []
    for name, record in sorted(packages(native).items()):
        url = record["url"]
        rev = record["vcsRevision"]
        repository = None
        for candidate in sorted(repositories):
            try:
                origin = git(candidate, "config", "--get", "remote.origin.url").strip()
                actual = git(candidate, "rev-parse", "HEAD").strip()
                if origin == url and actual == rev:
                    repository = candidate
                    break
            except subprocess.CalledProcessError:
                pass
        if repository is None:
            raise ValueError("native source cache missing for " + name)
        package_info = json.loads(
            subprocess.check_output(
                [native_tool, "--nimbleDir:" + str(home), "--silent", "dump", "--json"],
                cwd=repository,
                env=environment,
                text=True,
            )
        )
        registry_record = {
            "name": name,
            "url": url,
            "method": "git",
            "description": package_info["desc"],
            "license": package_info["license"],
            "tags": [],
            "web": url,
        }
        tree = temporary / name
        tree.mkdir(parents=True)
        subprocess.run(
            [
                "git",
                "--git-dir",
                str(repository / ".git"),
                "--work-tree",
                str(tree),
                "checkout",
                rev,
                "--",
                ".",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        raw = git(repository, "cat-file", "commit", rev, binary=True)
        for item in git(repository, "ls-tree", "-rz", rev, binary=True).split(b"\0"):
            if item.startswith(b"160000 "):
                raise ValueError("Git submodules are not yet supported")
        nar = subprocess.check_output(
            ["nix", "hash", "path", str(tree)], text=True
        ).strip()
        source = system + "/" + name + "-" + rev
        # Project the native version->commit pin into the local Git cache.
        # Exact-revision downloads may contain no upstream tag refs at all.
        aliases = []
        version = record["version"]
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:[-+][A-Za-z0-9.-]+)?", version):
            aliases.append("refs/tags/v" + version)
        elif version.startswith("#") and version != "#head":
            aliases.extend(["refs/tags/" + version[1:], "refs/heads/" + version[1:]])
        for alias in aliases:
            subprocess.run(["git", "check-ref-format", alias], check=True)
        identity = hashlib.sha256((url + "\n" + rev).encode()).hexdigest()
        dependencies.append(
            {
                "name": name,
                "registry": registry_record,
                "source": source,
                "native": record,
                "aliases": sorted(set(aliases)),
                "cacheName": re.sub(
                    "[^A-Za-z0-9]", "", urlsplit(url).netloc.split(":")[0]
                )
                + "_"
                + re.sub("[^A-Za-z0-9]", "", urlsplit(url).path)
                + "_purifier_"
                + identity,
            }
        )
        entries.append(
            {
                "path": source,
                "hash": nar,
                "git": {
                    "url": url,
                    "rev": rev,
                    "submodules": False,
                    "leaveDotGit": True,
                    "commitObject": {
                        "object": base64.b64encode(raw).decode(),
                        "gitlinks": [],
                    },
                },
            }
        )
    return dependencies, entries


def registry(dependencies):
    return [dep["registry"] for dep in dependencies]
