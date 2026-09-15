#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
arch=${RELEASE_ARCH:?Set RELEASE_ARCH to amd64 or arm64}
case "$arch" in amd64|arm64) ;; *) exit 2 ;; esac
mkdir -p artifacts public-download build/stage/opt build/public-charts
# Anonymous pull credentials are isolated from the runner and the user's Docker config.
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d)
trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
curl --fail --silent --show-error --location \
  https://api.github.com/repos/SamuelSupe/morrowsql/releases/tags/v8.4.11-1 \
  --output artifacts/public-release.json
python3 - <<'PY'
import json, pathlib, subprocess
release = json.load(open('artifacts/public-release.json'))
assert not release['draft'] and not release['prerelease']
for asset in release['assets']:
    name = asset['name']
    assert pathlib.Path(name).name == name
    subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location',
                    asset['browser_download_url'], '--output', 'public-download/' + name], check=True)
PY
(cd public-download && sha256sum --check SHA256SUMS)
curl --fail --silent --show-error --location \
  https://api.github.com/repos/SamuelSupe/morrowsql/git/ref/tags/v8.4.11-1 \
  --output artifacts/public-tag.json
python3 - <<'PY'
import json, subprocess
report = json.load(open('public-download/validation.json'))
assert json.load(open('artifacts/public-tag.json'))['object']['sha'] == report['revision']
images = json.load(open('public-download/images.json'))
for reference, expected in images.items():
    actual = json.loads(subprocess.check_output(['docker','buildx','imagetools','inspect',reference,
                                                '--format','{{json .Manifest}}'],text=True))
    assert actual['digest'] == expected['digest']
    assert {m['platform']['architecture'] for m in actual['manifests']} == {'amd64','arm64'}
    subprocess.run(['docker','pull', reference + '@' + expected['digest']],check=True)
    subprocess.run(['docker','tag',reference + '@' + expected['digest'],reference],check=True)
PY
docker tag ghcr.io/samuelsupe/morrowsql:8.4.11-1 morrowsql:8.4.11-1
docker tag ghcr.io/samuelsupe/morrowsql/8.4.11-1/community-router:8.4.11 morrowsql-router:8.4.11-1
docker tag ghcr.io/samuelsupe/morrowsql/8.4.11-1/community-operator:8.4.9-2.1.11 morrowsql-operator:8.4.11-1
docker build -f docker/builder.Dockerfile -t morrowsql-builder:8.4.11-1 .
mkdir -p build/stage/opt/morrowsql
tar -xzf "public-download/morrowsql-8.4.11-1-linux-$arch.tar.gz" \
  --strip-components=1 -C build/stage/opt/morrowsql
bash scripts/test-standalone.sh
bash scripts/test-package.sh "public-download/morrowsql-8.4.11-1-linux-$arch.tar.gz"
for chart in morrowsql morrowsql-operator; do
  tar -xzf "public-download/$chart-1.0.0.tgz" -C build/public-charts
done
export MORROWSQL_CHART_DIRECTORY="$PWD/build/public-charts"
bash scripts/test-ha.sh
printf '{"anonymousAccess":true,"freshStandalone":true,"freshKubernetes":true,"architecture":"%s"}\n' \
  "$arch" > artifacts/public-install.json
