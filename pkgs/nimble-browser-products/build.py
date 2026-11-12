# SPDX-License-Identifier: MIT
"""Compile owned Nim modules with the native JS backend; retain its input graph."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

out, environment, spec_file, nim = sys.argv[1:]
out, environment = Path(out), Path(environment).resolve()
project = (out / 'project').resolve()
package = json.loads(subprocess.check_output(['nimble', '--silent', 'dump', '--json'], text=True))
source_root = (project / package.get('srcDir', '')).resolve()
if not source_root.is_relative_to(project):
    raise ValueError('Nimble source directory escapes project')
sdk = json.loads(subprocess.check_output([nim, 'dump', '--dump.format:json', '--verbosity:0',
                                        str(next(source_root.rglob('*.nim')))], text=True))
sdk_root = Path(sdk['libpath']).resolve()
metadata = json.loads((environment / 'metadata.json').read_text())
if sdk['version'] != metadata['profile']['toolVersions']['nim']:
    raise ValueError('Nim SDK changed from captured profile')
dependencies = []
for dep in metadata['profile']['dependencies']:
    root = Path(subprocess.check_output(['nimble', '--silent', 'path', dep['name']], text=True).strip()).resolve()
    if not root.is_relative_to(environment / 'pkgs2'):
        raise ValueError('dependency is outside captured environment')
    dependencies.append((root, dep))

def owner(path):
    if path.is_relative_to(project):
        return {'kind': 'project', 'path': str(path.relative_to(project))}
    if path.is_relative_to(sdk_root):
        return {'kind': 'sdk', 'path': str(path.relative_to(sdk_root))}
    for root, dep in dependencies:
        if path.is_relative_to(root):
            return {'kind': 'dependency', 'package': dep['name'],
                    'version': dep['native']['version'], 'revision': dep['native']['vcsRevision'],
                    'path': str(path.relative_to(root))}
    raise ValueError('compiler input has no captured owner: ' + str(path))

models = {}
for name, spec in json.loads(Path(spec_file).read_text()).items():
    entry = (project / spec['module']).resolve(strict=True)
    if not entry.is_relative_to(source_root) or not entry.is_file():
        raise ValueError('browser module is not an owned production source')
    cache = Path(os.environ['TMPDIR']) / 'js-cache' / name
    cache.mkdir(parents=True)
    assets = out / 'assets' / name
    assets.mkdir(parents=True)
    payload = assets / 'main.js'
    subprocess.run([nim, 'js', '-d:release', '--genScript:on', '--nimcache:' + str(cache),
                    '--out:' + str(payload), str(entry)], check=True)
    graph = []
    for line in (cache / (entry.stem + '.deps')).read_text().splitlines():
        path = Path(line).resolve(strict=True)
        graph.append(owner(path) | {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    if not any(p['kind'] == 'project' and p['path'] == spec['module'] for p in graph):
        raise ValueError('native compiler graph omitted the requested module')
    models[name] = {'backend': 'js', 'module': spec['module'], 'sources': graph,
                    'payload': 'assets/' + name + '/main.js',
                    'sha256': hashlib.sha256(payload.read_bytes()).hexdigest()}
(out / 'browser-products.json').write_text(json.dumps(models, sort_keys=True, indent=2) + '\n')
