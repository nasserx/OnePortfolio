"""Regression coverage for Flask-Limiter storage configuration."""

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

from config import Config
from limits.storage import MemoryStorage
from portfolio_app import create_app, limiter


app = create_app(Config)

print(json.dumps({
    'configured_uri': app.config['RATELIMIT_STORAGE_URI'],
    'uses_memory_storage': isinstance(limiter.storage, MemoryStorage),
    'storage_healthy': limiter.storage.check(),
}))
"""


def _run_probe(value=_UNSET):
    env = os.environ.copy()
    env['SECRET_KEY'] = 'rate-limit-storage-test-secret'
    env['DATABASE_URL'] = 'sqlite:///:memory:'
    env['DEV_AUTO_LOGIN'] = '0'
    env['GOOGLE_OAUTH_ENABLED'] = '0'

    if value is _UNSET:
        env.pop('RATELIMIT_STORAGE_URI', None)
    else:
        env['RATELIMIT_STORAGE_URI'] = value

    return subprocess.run(
        [sys.executable, '-B', '-c', _PROBE_SCRIPT],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _successful_probe(value=_UNSET):
    result = _run_probe(value)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _assert_memory_storage(probe):
    assert probe == {
        'configured_uri': 'memory://',
        'uses_memory_storage': True,
        'storage_healthy': True,
    }


def test_absent_storage_uri_uses_memory_backend():
    _assert_memory_storage(_successful_probe())


@pytest.mark.parametrize('value', ['', '   \t'])
def test_blank_storage_uri_uses_memory_backend(value):
    _assert_memory_storage(_successful_probe(value))


def test_explicit_storage_uri_is_trimmed_and_reaches_flask_limiter():
    result = _run_probe('  unsupported-for-test://configured  ')
    failure_output = result.stdout + result.stderr

    assert result.returncode != 0
    assert 'unsupported-for-test://configured' in failure_output
