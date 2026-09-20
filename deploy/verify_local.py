"""Check production images against disposable PostgreSQL and a local HTTPS proxy.

Run from the project root: python deploy/verify_local.py
Requires Docker and the two production images already built. Creates no AWS resources.
"""
import json
from pathlib import Path
import secrets
import ssl
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


prefix = 'uml-verify-' + secrets.token_hex(4)
network = prefix + '-net'
containers = []
volume = prefix + '-static'


def docker(*args, capture=True):
    result = subprocess.run(['docker', *args], check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else ''


def container(name, *args):
    containers.append(name)
    return docker('run', '-d', '--name', name, '--network', network, *args)


def request(method, path, body=None, token=None, expected=200):
    headers = {'Host': 'localhost', 'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Token ' + token
    req = Request(base + path, data=None if body is None else json.dumps(body).encode(),
                  headers=headers, method=method)
    # Only this disposable localhost proxy uses an internal certificate.
    try:
        with urlopen(req, timeout=20, context=ssl._create_unverified_context()) as response:
            status, payload = response.status, response.read()
    except HTTPError as error:
        status, payload = error.code, error.read()
    assert status == expected, f'{method} {path}: {status}, expected {expected}: {payload[:200]!r}'
    return payload


try:
    docker('network', 'create', network)
    database = prefix + '-db'
    container(database, '--network-alias', 'db', '-e', 'POSTGRES_DB=diagrama',
              '-e', 'POSTGRES_USER=app', '-e', 'POSTGRES_PASSWORD=local-verify-only', 'postgres:17')
    for attempt in range(60):
        result = subprocess.run(['docker', 'exec', database, 'pg_isready', '-U', 'app', '-d', 'diagrama'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Temporary PostgreSQL did not become ready')
    environment = {
        'DJANGO_SETTINGS_MODULE': 'backend.settings_production', 'DEBUG': 'False',
        'SECRET_KEY': secrets.token_urlsafe(64), 'ALLOWED_HOSTS': 'localhost',
        'DB_ENGINE': 'postgres', 'DB_NAME': 'diagrama', 'DB_USER': 'app',
        'DB_PASSWORD': 'local-verify-only', 'DB_HOST': 'db', 'DB_PORT': '5432',
        'DB_SSLMODE': 'disable', 'GENERADOR_TMP_DIR': '/var/lib/uml/generados',
        'TRUST_PROXY_SSL_HEADER': 'true', 'CSRF_TRUSTED_ORIGINS': 'https://localhost',
    }
    env_args = [item for key, value in environment.items() for item in ('-e', key + '=' + value)]
    backend = prefix + '-backend'
    container(backend, '--network-alias', 'backend', *env_args,
              '--mount', f'type=volume,source={volume},target=/app/staticfiles',
              'examen-production-backend')
    for command in [('check', '--deploy'), ('migrate', '--noinput'), ('collectstatic', '--noinput')]:
        docker('exec', backend, 'python', 'manage.py', *command, capture=False)
    # Tests use development settings against the disposable database, so HTTPS
    # redirects do not change the existing APIClient fixtures.
    docker('exec', '-e', 'DJANGO_SETTINGS_MODULE=backend.settings',
           '-e', 'ALLOWED_HOSTS=localhost,testserver,127.0.0.1', backend,
           'python', 'manage.py', 'test', '--noinput', capture=False)
    container(prefix + '-frontend', '--network-alias', 'frontend', 'examen-production-frontend')
    proxy = prefix + '-proxy'
    caddyfile = str((Path(__file__).resolve().parent / 'Caddyfile'))
    container(proxy, '-p', '127.0.0.1::443', '-e', 'SITE_DOMAIN=localhost',
              '--mount', f'type=bind,source={caddyfile},target=/etc/caddy/Caddyfile,readonly',
              '--mount', f'type=volume,source={volume},target=/srv/static,readonly', 'caddy:2-alpine')
    port = docker('port', proxy, '443/tcp').rsplit(':', 1)[-1]
    base = 'https://localhost:' + port
    for attempt in range(60):
        try:
            request('GET', '/api/health/')
            break
        except (URLError, AssertionError, ConnectionError, TimeoutError):
            time.sleep(1)
    else:
        raise RuntimeError('Production HTTPS routing did not become ready')
    assert b'<html' in request('GET', '/')
    assert b'<html' in request('GET', '/editor/example')
    request('GET', '/static/admin/css/base.css')
    request('GET', '/api/projects/', expected=401)
    auth = json.loads(request('POST', '/api/auth/register/', {
        'username': prefix, 'password': secrets.token_urlsafe(24)}, expected=201))
    token = auth['token']
    project = json.loads(request('POST', '/api/projects/', {'name': 'Production verify'}, token, 201))
    diagram = json.loads(request('POST', '/api/diagrams/', {'project': project['id'], 'name': 'Verify'}, token, 201))
    request('POST', '/api/classes/', {'diagram': diagram['id'], 'name': 'Objects'}, token, 201)
    generation = json.loads(request('POST', '/api/generar-backend/', {
        'diagrama_id': diagram['id'], 'autocorregir': True}, token, 201))
    assert generation['entidades_generadas'] == ['ObjectsModelo']
    from urllib.parse import urlparse
    import hashlib
    payload = request('GET', urlparse(generation['zip_url']).path, token=token)
    assert len(payload) == generation['tamano_bytes']
    assert hashlib.sha256(payload).hexdigest() == generation['sha256']
    request('POST', '/api/auth/logout/', token=token, expected=204)
    request('GET', '/api/projects/', token=token, expected=401)
    print('PASS: production images, PostgreSQL tests, HTTPS routing, SPA, admin static, auth, generation and ZIP integrity', flush=True)
finally:
    for name in reversed(containers):
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['docker', 'network', 'rm', network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['docker', 'volume', 'rm', volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
