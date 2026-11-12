# SPDX-License-Identifier: MIT
{ lib }:
{
  src,
  lockFile ? src + "/nimble-purifier.lock.json",
  nimbleLock ? src + "/nimble.lock",
}:
let
  exists = builtins.pathExists lockFile && builtins.pathExists nimbleLock;
  raw = if exists then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  relative =
    p:
    builtins.isString p
    && p != ""
    && !(lib.hasPrefix "/" p)
    && !(lib.hasInfix "\\" p)
    && builtins.all (
      v:
      !(builtins.elem v [
        ""
        "."
        ".."
      ])
    ) (lib.splitString "/" p);
  hex40 = v: builtins.isString v && builtins.match "[0-9a-f]{40}" v != null;
  hex64 = v: builtins.isString v && builtins.match "[0-9a-f]{64}" v != null;
  sri = v: builtins.isString v && builtins.match "sha256-[A-Za-z0-9+/]{43}=" v != null;
  urlOK =
    v:
    builtins.isString v
    && builtins.match "https://[A-Za-z0-9._-]+(:[0-9]+)?/[A-Za-z0-9_./~%+-]+" v != null;
  inputNames = lib.filter (
    n: lib.hasSuffix ".nimble" n && (builtins.readDir src).${n} != "directory"
  ) (builtins.attrNames (builtins.readDir src));
  inputs = data.inputs or [ ];
  manifests = data.manifests or { };
  inputOK =
    i:
    builtins.isAttrs i
    && relative (i.path or null)
    && builtins.elem i.path inputNames
    && hex64 (i.hash or null)
    && builtins.hashFile "sha256" (src + "/${i.path}") == i.hash
    && builtins.isString (manifests.${i.path} or null)
    && builtins.hashString "sha256" manifests.${i.path} == i.hash;
  graphs = n: [ n.packages ] ++ builtins.attrValues n.tasks;
  pins = n: lib.foldl' (acc: graph: acc // graph) { } (graphs n);
  pinOK =
    all: name: p:
    builtins.match "[A-Za-z0-9_-]+" name != null
    && name != "nim"
    && builtins.isAttrs p
    && builtins.isString (p.version or null)
    && p.version != ""
    && (p.downloadMethod or null) == "git"
    && urlOK (p.url or null)
    && hex40 (p.vcsRevision or null)
    && builtins.isAttrs (p.checksums or null)
    && hex40 (p.checksums.sha1 or null)
    && builtins.isList (p.dependencies or null)
    && builtins.all (v: builtins.isString v && (v == "nim" || builtins.hasAttr v all)) p.dependencies;
  nativeOK =
    n:
    builtins.isAttrs n
    && (n.version or null) == 2
    && builtins.isAttrs (n.packages or null)
    && builtins.isAttrs (n.tasks or null)
    && builtins.all builtins.isAttrs (builtins.attrValues n.tasks)
    && (
      let
        all = pins n;
      in
      lib.all (name: pinOK all name all.${name}) (builtins.attrNames all)
      && builtins.all (g: lib.all (name: g.${name} == all.${name}) (builtins.attrNames g)) (graphs n)
    );
  refOK =
    v:
    builtins.isString v
    && builtins.match "refs/(heads|tags)/[A-Za-z0-9._/-]+" v != null
    && !(lib.hasInfix ".." v);
  entryOK =
    system: e:
    builtins.isAttrs e
    && relative (e.path or null)
    && lib.hasPrefix "${system}/" e.path
    && sri (e.hash or null)
    && builtins.isAttrs (e.git or null)
    && urlOK (e.git.url or null)
    && hex40 (e.git.rev or null)
    && (e.git.submodules or null) == false
    && (e.git.leaveDotGit or null) == true
    && builtins.isAttrs (e.git.commitObject or null)
    && builtins.isString (e.git.commitObject.object or null)
    && e.git.commitObject.object != ""
    && builtins.match "[A-Za-z0-9+/]*={0,2}" e.git.commitObject.object != null
    && (e.git.commitObject.gitlinks or null) == [ ];
  depOK =
    all: entries: d:
    builtins.isAttrs d
    && builtins.isString (d.name or null)
    && builtins.hasAttr d.name all
    && (d.native or null) == all.${d.name}
    && builtins.isAttrs (d.registry or null)
    && (d.registry.name or null) == d.name
    && (d.registry.url or null) == d.native.url
    && (d.registry.method or null) == "git"
    && builtins.isString (d.registry.license or null)
    && d.registry.license != ""
    && builtins.isString (d.registry.description or null)
    && builtins.isString (d.source or null)
    && builtins.hasAttr d.source entries
    && entries.${d.source}.git.url == d.native.url
    && entries.${d.source}.git.rev == d.native.vcsRevision
    && builtins.isString (d.cacheName or null)
    && builtins.match "[A-Za-z0-9_]+" d.cacheName != null
    && builtins.isList (d.aliases or null)
    && builtins.all refOK d.aliases;
  profiles = data.profiles or { };
  profileOK =
    system: p:
    builtins.elem system [
      "x86_64-linux"
      "aarch64-linux"
    ]
    && builtins.isAttrs p
    && (p.system or null) == system
    && builtins.isAttrs (p.toolVersions or null)
    && (p.toolVersions.nim or null) == "2.2.12"
    && (p.toolVersions.nimble or null) == "0.26.0"
    && hex64 (p.toolVersions.sdk or null)
    && hex64 (p.toolVersions.resolver or null)
    && builtins.isList (p.binaries or null)
    && builtins.all relative p.binaries
    && builtins.isString (p.nativeLock or null)
    && (
      let
        n = builtins.fromJSON p.nativeLock;
      in
      nativeOK n
      && builtins.isList (p.entries or null)
      && builtins.all (entryOK system) p.entries
      && builtins.isList (p.dependencies or null)
      && (
        let
          all = pins n;
          byPath = lib.listToAttrs (
            map (e: {
              name = e.path;
              value = e;
            }) p.entries
          );
        in
        builtins.length p.entries == builtins.length (builtins.attrNames all)
        && builtins.length p.dependencies == builtins.length p.entries
        && builtins.length (builtins.attrNames byPath) == builtins.length p.entries
        && lib.sort builtins.lessThan (map (d: d.name) p.dependencies) == builtins.attrNames all
        && builtins.all (depOK all byPath) p.dependencies
      )
    );
  problems =
    lib.optionals (!exists) [ "missing lockfiles; run nimble-purifier lock" ]
    ++ lib.optionals (
      exists
      && (
        (data.version or null) != 1
        ||
          (data.contentHash or null)
          != builtins.hashString "sha256" (builtins.toJSON (builtins.removeAttrs data [ "contentHash" ]))
      )
    ) [ "invalid companion seal; run nimble-purifier lock" ]
    ++ lib.optionals (
      exists
      && (
        !builtins.isList inputs
        || builtins.length inputs != 1
        || map (i: i.path or "") inputs != inputNames
        || !(builtins.all inputOK inputs)
      )
    ) [ "project manifest changed; run nimble-purifier lock" ]
    ++ lib.optionals (
      exists
      && (
        (data.nativeLock or null) != builtins.readFile nimbleLock
        || (data.nativeHash or null) != builtins.hashFile "sha256" nimbleLock
        || !(nativeOK (builtins.fromJSON (builtins.readFile nimbleLock)))
      )
    ) [ "native Nimble pins changed; run nimble-purifier lock" ]
    ++ lib.optionals (
      !builtins.isAttrs profiles
      || profiles == { }
      || !(lib.all (s: profileOK s profiles.${s}) (builtins.attrNames profiles))
    ) [ "invalid native SDK profiles; run nimble-purifier lock" ];
in
{
  purifier = "nimble";
  inherit data problems;
  entries = lib.concatMap (p: p.entries or [ ]) (builtins.attrValues profiles);
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
