"""Install an integrity-pinned, project-local HWP engine; no global configuration."""
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def setup():
    manifest = json.loads((ROOT / 'scripts/hwp-release.json').read_text())
    machine = {'arm64': 'aarch64', 'AMD64': 'x86_64'}.get(platform.machine(), platform.machine())
    system = {'Darwin': 'apple-darwin', 'Linux': 'unknown-linux-gnu'}.get(platform.system())
    target = f'{machine}-{system}'
    if target not in manifest['sha256']: raise ValueError(f'지원되지 않는 플랫폼: {target}')
    asset = f'hwp-v{manifest["version"]}-{target}.tar.gz'
    url = f'https://github.com/{manifest["repository"]}/releases/download/v{manifest["version"]}/{asset}'
    with urllib.request.urlopen(url, timeout=120) as response: data = response.read()
    if hashlib.sha256(data).hexdigest() != manifest['sha256'][target]: raise ValueError('HWP engine checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        member = archive.getmember('hwp')
        if not member.isfile(): raise ValueError('Unexpected executable type')
        payload = archive.extractfile(member).read()
    folder = ROOT / 'data/bin'; folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / 'hwp.install'
    temporary.write_bytes(payload); temporary.chmod(0o755); temporary.replace(folder / 'hwp')
    (folder / 'hwp-receipt.json').write_text(json.dumps({'version': manifest['version'], 'url': url,
                'archive_sha256': manifest['sha256'][target], 'binary_sha256': hashlib.sha256(payload).hexdigest()}, indent=2))
    jar_info = manifest['hwplib']
    jar = folder / f"hwplib-{jar_info['version']}.jar"
    if not jar.exists() or hashlib.sha256(jar.read_bytes()).hexdigest() != jar_info['sha256']:
        with urllib.request.urlopen(jar_info['url'], timeout=120) as response: payload = response.read()
        if hashlib.sha256(payload).hexdigest() != jar_info['sha256']: raise ValueError('hwplib checksum mismatch')
        jar.write_bytes(payload)
    javac = shutil.which('javac')
    for candidate in ['/opt/homebrew/opt/openjdk/bin/javac', '/usr/local/opt/openjdk/bin/javac']:
        if Path(candidate).exists(): javac = candidate; break
    if not javac: raise ValueError('JDK 17 이상이 필요합니다. macOS: brew install openjdk')
    sources = sorted((ROOT / 'tools/layout-java').glob('*.java'))
    subprocess.run([javac, '-encoding', 'UTF-8', '-cp', str(jar), '-d', str(folder), *map(str, sources)], check=True)
    (folder / 'java-receipt.json').write_text(json.dumps({'library': jar_info,
        'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}, indent=2))
    print('HWP 읽기·MCP 엔진과 원본 양식 삽입 도구 설치 완료.')


if __name__ == '__main__': setup()
