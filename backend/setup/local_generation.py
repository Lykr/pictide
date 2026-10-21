"""Pinned Windows ComfyUI preparation and complete model/workflow recipes."""
from dataclasses import asdict, dataclass
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request

from ..network import open_url as urlopen


COMFY_VERSION = 'v0.42.1'
_RELEASE = f'https://github.com/Comfy-Org/ComfyUI/releases/download/{COMFY_VERSION}'
_ANIMA = 'https://huggingface.co/circlestone-labs/Anima/resolve/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files'
_RANGE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class Resource:
    path: str
    url: str
    size: int
    sha256: str


def _archive(name, size, sha256):
    filename = f'ComfyUI_windows_portable_{name}.7z'
    return Resource(filename, f'{_RELEASE}/{filename}', size, sha256)


_NVIDIA = _archive('nvidia', 2018444114, '496afd18790ec685d99ebba2edf200d7371a29fbdd3a992bb0f4f52f244a6874')
_CU126 = _archive('nvidia_cu126', 1910153206, '0506abc6563ea5928a052fe0bc0b32c2a063098558bd593fe39345a27f1e47fc')
PROFILES = {
    'nvidia': ('NVIDIA', _NVIDIA),
    'nvidia-cu126': ('NVIDIA (CUDA 12.6)', _CU126),
    'amd': ('AMD', _archive('amd', 1636139353, '8af051e342de65e5ca2d9f43a5f0b11a6377da10bd96159dc41e8722cc5841fc')),
    'intel': ('Intel', _archive('intel', 1451207360, 'a1e03d31ea364af2f80820461cd0c5ae5bbba4b562c023c1f43b2cf65541d4ab')),
    'cpu': ('CPU', _CU126),
}
EXTRACTOR = Resource('7zr-26.04.exe', 'https://github.com/ip7z/7zip/releases/download/26.04/7zr.exe',
                     602624, '256feca8e274e5da655e2a284fabafd9f554365eb164862089dacd4e8276d282')


@dataclass(frozen=True)
class HardwareRequirements:
    min_vram_gib: int
    min_ram_gib: int
    profiles: tuple[str, ...]

    def __post_init__(self):
        if (type(self.min_vram_gib) is not int or self.min_vram_gib <= 0 or
                type(self.min_ram_gib) is not int or self.min_ram_gib <= 0 or
                not self.profiles or any(profile not in PROFILES for profile in self.profiles)):
            raise ValueError('Model hardware requirements must specify VRAM, RAM and supported environments')


