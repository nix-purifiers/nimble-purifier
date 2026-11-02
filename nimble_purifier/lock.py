# SPDX-License-Identifier: MIT
import base64, hashlib, json, re
from .sources import packages

SYSTEMS = ("x86_64-linux", "aarch64-linux")
FIX = "; run nimble-purifier lock, then nimble-purifier prefetch"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def seal(data):
    data = dict(data)
    data.pop("contentHash", None)
    data["contentHash"] = hashlib.sha256(canonical(data).encode()).hexdigest()
    return data


def relative(value):
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and "\\" not in value
        and all(v not in ("", ".", "..") for v in value.split("/"))
    )


def inputs(root):
    return [
        {"path": p.name, "hash": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(root.glob("*.nimble"))
    ]


def problems(root, native, data, system=None):
    try:
        if (
            not isinstance(data, dict)
            or data.get("version") != 1
            or data.get("contentHash") != seal(data)["contentHash"]
        ):
            raise ValueError("invalid companion format or seal")
        if (
            not data["inputs"]
            or data["inputs"] != inputs(root)
            or len(data["inputs"]) != 1
        ):
            raise ValueError("project manifest changed or ambiguous")
        if set(data["manifests"]) != {v["path"] for v in data["inputs"]}:
            raise ValueError("incomplete manifest snapshot")
        if any(
            hashlib.sha256(data["manifests"][v["path"]].encode()).hexdigest()
            != v["hash"]
            for v in data["inputs"]
        ):
            raise ValueError("native manifest snapshot changed")
        if (
            native.read_text() != data["nativeLock"]
            or hashlib.sha256(native.read_bytes()).hexdigest() != data["nativeHash"]
        ):
            raise ValueError("native Nimble lock changed")
        packages(json.loads(data["nativeLock"]))
        profiles = data["profiles"]
        if not profiles or any(v not in SYSTEMS for v in profiles):
            raise ValueError("invalid platform profiles")
        if system and system not in profiles:
            raise ValueError("missing SDK profile for " + system)
        for platform, profile in profiles.items():
            if (
                profile["system"] != platform
                or profile["toolVersions"]["nim"] != "2.2.12"
                or profile["toolVersions"]["nimble"] != "0.26.0"
            ):
                raise ValueError("unsupported native SDK profile")
            if not re.fullmatch("[0-9a-f]{64}", profile["toolVersions"].get("sdk", "")):
                raise ValueError("invalid SDK implementation fingerprint")
            if not isinstance(profile["binaries"], list) or any(
                not relative(p) for p in profile["binaries"]
            ):
                raise ValueError("invalid native binary output paths")
            pins = packages(json.loads(profile["nativeLock"]))
            deps = profile["dependencies"]
            entries = profile["entries"]
            sources = {e["path"]: e for e in entries}
            if (
                len(sources) != len(entries)
                or len(deps) != len(pins)
                or len(entries) != len(pins)
            ):
                raise ValueError("invalid native source graph")
            if {d["name"] for d in deps} != set(pins):
                raise ValueError("native package closure changed")
            for dep in deps:
                record = dep["registry"]
                if (
                    record["name"] != dep["name"]
                    or record["url"] != dep["native"]["url"]
                    or record["method"] != "git"
                    or not record["license"]
                    or not isinstance(record["description"], str)
                ):
                    raise ValueError("invalid native registry projection")
                pin = pins[dep["name"]]
                entry = sources[dep["source"]]
                if (
                    dep["native"] != pin
                    or entry["git"]["url"] != pin["url"]
                    or entry["git"]["rev"] != pin["vcsRevision"]
                ):
                    raise ValueError("native Git pins changed")
                if (
                    not relative(entry["path"])
                    or not entry["path"].startswith(platform + "/")
                    or not re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=", entry["hash"])
                ):
                    raise ValueError("invalid source path or hash")
                git = entry["git"]
                if (
                    git["submodules"] is not False
                    or git["leaveDotGit"] is not True
                    or git["commitObject"]["gitlinks"] != []
                ):
                    raise ValueError("unsupported Git metadata")
                raw = base64.b64decode(git["commitObject"]["object"], validate=True)
                if (
                    hashlib.sha1(
                        b"commit " + str(len(raw)).encode() + b"\0" + raw
                    ).hexdigest()
                    != pin["vcsRevision"]
                ):
                    raise ValueError("Git commit object changed")
                if (
                    not re.fullmatch("[A-Za-z0-9_]+", dep["cacheName"])
                    or not isinstance(dep["aliases"], list)
                    or any(
                        not isinstance(a, str)
                        or not a.startswith(("refs/heads/", "refs/tags/"))
                        or ".." in a
                        or any(c in a for c in " ~^:?*[\\")
                        for a in dep["aliases"]
                    )
                ):
                    raise ValueError("invalid native cache metadata")
        return []
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        return [str(error) + FIX]
