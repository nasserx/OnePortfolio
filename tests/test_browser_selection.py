"""Browser selection must not silently discard CI's layout coverage."""

import pytest

from tests import test_book_value_layout as layout


@pytest.fixture
def browsers(monkeypatch, tmp_path):
    for name in ('ONEPORTFOLIO_TEST_BROWSER', 'CI', 'PROGRAMFILES(X86)', 'PROGRAMFILES'):
        monkeypatch.delenv(name, raising=False)
    installed = {}
    for name in ('google-chrome', 'chromium'):
        path = tmp_path / name
        path.touch()
        installed[name] = str(path)
    monkeypatch.setattr(layout.shutil, 'which', lambda name: installed.get(name))
    return installed


def test_prefers_packaged_chrome_over_chromium(browsers):
    assert layout._find_chromium_browser() == browsers['google-chrome']


def test_explicit_browser_overrides_discovery(browsers, monkeypatch, tmp_path):
    custom = tmp_path / 'custom-browser'
    custom.touch()
    browsers[str(custom)] = str(custom)
    monkeypatch.setenv('ONEPORTFOLIO_TEST_BROWSER', str(custom))
    assert layout._find_chromium_browser() == str(custom)


def test_invalid_explicit_browser_fails_instead_of_falling_back(browsers, monkeypatch):
    monkeypatch.setenv('ONEPORTFOLIO_TEST_BROWSER', 'missing-browser')
    with pytest.raises(pytest.fail.Exception, match='ONEPORTFOLIO_TEST_BROWSER'):
        layout._find_chromium_browser()


def test_ci_without_browser_fails_instead_of_skipping(browsers, monkeypatch):
    browsers.clear()
    monkeypatch.setenv('CI', 'true')
    with pytest.raises(pytest.fail.Exception, match='CI'):
        try:
            layout._find_chromium_browser()
        except pytest.skip.Exception:
            pytest.fail('Browser coverage was silently skipped')


def test_local_without_browser_can_skip(browsers):
    browsers.clear()
    with pytest.raises(pytest.skip.Exception, match='Chromium'):
        layout._find_chromium_browser()
