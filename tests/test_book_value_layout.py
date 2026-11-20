"""Real layout regression; skips where no local Chromium browser is installed."""

from decimal import Decimal
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from flask import render_template_string
import pytest


@pytest.fixture(scope='session')
def chromium_browser():
    candidates = [shutil.which(name) for name in ('chromium', 'google-chrome', 'msedge')]
    for root in ('PROGRAMFILES(X86)', 'PROGRAMFILES'):
        if os.environ.get(root):
            candidates.append(str(Path(os.environ[root]) / 'Microsoft/Edge/Application/msedge.exe'))
    browser = next((path for path in candidates if path and Path(path).is_file()), None)
    if not browser:
        pytest.skip('A local Chromium browser is required for layout measurements')
    return browser


def _render_card(app):
    # Render the production row and macros, including the info button. No
    # server, external resources, email or production data is used.
    template, _, _ = app.jinja_env.loader.get_source(app.jinja_env, 'index.html')
    row = re.search(
        r'<div class="hero-figure__facts">.*?</div>',
        template, re.S,
    )
    assert row, 'Overview supporting-metrics row is missing from index.html'
    with app.app_context():
        return render_template_string(
            "{% from 'macros/ui.html' import fact, money %}"
            '<section class="surface-card hero-figure">' + row.group(0) + '</section>',
            totals={
                'net_contributions': Decimal('1200'),
                'cash_balance': Decimal('300239.95'),
                'dividend_income': Decimal('300120'),
            },
        )


@pytest.mark.parametrize('width', [360, 512, 513, 560, 900])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_book_value_metric_alignment(app, chromium_browser, tmp_path, width, theme):
    css_dir = Path(app.static_folder) / 'css'
    css = '\n'.join((css_dir / name).read_text(encoding='utf-8') for name in (
        'tokens.css', 'base.css', 'components.css', 'app.css',
    ))
    card = _render_card(app)
    script = '''
        function measure() {
            const metrics = [...document.querySelectorAll('.fact')].map(fact => {
                const label = fact.querySelector('.fact__label');
                const range = document.createRange();
                range.selectNodeContents(label.firstChild);
                const text = range.getBoundingClientRect();
                const valueElement = fact.querySelector('.fact__value');
                const value = valueElement.getBoundingClientRect();
                const rect = fact.getBoundingClientRect();
                const help = label.querySelector('.info-dot');
                const helpRect = help ? help.getBoundingClientRect() : null;
                const valueRange = document.createRange();
                valueRange.selectNodeContents(valueElement);
                const contentRight = Math.max(text.right, valueRange.getBoundingClientRect().right,
                    helpRect ? helpRect.right : 0);
                return {textY: text.y, valueY: value.y, top: rect.top,
                    bottom: rect.bottom, left: rect.left, right: rect.right,
                    contentRight,
                    helpWidth: helpRect ? helpRect.width : null,
                    helpHeight: helpRect ? helpRect.height : null};
            });
            const dividers = [...document.querySelectorAll('.hero-figure__divider')].map(line => {
                const rect = line.getBoundingClientRect();
                return {x: rect.x + rect.width / 2, top: rect.top, bottom: rect.bottom,
                    width: rect.width, display: getComputedStyle(line).display,
                    hidden: line.getAttribute('aria-hidden')};
            });
            return {metrics, dividers};
        }
        const ordinary = measure();
        document.querySelector('.fact__label').firstChild.textContent =
            'Net Contributions with a longer financial label';
        const wrapped = measure();
        parent.document.body.insertAdjacentHTML('beforeend', '<pre id="result">' +
            JSON.stringify({ordinary, wrapped, viewport: innerWidth}) + '</pre>');
    '''
    page = tmp_path / 'card.html'
    document = (
        f'<!doctype html><html data-theme="{theme}"><meta charset="utf-8">'
        f'<style>{css}</style><body>{card}<script>{script}</script></body></html>'
    )
    # A frame avoids desktop Chromium's minimum window width, so the mobile
    # case really exercises the 32rem breakpoint.
    page.write_text(
        f'<!doctype html><body><iframe style="border:0;width:{width}px;height:700px" '
        f'srcdoc="{escape(document, quote=True)}"></iframe></body>',
        encoding='utf-8',
    )
    result = subprocess.run([
        chromium_browser, '--headless', '--disable-gpu', '--no-first-run',
        '--no-default-browser-check', '--disable-background-networking',
        f'--user-data-dir={tmp_path / "profile"}', '--window-size=1100,900',
        '--dump-dom', page.as_uri(),
    ], capture_output=True, text=True, encoding='utf-8', timeout=45)
    assert result.returncode == 0, result.stderr
    match = re.search(r'<pre id="result">(.*?)</pre>', result.stdout)
    assert match, 'Browser did not return layout measurements: ' + result.stderr
    data = json.loads(match.group(1))
    assert data['viewport'] == width
    for scenario in ('ordinary', 'wrapped'):
        rows = data[scenario]['metrics']
        lines = data[scenario]['dividers']
        assert len(rows) == 3
        assert len(lines) == 2
        assert all(line['hidden'] == 'true' for line in lines)
        if data['viewport'] <= 512:
            assert all(b['top'] >= a['bottom'] for a, b in zip(rows, rows[1:]))
            assert all(line['display'] == 'none' for line in lines)
        else:
            assert max(row['valueY'] for row in rows) - min(row['valueY'] for row in rows) < 1
            assert max(row['bottom'] for row in rows) - min(row['bottom'] for row in rows) < 1
            assert all(line['display'] != 'none' and line['width'] == 1 for line in lines)
            for previous, current, line in zip(rows, rows[1:], lines):
                assert abs(line['x'] - (previous['right'] + current['left']) / 2) < 1
                assert abs(line['top'] - current['top']) < 1
                assert abs(line['bottom'] - current['bottom']) < 1
            if scenario == 'ordinary' and width == 900:
                assert max(row['textY'] for row in rows) - min(row['textY'] for row in rows) < 1
                for previous, current, line in zip(rows, rows[1:], lines):
                    midpoint = (previous['contentRight'] + current['left']) / 2
                    assert abs(line['x'] - midpoint) < 1
        assert all(0 <= row['left'] < row['right'] <= data['viewport'] for row in rows)
        assert rows[0]['helpWidth'] == rows[0]['helpHeight'] == 24
