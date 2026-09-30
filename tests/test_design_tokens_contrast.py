"""OKLCH-aware contrast guardrails for the canonical preset roles."""

from pathlib import Path

import pytest

from tests._colour import TEXT_MIN, contrast, mix_oklab, resolve, theme_tokens, to_rgb


TOKENS = Path('portfolio_app/static/css/tokens.css')


@pytest.fixture(scope='module')
def css():
    assert TOKENS.exists()
    return TOKENS.read_text(encoding='utf-8')


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize(
    ('foreground', 'background'),
    [
        ('foreground', 'background'),
        ('card-foreground', 'card'),
        ('popover-foreground', 'popover'),
        ('primary-foreground', 'primary'),
        ('secondary-foreground', 'secondary'),
        ('accent-foreground', 'accent'),
        ('destructive-foreground', 'destructive'),
    ],
)
def test_canonical_text_pairs_meet_wcag_aa(css, theme, foreground, background):
    declared = theme_tokens(css, theme)
    ratio = contrast(resolve(foreground, declared), resolve(background, declared))
    assert ratio >= TEXT_MIN, (
        f'{theme}: --{foreground} on --{background} is {ratio:.2f}:1'
    )


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize(
    'role',
    ['financial-positive', 'financial-negative', 'financial-income', 'financial-flat'],
)
@pytest.mark.parametrize('surface', ['background', 'card', 'popover'])
def test_financial_text_roles_meet_wcag_aa(css, theme, role, surface):
    declared = theme_tokens(css, theme)
    ratio = contrast(resolve(role, declared), resolve(surface, declared))
    assert ratio >= TEXT_MIN, (
        f'{theme}: --{role} on --{surface} is {ratio:.2f}:1'
    )


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_muted_text_remains_readable(css, theme):
    declared = theme_tokens(css, theme)
    for surface in ('background', 'card', 'popover'):
        ratio = contrast(
            resolve('muted-foreground', declared), resolve(surface, declared)
        )
        assert ratio >= TEXT_MIN, (
            f'{theme}: --muted-foreground on --{surface} is {ratio:.2f}:1'
        )


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_global_selection_pair_meets_wcag_aa(css, theme):
    declared = theme_tokens(css, theme)
    ratio = contrast(
        resolve('selection-foreground', declared),
        resolve('selection-background', declared),
    )
    assert ratio >= TEXT_MIN, f'{theme}: selection pair is {ratio:.2f}:1'
    assert declared['selection-background'] == 'var(--primary)'
    assert declared['selection-foreground'] == 'var(--primary-foreground)'
    assert declared['caret-color'] == 'var(--foreground)'


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('role', ['financial-positive', 'financial-negative'])
def test_transaction_direction_text_is_readable_on_soft_selected_surface(
    css, theme, role,
):
    declared = theme_tokens(css, theme)
    foreground = to_rgb(resolve(role, declared))
    soft_surface = mix_oklab(
        resolve(role, declared),
        resolve('popover', declared),
        0.06 if role == 'financial-positive' else 0.12,
    )
    ratio = contrast(foreground, soft_surface)
    assert ratio >= TEXT_MIN, (
        f'{theme}: --{role} on its soft selected surface is {ratio:.2f}:1'
    )

    if role == 'financial-positive':
        assert soft_surface[1] > soft_surface[0], (
            f'{theme}: positive soft surface drifted out of the green family'
        )
    else:
        assert soft_surface[0] > soft_surface[1], (
            f'{theme}: negative soft surface drifted out of the red family'
        )


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_transaction_direction_tokens_use_deterministic_oklab_derivation(css, theme):
    declared = theme_tokens(css, theme)
    assert declared['financial-positive-soft'] == (
        'color-mix(in oklab, var(--financial-positive) 6%, var(--popover))'
    )
    assert declared['financial-positive-line'] == (
        'color-mix(in oklab, var(--financial-positive) 32%, var(--popover))'
    )
    assert declared['financial-negative-soft'] == (
        'color-mix(in oklab, var(--financial-negative) 12%, var(--popover))'
    )
    assert declared['financial-negative-line'] == (
        'color-mix(in oklab, var(--financial-negative) 32%, var(--popover))'
    )