def capacity_gib(value):
    # DXGI excludes some driver-reserved memory; use nominal capacity tiers with
    # at most 512 MiB rounding. Never include shared memory or combine adapters.
    return int((value + 512 * 1024 ** 2) // 1024 ** 3) if value is not None else None


def hardware_issues(requirements, hardware, profile_id):
    """Fail closed before download; return structured reasons for the TUI."""
    from .windows_hardware import select_gpu
    if not requirements:
        return [{'code': 'requirements_missing'}]
    if profile_id not in requirements['profiles']:
        return [{'code': 'environment'}]
    issues = []
    gpu = select_gpu(hardware, profile_id)
    if gpu is None:
        issues.append({'code': 'gpu_missing'})
    else:
        actual = capacity_gib(gpu.get('vram_bytes'))
        if actual is None or actual < requirements['min_vram_gib']:
            issues.append({'code': 'vram', 'required': requirements['min_vram_gib'], 'actual': actual})
    actual = capacity_gib(hardware.get('ram_bytes'))
    if actual is None or actual < requirements['min_ram_gib']:
        issues.append({'code': 'ram', 'required': requirements['min_ram_gib'], 'actual': actual})
    return issues


@dataclass(frozen=True)
class ModelRecipe:
    """A recommended model is installable only with its complete API workflow."""
    id: str
    name: str
    files: tuple[Resource, ...]
    workflow_file: str
    bindings: dict
    output_nodes: tuple[str, ...]
    license_name: str
    license_url: str
    hardware: HardwareRequirements
    noncommercial: bool = False

    def connection(self, base_url):
        if not isinstance(self.hardware, HardwareRequirements):
            raise ValueError(f'Missing model hardware requirements: {self.id}')
        if not self.files or not self.workflow_file or not self.output_nodes:
            raise ValueError(f'Incomplete model recipe: {self.id}')
        # The same canonical workflow is copied by the portable builder, not duplicated.
        directory = (Path(__file__).resolve().parents[1] / 'workflows' if getattr(sys, 'frozen', False)
                     else Path(__file__).resolve().parents[2] / 'docs/assets/workflows')
        workflow = json.loads((directory / self.workflow_file).read_text(encoding='utf-8'))
        from ..generation import validate_backend
        config = dict(id=f'local-{self.id}', name=self.name, kind='comfyui', base_url=base_url,
                      workflow=workflow, bindings=copy.deepcopy(self.bindings),
                      output_nodes=list(self.output_nodes))
        validated = validate_backend(config)
        return dict(validated, workflow_mode='custom', workflow_name=self.name)


RECIPES = {
    'anima-turbo-v1-1': ModelRecipe(
        'anima-turbo-v1-1', 'Anima Turbo v1.1', (
            Resource('diffusion_models/anima-turbo-v1.1.safetensors',
                     f'{_ANIMA}/diffusion_models/anima-turbo-v1.1.safetensors?download=true',
                     4182230656, 'fba11953276b57edf59d1dc4f1857ac05aa079c56f982b4d7c20298d57d3f7eb'),
            Resource('text_encoders/qwen_3_06b_base.safetensors',
                     f'{_ANIMA}/text_encoders/qwen_3_06b_base.safetensors?download=true',
                     1192135096, 'cd2a512003e2f9f3cd3c32a9c3573f820bb28c940f73c57b1ddaa983d9223eba'),
            Resource('vae/qwen_image_vae.safetensors',
                     f'{_ANIMA}/vae/qwen_image_vae.safetensors?download=true',
                     253806246, 'a70580f0213e67967ee9c95f05bb400e8fb08307e017a924bf3441223e023d1f'),
        ), 'anima-turbo-v1.1.api.json',
        {'positive': {'node_id': '11', 'input': 'text'},
         'negative': {'node_id': '12', 'input': 'text'},
         'seed': {'node_id': '19', 'input': 'seed'}}, ('1',),
        'CircleStone Labs Non-Commercial License',
        'https://huggingface.co/circlestone-labs/Anima/blob/main/LICENSE.md',
        HardwareRequirements(8, 16, ('nvidia', 'nvidia-cu126', 'amd', 'intel')), True),
}


def profile_catalog():
    return {key: {'name': name, 'size': resource.size + EXTRACTOR.size,
                  'required_space': resource.size * 4}
            for key, (name, resource) in PROFILES.items()}


def recipe_catalog():
    result = {}
    for key, recipe in RECIPES.items():
        recipe.connection('http://127.0.0.1:8188')
        result[key] = dict(name=recipe.name, size=sum(item.size for item in recipe.files),
                           license_name=recipe.license_name, license_url=recipe.license_url,
                           hardware=asdict(recipe.hardware),
                           noncommercial=recipe.noncommercial)
    return result


def model_connection(recipe_id, base_url):
    return RECIPES[recipe_id].connection(base_url)


def _emit(progress, phase, name, downloaded=0, total=0, speed=0):
    progress(dict(phase=phase, name=name, downloaded=downloaded, total=total, speed=speed))


def _verified(path, resource, progress):
    if not path.is_file() or path.stat().st_size != resource.size:
        return False
    digest = hashlib.sha256()
    received = 0
    with path.open('rb') as source:
        while chunk := source.read(4 * 1024 * 1024):
            digest.update(chunk)
            received += len(chunk)
            _emit(progress, 'verify', resource.path, received, resource.size)
    return digest.hexdigest() == resource.sha256


def download_resource(resource, destination, progress=lambda event: None):
    """Resume fixed-size HTTP ranges, verify SHA256, then publish atomically."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if _verified(destination, resource, progress):
            return destination
        raise FileExistsError(f'Existing file differs from the pinned resource: {destination}')
    partial = destination.with_name(destination.name + '.part')
    if partial.exists() and partial.stat().st_size >= resource.size:
        if _verified(partial, resource, progress):
            os.replace(partial, destination)
            return destination
        # An invalid partial belongs to this installer; the user's target stays untouched.
        partial.unlink()
    started = time.monotonic()
    initial = partial.stat().st_size if partial.exists() else 0
    failed = 0
    while (offset := partial.stat().st_size if partial.exists() else 0) < resource.size:
        end = min(resource.size, offset + _RANGE_BYTES) - 1
        # HF/CDN redirects can cache a signed response for an earlier range. A distinct
        # URL for each offset avoids reusing it while preserving download/source options.
        url = urlsplit(resource.url)
        query = [(key, value) for key, value in parse_qsl(url.query, keep_blank_values=True)
                 if key != 'pictide_part']
        query.append(('pictide_part', str(offset)))
        range_url = urlunsplit((url.scheme, url.netloc, url.path, urlencode(query), url.fragment))
        request = Request(range_url, headers={'User-Agent': 'Pictide local setup',
                                                'Range': f'bytes={offset}-{end}'})
        try:
            with urlopen(request, timeout=20) as response:
                status = response.status
                if status == 206:
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                    if not match or tuple(map(int, match.groups())) != (offset, end, resource.size):
                        raise ValueError('Unexpected HTTP download range')
                elif status == 200:
                    # Some hosts ignore Range. Restart from zero instead of appending duplicates.
                    offset, end = 0, resource.size - 1
                else:
                    raise ValueError(f'Unexpected download status: {status}')
                received = offset
                with partial.open('ab' if offset else 'wb') as output:
                    read = getattr(response, 'read1', response.read)
                    while chunk := read(min(256 * 1024, end - received + 1)):
                        output.write(chunk)
                        received += len(chunk)
                        _emit(progress, 'download', resource.path, received, resource.size,
                              max(0, received - initial) / max(.001, time.monotonic() - started))
                        if received == end + 1:
                            break
                if received != end + 1:
                    raise OSError('Download ended before the requested range completed')
            failed = 0
        except (OSError, ValueError):
            failed += 1
            if failed >= 3:
                raise
            time.sleep(.5)
    if not _verified(partial, resource, progress):
        partial.unlink()
        raise ValueError(f'SHA256 verification failed: {resource.path}')
    os.replace(partial, destination)
    return destination


def _installed(install, profile_id):
    marker = install / 'pictide-install.json'
    if not marker.is_file():
        return False
    record = json.loads(marker.read_text(encoding='utf-8'))
    return (record.get('version') == COMFY_VERSION and record.get('profile_id') == profile_id
            and (install / 'python_embeded/python.exe').is_file()
            and (install / 'ComfyUI/main.py').is_file())


def _extract(archive, extractor, staging, progress):
    log = staging / 'extract.log'
    _emit(progress, 'extract', archive.name)
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.Popen([str(extractor), 'x', str(archive), f'-o{staging}', '-y', '-bso0', '-bsp0'],
                                   stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while process.poll() is None:
                _emit(progress, 'extract', archive.name)
                time.sleep(.2)
            if process.returncode:
                raise RuntimeError(f'ComfyUI extraction failed: {log.read_text(encoding="utf-8")[-2000:]}')
        except BaseException:
            if process.poll() is None:
                process.terminate()
                process.wait()
            raise


def prepare_local_comfy(paths, profile_id, recipe_id_or_None, progress=lambda event: None):
    """Install only owned runtime/model files; keep downloads resumable on cancellation."""
    _, archive_resource = PROFILES[profile_id]
    recipe = RECIPES[recipe_id_or_None] if recipe_id_or_None else None
    if recipe:
        recipe.connection('http://127.0.0.1:8188')
        from .windows_hardware import detect_hardware
        issues = hardware_issues(asdict(recipe.hardware), detect_hardware(), profile_id)
        if issues:
            raise ValueError('Model hardware requirements not met: ' + ', '.join(item['code'] for item in issues))
    paths.ensure()
    downloads = paths.cache / 'downloads'
    install = paths.runtime / 'comfyui'
    if not _installed(install, profile_id):
        if install.exists():
            raise FileExistsError(f'A different ComfyUI installation already exists: {install}')
        # Space for the archive's expanded Python/PyTorch runtime and model files.
        needed = archive_resource.size * 4 + (sum(item.size for item in recipe.files) if recipe else 0)
        if shutil.disk_usage(paths.root).free < needed:
            raise OSError(f'Not enough free disk space: approximately {needed} bytes required')
        archive = download_resource(archive_resource, downloads / archive_resource.path, progress)
        extractor = download_resource(EXTRACTOR, downloads / EXTRACTOR.path, progress)
        with tempfile.TemporaryDirectory(prefix='comfy-install-', dir=paths.tmp) as temporary:
            staging = Path(temporary)
            _extract(archive, extractor, staging, progress)
            candidates = [path.parent for path in staging.glob('*/python_embeded')
                          if (path / 'python.exe').is_file() and (path.parent / 'ComfyUI/main.py').is_file()]
            if len(candidates) != 1:
                raise RuntimeError('Official ComfyUI archive has an unexpected layout')
            package = candidates[0]
            (package / 'pictide-install.json').write_text(
                json.dumps(dict(version=COMFY_VERSION, profile_id=profile_id)), encoding='utf-8')
            os.rename(package, install)
    if recipe:
        for resource in recipe.files:
            target = paths.models / 'generation' / resource.path
            if target.exists():
                if _verified(target, resource, progress):
                    continue
                raise FileExistsError(f'Existing model differs from the pinned resource: {target}')
            cached = download_resource(resource, downloads / resource.path, progress)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.rename(cached, target)
    return dict(mode='managed', profile_id=profile_id, recipe_id=recipe_id_or_None, install_dir=str(install))
