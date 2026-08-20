"""Regression coverage for strict authentication-cookie configuration."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
_UNSET = object()
_PROBE_SCRIPT = r"""
import json

from flask import session
from flask_login import UserMixin, login_user

from config import Config
from portfolio_app import create_app


class ProbeUser(UserMixin):
    def get_id(self):
        return 'v1:1:0'


app = create_app(Config)


@app.get('/_cookie-config-probe')
def cookie_config_probe():
    session['probe'] = True
    login_user(ProbeUser(), remember=True)
    return 'ok'


response = app.test_client().get('/_cookie-config-probe')
cookie_headers = response.headers.getlist('Set-Cookie')
session_name = app.config.get('SESSION_COOKIE_NAME', 'session')
remember_name = app.config.get('REMEMBER_COOKIE_NAME', 'remember_token')


def cookie_is_secure(name):
    return any(
        header.startswith(f'{name}=') and '; Secure' in header
        for header in cookie_headers
    )


print(json.dumps({
    'session_config': app.config['SESSION_COOKIE_SECURE'],
    'remember_config': app.config['REMEMBER_COOKIE_SECURE'],
    'session_cookie_secure': cookie_is_secure(session_name),
    'remember_cookie_secure': cookie_is_secure(remember_name),
    'hsts': response.headers.get('Strict-Transport-Security'),
}))
"""


def _run_probe(value=_UNSET, *, flask_debug=None):
    env = os.environ.copy()
    env['SECRET_KEY'] = 'cookie-config-test-secret'
    env['DATABASE_URL'] = 'sqlite:///:memory:'

    if value is _UNSET:
        env.pop('SESSION_COOKIE_SECURE', None)
    else:
        env['SESSION_COOKIE_SECURE'] = value

    if flask_debug is None:
        env.pop('FLASK_DEBUG', None)
    else:
        env['FLASK_DEBUG'] = flask_debug

    return subprocess.run(
        [sys.executable, '-B', '-c', _PROBE_SCRIPT],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _successful_probe(value=_UNSET, *, flask_debug=None):
    result = _run_probe(value, flask_debug=flask_debug)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _assert_effective_secure_behavior(probe, expected):
    assert probe['session_config'] is expected
    assert probe['remember_config'] is expected
    assert probe['session_cookie_secure'] is expected
    assert probe['remember_cookie_secure'] is expected
    assert (probe['hsts'] is not None) is expected


def test_absent_value_preserves_production_like_secure_default():
    _assert_effective_secure_behavior(_successful_probe(), True)


def test_absent_value_preserves_debug_automatic_default():
    _assert_effective_secure_behavior(
        _successful_probe(flask_debug='1'),
        False,
    )


@pytest.mark.parametrize('value', ['', '   \t'])
def test_blank_value_uses_secure_automatic_default(value):
    _assert_effective_secure_behavior(_successful_probe(value), True)


@pytest.mark.parametrize('value', ['1', 'true', ' TRUE '])
def test_recognized_true_value_enables_secure_behavior(value):
    _assert_effective_secure_behavior(
        _successful_probe(value, flask_debug='1'),
        True,
    )


@pytest.mark.parametrize('value', ['0', 'false', ' FALSE '])
def test_recognized_false_value_disables_secure_behavior(value):
    _assert_effective_secure_behavior(_successful_probe(value), False)


@pytest.mark.parametrize('value', ['tru', 'yes', '2'])
def test_malformed_nonblank_value_fails_startup(value):
    result = _run_probe(value)

    assert result.returncode != 0
    assert (
        'SESSION_COOKIE_SECURE must be unset, blank, or one of: '
        '1, true, 0, false.'
    ) in result.stderr
