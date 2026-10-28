"""Build-environment provenance and portable-package inventory checks."""
from collections import defaultdict
import hashlib
import importlib.metadata as metadata
import importlib.util
from pathlib import Path
import sys
import sysconfig


def audit_builder():
    """Reject dependencies borrowed from another interpreter's site-packages."""
    roots = sorted({Path(sysconfig.get_path(key)).resolve() for key in ('purelib', 'platlib')})
    versions = {}
    external = []
    for distribution in metadata.distributions():
        name = distribution.metadata['Name']
        location = Path(distribution.locate_file('')).resolve()
        versions[name] = distribution.version
        if not any(location.is_relative_to(root) for root in roots):
            external.append(f'{name}: {location}')
    for name in ('PyInstaller', 'aiohttp', 'jwt', 'fastembed', 'numpy', 'onnxruntime', 'tokenizers', 'PIL'):
        spec = importlib.util.find_spec(name)
        if spec is None or not spec.origin:
            raise RuntimeError('Missing builder dependency: ' + name)
        location = Path(spec.origin).resolve()
        if not any(location.is_relative_to(root) for root in roots):
            external.append(f'{name}: {location}')
    if external:
        raise RuntimeError('Builder dependencies must be installed into this interpreter environment; '
                           'remove borrowed PYTHONPATH/site-packages and install requirements-release.txt: '
                           + '; '.join(sorted(set(external))))
    return {'executable': sys.executable, 'python': sys.version, 'prefix': sys.prefix,
            'base_prefix': sys.base_prefix, 'site_packages': [str(root) for root in roots],
            'distributions': dict(sorted(versions.items(), key=lambda item: item[0].lower()))}


def audit_package(package):
    """Inventory contents; report legal duplicates and reject unreviewed runtime duplication."""
    package = Path(package)
    files = []
    contents = defaultdict(list)
    binaries = defaultdict(list)
    violations = []
    for path in sorted(package.rglob('*')):
        relative = path.relative_to(package).as_posix()
        if path.is_symlink():
            files.append({'path': relative, 'symlink': str(path.readlink())})
            continue
        if not path.is_file():
            continue
        size = path.stat().st_size
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        files.append({'path': relative, 'bytes': size, 'sha256': digest})
        if size:
            contents[(digest, size)].append(relative)
        name = path.name.lower()
        if path.suffix.lower() in {'.dll', '.pyd', '.so', '.dylib'} or '.so.' in name:
            binaries[(name, digest)].append(relative)
        if path.suffix.lower() in {'.py', '.pyc'}:
            violations.append('Unexpected loose Python source/bytecode: ' + relative)
        if path.suffix.lower() in {'.sqlite', '.sqlite3', '.db', '.onnx', '.safetensors'}:
            violations.append('Unexpected bundled database/model: ' + relative)
    for paths in binaries.values():
        if len(paths) > 1:
            violations.append('Duplicate binary with identical name and contents: ' + ', '.join(paths))
    duplicates = [{'sha256': digest, 'bytes': size, 'paths': paths}
                  for (digest, size), paths in contents.items() if len(paths) > 1]
    return {'file_count': len(files), 'unpacked_bytes': sum(row.get('bytes', 0) for row in files),
            'files': files, 'duplicate_contents': duplicates, 'violations': violations}
