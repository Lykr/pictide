"""Fixed GitHub release source. Calling read_release is always an explicit action."""
import json
import re
from urllib.parse import quote
from urllib.request import Request

from ..network import open_url
from .contracts import Release

REPOSITORY = 'Lykr/pictide'
API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
PAGE = f'https://github.com/{REPOSITORY}/releases'
PROTOCOL = 1


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('Invalid stable release version')
    return tuple(map(int, value.split('.')))


def read_json(url, *, opener=open_url):
    request = Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'Pictide-updates'})
    with opener(request, timeout=25) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError('Update metadata exceeds the size limit')
    return json.loads(data)


def read_release(current, platform, arch, *, opener=open_url):
    document = read_json(API, opener=opener)
    latest = str(document.get('tag_name', '')).removeprefix('v')
    version(latest)
    page = PAGE + '/tag/v' + latest
    if document.get('draft') or document.get('prerelease'):
        raise ValueError('The latest release is not a stable published release')
    if version(latest) <= version(current):
        return Release(latest, page, False, 'already_current')
    assets = {item['name']: item for item in document.get('assets', [])}
    manifest_asset = assets.get('update.json')
    prefix = PAGE + '/download/v' + latest + '/'
    if not manifest_asset:
        return Release(latest, page, False, 'manual_update')
    if manifest_asset.get('browser_download_url') != prefix + 'update.json':
        raise ValueError('Unexpected update manifest location')
    manifest = read_json(prefix + 'update.json', opener=opener)
    if manifest.get('schema') != PROTOCOL or manifest.get('version') != latest:
        return Release(latest, page, False, 'manual_update')
    allowed = manifest.get('direct_upgrade_from', {})
    if not (version(allowed.get('minimum')) <= version(current) < version(allowed.get('maximum_exclusive'))):
        return Release(latest, page, False, 'incompatible')
    asset = manifest.get('assets', {}).get(platform + '-' + arch)
    if not asset or not asset.get('install_verified'):
        return Release(latest, page, False, 'platform_unverified')
    expected = f'pictide-{latest}-{platform}-{arch}.zip'
    remote = assets.get(expected)
    if (asset.get('name') != expected or not remote or remote.get('browser_download_url') != prefix + quote(expected)
            or type(asset.get('bytes')) is not int or asset['bytes'] <= 0 or asset['bytes'] != remote.get('size')
            or type(asset.get('unpacked_bytes')) is not int or asset['unpacked_bytes'] <= 0
            or not re.fullmatch(r'[0-9a-f]{64}', str(asset.get('sha256', '')))):
        raise ValueError('Invalid release asset metadata')
    if remote.get('digest') and remote['digest'] != 'sha256:' + asset['sha256']:
        raise ValueError('Release asset checksum does not match GitHub metadata')
    return Release(latest, page, True, '', {**asset, 'url': prefix + quote(expected)})
