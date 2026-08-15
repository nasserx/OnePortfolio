"""Contract tests for externally usable password-reset URLs."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from config import Config
from portfolio_app import create_app
from portfolio_app.utils import email as email_utils


_REPO_ROOT = Path(__file__).resolve().parents[1]
_LOCAL_STARTUP_PROBE = r"""
import json
import runpy

from flask import Flask


def capture_run(app, *args, **kwargs):
    print(json.dumps({
        'app_base_url': app.config['APP_BASE_URL'],
        'debug': app.debug,
        'run_debug': kwargs.get('debug'),
    }))


Flask.run = capture_run
runpy.run_path('app.py', run_name='__main__')
"""


class _BaseUrlTestConfig(Config):
    SECRET_KEY = 'base-url-test-secret'
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = False
    GOOGLE_OAUTH_ENABLED = False
    TESTING = False
    DEBUG = False


def _config_for(db_path: Path, **overrides):
    class _Config(_BaseUrlTestConfig):
        SQLALCHEMY_DATABASE_URI = (
            f"sqlite:///{db_path.resolve().as_posix()}"
        )

    for key, value in overrides.items():
        setattr(_Config, key, value)
    return _Config


def test_valid_production_url_is_normalized_at_startup(tmp_path):
    app = create_app(_config_for(
        tmp_path / 'valid.sqlite',
        APP_BASE_URL='  https://portfolio.example/  ',
    ))

    assert app.config['APP_BASE_URL'] == 'https://portfolio.example'


def test_blank_production_url_fails_startup(tmp_path):
    with pytest.raises(
        RuntimeError,
        match='APP_BASE_URL must be configured as an absolute HTTPS URL',
    ):
        create_app(_config_for(
            tmp_path / 'blank.sqlite',
            APP_BASE_URL='   ',
        ))


@pytest.mark.parametrize(
    'value',
    (
        'portfolio.example',
        'ftp://portfolio.example',
        'https://',
        'https://user:secret@portfolio.example',
        'https://portfolio.example?source=reset',
        'https://portfolio.example#reset',
        'https://portfolio.example:invalid',
        'https://portfolio.example:',
        'http://portfolio.example',
    ),
)
def test_malformed_or_insecure_production_url_fails_startup(tmp_path, value):
    with pytest.raises(RuntimeError, match='APP_BASE_URL'):
        create_app(_config_for(
            tmp_path / 'invalid.sqlite',
            APP_BASE_URL=value,
        ))


@pytest.mark.parametrize(
    'value',
    (
        'https://-portfolio.example',
        'https://portfolio-.example',
        'https://port_folio.example',
        'https://portfolio..example',
        'https://%zz.example',
        'https://999.999.999.999',
    ),
)
def test_malformed_hostname_labels_fail_startup(tmp_path, value):
    with pytest.raises(RuntimeError, match='invalid hostname'):
        create_app(_config_for(
            tmp_path / 'invalid-host.sqlite',
            APP_BASE_URL=value,
        ))


@pytest.mark.parametrize(
    'value',
    (
        'https://portfolio.example/application',
        'https://portfolio.example/application/',
        'https://portfolio.example//',
    ),
)
def test_non_root_path_fails_origin_only_contract(tmp_path, value):
    with pytest.raises(RuntimeError, match='origin without a path'):
        create_app(_config_for(
            tmp_path / 'path.sqlite',
            APP_BASE_URL=value,
        ))


@pytest.mark.parametrize(
    'mode',
    ('testing', 'debug'),
)
def test_blank_debug_or_test_url_uses_deterministic_local_fallback(
    tmp_path,
    mode,
):
    app = create_app(_config_for(
        tmp_path / f'{mode}.sqlite',
        APP_BASE_URL='',
        TESTING=mode == 'testing',
        DEBUG=mode == 'debug',
    ))

    assert app.config['APP_BASE_URL'] == 'http://127.0.0.1:5000'


def test_python_app_entry_point_enables_development_before_url_validation():
    environment = os.environ.copy()
    environment.update({
        'APP_BASE_URL': '',
        'DATABASE_URL': 'sqlite:///:memory:',
        'GOOGLE_OAUTH_ENABLED': '0',
        'RATELIMIT_ENABLED': '0',
        'SECRET_KEY': 'local-entry-point-test-secret',
    })
    result = subprocess.run(
        [sys.executable, '-B', '-c', _LOCAL_STARTUP_PROBE],
        cwd=_REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    probe = json.loads(result.stdout.strip().splitlines()[-1])
    assert probe == {
        'app_base_url': 'http://127.0.0.1:5000',
        'debug': True,
        'run_debug': True,
    }


def test_reset_email_contains_configured_absolute_url(tmp_path, monkeypatch):
    app = create_app(_config_for(
        tmp_path / 'email.sqlite',
        APP_BASE_URL='https://portfolio.example/',
        TESTING=True,
    ))
    delivered = []
    monkeypatch.setattr(email_utils.mail, 'send', delivered.append)

    with app.app_context():
        assert email_utils.send_reset_email(
            'recipient@example.com',
            'signed-reset-token',
        ) is True

    assert len(delivered) == 1
    assert (
        'https://portfolio.example/reset-password/signed-reset-token'
    ) in delivered[0].body
    assert '/reset-password/signed-reset-token' in delivered[0].body


def test_debug_mode_accepts_explicit_http_url(tmp_path):
    app = create_app(_config_for(
        tmp_path / 'debug-http.sqlite',
        APP_BASE_URL='http://localhost:5001/',
        DEBUG=True,
    ))

    assert app.config['APP_BASE_URL'] == 'http://localhost:5001'


@pytest.mark.parametrize(
    'value',
    (
        'http://localhost:5001',
        'http://127.0.0.1:5001',
        'http://[::1]:5001',
    ),
)
def test_debug_mode_accepts_localhost_and_ip_origins(tmp_path, value):
    app = create_app(_config_for(
        tmp_path / 'debug-host.sqlite',
        APP_BASE_URL=value,
        DEBUG=True,
    ))

    assert app.config['APP_BASE_URL'] == value
