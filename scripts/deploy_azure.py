"""Deploy Python sources through Kudu ZipDeploy, then verify Oryx and HTTP readiness.

AZURE_PUBLISH_PROFILE is read only from the environment and never logged.
The source archive deliberately contains no virtualenv; Oryx must build it.
"""
import argparse
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
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


def request(session, method, url, *, allowed_statuses=(200, 202), **kwargs):
    try:
        result = session.request(method, url, timeout=60, allow_redirects=False, **kwargs)
    except requests.RequestException:
        raise RuntimeError('Azure request failed; inspect connectivity without exposing credentials') from None
    if result.status_code not in allowed_statuses:
        # Server bodies and exception strings can echo credentials. Never print them.
        raise RuntimeError(f'Azure request returned HTTP {result.status_code}')
    return result


def submit_archive(session, endpoint, archive, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # A 409 rejects the submission. Reopen to resend from byte zero once free.
        # Never retry an ambiguous network failure: that could submit the ZIP twice.
        with Path(archive).open('rb') as stream:
            result = request(session, 'POST', endpoint + '/api/zipdeploy?isAsync=true',
                             data=stream, headers={'Content-Type': 'application/zip'},
                             allowed_statuses=(200, 202, 409))
        if result.status_code != 409:
            return result
        print('Kudu busy (HTTP 409); waiting 15s before resubmitting ZIP.', flush=True)
        time.sleep(15)
    raise RuntimeError('Azure SCM remains busy after 10 minutes; inspect active deployment in Deployment Center')


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
    result = submit_archive(session, endpoint, archive)
    location = result.headers.get('Location')
    if not location:
        raise RuntimeError('Azure did not return a deployment status URL')
    # Kudu may report its internal proxy origin or an explicit :443. Only use
    # its deployment resource path; keep all authenticated calls on our SCM host.
    polling_path = urlsplit(location).path
    if not re.fullmatch(r'/api/deployments/[A-Za-z0-9][A-Za-z0-9_.-]*', polling_path):
        raise ValueError('Invalid deployment polling path; refusing another origin')
    polling_url = endpoint + polling_path
    wait_for_deployment(session, polling_url, 1200)
    try:
        manifest = request(session, 'GET', endpoint + '/api/vfs/site/wwwroot/oryx-manifest.toml')
    except RuntimeError:
        raise RuntimeError('Oryx build manifest unavailable; verify remote build settings and logs') from None
    if 'antenv' not in manifest.text:
        raise RuntimeError('Oryx manifest does not identify the Python virtual environment')
    wait_for_login(public_url, 300)
    print('ZipDeploy, Oryx manifest and application login verified.', flush=True)


def diagnose(profile_xml, app_name):
    """Read only status flags and expected filenames, never configuration values."""
    endpoint, credentials, _ = publish_target(profile_xml, app_name)
    session = requests.Session()
    session.auth = credentials
    try:
        latest = request(session, 'GET', endpoint + '/api/deployments/latest').json()
        print('Previous Kudu deployment:',
              'status=', int(latest.get('status', -1)),
              'complete=', bool(latest.get('complete')),
              'active=', bool(latest.get('active')), flush=True)
        entries = request(session, 'GET', endpoint + '/api/vfs/site/wwwroot/').json()
        expected = {'run.py', 'gunicorn.conf.py', 'requirements.txt', '.deployment',
                    'oryx-manifest.toml', 'output.tar.gz', 'antenv'}
        present = {item.get('name') for item in entries} & expected
        print('Expected runtime entries present:', ', '.join(sorted(present)), flush=True)
    except (RuntimeError, ValueError, TypeError):
        print('SCM diagnostic unavailable; deployment will report its own result.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--app-name', required=True)
    parser.add_argument('--diagnose-only', action='store_true')
    args = parser.parse_args()
    try:
        profile_xml = os.environ.get('AZURE_PUBLISH_PROFILE', '')
        if args.diagnose_only:
            diagnose(profile_xml, args.app_name)
        else:
            deploy(args.package, profile_xml, args.app_name)
    except (ValueError, RuntimeError, OSError) as error:
        # Keep CLI failure diagnostics useful without dumping XML, HTTP bodies or secrets.
        if isinstance(error, (ValueError, RuntimeError)):
            print(f'::error::{error}', file=sys.stderr)
        else:
            print('::error::Cannot read the deployment package', file=sys.stderr)
        sys.exit(1)
