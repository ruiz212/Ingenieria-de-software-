"""Deploy Python sources through Kudu ZipDeploy, then verify Oryx and HTTP readiness.

AZURE_PUBLISH_PROFILE is read only from the environment and never logged.
The source archive deliberately contains no virtualenv; Oryx must build it.
"""
import argparse
import os
from pathlib import Path
import sys
import time
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import requests

# Support both `python scripts/deploy_azure.py` and import by tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.build_deployment import validate_archive


def publish_target(profile_xml, app_name):
    try:
        root = ElementTree.fromstring(profile_xml)
    except ElementTree.ParseError:
        raise ValueError('Invalid Azure publish profile XML') from None
    for profile in root.iter('publishProfile'):
        if profile.get('publishMethod') not in {'MSDeploy', 'ZipDeploy'}:
            continue
        if profile.get('msdeploySite', '').lower() != app_name.lower():
            continue
        address = profile.get('publishUrl', '')
        endpoint = urlsplit(address if '://' in address else 'https://' + address)
        host = endpoint.hostname or ''
        if endpoint.scheme != 'https' or '.scm.' not in host or not host.endswith('.azurewebsites.net'):
            raise ValueError('Invalid SCM target host')
        credentials = (profile.get('userName'), profile.get('userPWD'))
        if not all(credentials):
            raise ValueError('Missing publish credentials')
        # Derive the public origin from the validated SCM host, never a profile redirect.
        if endpoint.port not in {None, 443} or endpoint.username or endpoint.password:
            raise ValueError('Invalid SCM target host')
        return 'https://' + host, credentials, 'https://' + host.replace('.scm.', '.', 1)
    raise ValueError('Publish profile does not match the requested app target')


def request(session, method, url, **kwargs):
    try:
        result = session.request(method, url, timeout=60, allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise RuntimeError('Azure request failed; inspect connectivity without exposing credentials') from None
    if result.status_code not in {200, 202}:
        # Server bodies and exception strings can echo credentials. Never print them.
        raise RuntimeError(f'Azure request returned HTTP {result.status_code}')
    return result


def wait_for_deployment(session, url, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = request(session, 'GET', url).json().get('status')
        if status == 4:
            return
        if status == 3:
            raise RuntimeError('Azure deployment failed; inspect Deployment Center build logs')
        print(f'Kudu deployment status: {status}', flush=True)
        time.sleep(15)
    raise RuntimeError('Timed out waiting for Azure deployment')


def wait_for_login(public_url, timeout):
    # Never send SCM authentication to the application's public endpoint.
    session = requests.Session()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = session.request('GET', public_url + '/login', timeout=20, allow_redirects=False)
            if result.status_code == 200 and 'name="csrf_token"' in result.text:
                return
        except requests.RequestException:
            pass
        time.sleep(10)
    raise RuntimeError('Application login is not ready after deployment')


def deploy(archive, profile_xml, app_name):
    validate_archive(archive)
    endpoint, credentials, public_url = publish_target(profile_xml, app_name)
    session = requests.Session()
    session.auth = credentials
    with Path(archive).open('rb') as stream:
        result = request(session, 'POST', endpoint + '/api/zipdeploy?isAsync=true',
                         data=stream, headers={'Content-Type': 'application/zip'})
    location = result.headers.get('Location')
    if not location:
        raise RuntimeError('Azure did not return a deployment status URL')
    polling_url = urljoin(endpoint, location)
    parsed = urlsplit(polling_url)
    if (parsed.scheme, parsed.netloc) != (urlsplit(endpoint).scheme, urlsplit(endpoint).netloc):
        raise ValueError('Deployment polling URL has a different origin')
    wait_for_deployment(session, polling_url, 1200)
    try:
        manifest = request(session, 'GET', endpoint + '/api/vfs/site/wwwroot/oryx-manifest.toml')
    except RuntimeError:
        raise RuntimeError('Oryx build manifest unavailable; verify remote build settings and logs') from None
    if 'antenv' not in manifest.text:
        raise RuntimeError('Oryx manifest does not identify the Python virtual environment')
    wait_for_login(public_url, 300)
    print('ZipDeploy, Oryx manifest and application login verified.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--app-name', required=True)
    args = parser.parse_args()
    try:
        deploy(args.package, os.environ.get('AZURE_PUBLISH_PROFILE', ''), args.app_name)
    except (ValueError, RuntimeError, OSError) as error:
        # Keep CLI failure diagnostics useful without dumping XML, HTTP bodies or secrets.
        if isinstance(error, (ValueError, RuntimeError)):
            print(f'::error::{error}', file=sys.stderr)
        else:
            print('::error::Cannot read the deployment package', file=sys.stderr)
        sys.exit(1)
