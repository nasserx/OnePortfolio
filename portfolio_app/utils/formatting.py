"""Formatting utilities for decimal and money values."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

COMPACT_DISPLAY_THRESHOLD = Decimal('1000000')
COMPACT_PERCENT_THRESHOLD = COMPACT_DISPLAY_THRESHOLD
_COMPACT_UNITS = (
    (Decimal('1000000000000'), 'T'),
    (Decimal('1000000000'), 'B'),
    (Decimal('1000000'), 'M'),
)


def _to_decimal(value):
    if value is None:
        return None

    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _safe_decimals(decimals, default=2):
    try:
        decimals_int = int(decimals)
    except (ValueError, TypeError):
        decimals_int = default
    return max(0, min(decimals_int, 12))


def _format_compact_decimal(value, decimals=2):
    d = _to_decimal(value)
    if d is None:
        return str(value)

    decimals_int = _safe_decimals(decimals)
    sign = '-' if d < 0 else ''
    abs_value = abs(d)

    for unit, suffix in _COMPACT_UNITS:
        if abs_value >= unit:
            scaled = abs_value / unit
            quant = Decimal('1').scaleb(-decimals_int)
            try:
                scaled = scaled.quantize(quant, rounding=ROUND_HALF_UP)
            except (InvalidOperation, ValueError):
                pass
            return f"{sign}{format(scaled, f'.{decimals_int}f')}{suffix}"

    return fmt_decimal(d)


def fmt_decimal(value):
    """Format a number like user input: no forced decimals + thousands separators.

    - Avoid scientific notation
    - Trim trailing zeros
    - Add commas to the integer part
    """
    if value is None:
        return ''

    # Keep Decimals intact; convert others via str() to avoid float artifacts.
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)

    # Fixed-point string (no exponent).
    s = format(d, 'f')
    sign = ''
    if s.startswith('-'):
        sign = '-'
        s = s[1:]

    if '.' in s:
        int_part, frac_part = s.split('.', 1)
        frac_part = frac_part.rstrip('0')
    else:
        int_part, frac_part = s, ''

    # Add thousands separators.
    if int_part:
        int_part = f"{int(int_part):,}"
    else:
        int_part = '0'

    if frac_part:
        return f"{sign}{int_part}.{frac_part}"
    return f"{sign}{int_part}"


def fmt_money(value, decimals=2):
    """Format a number as money: thousands separators + fixed decimals.

    - Avoid scientific notation
    - Round using ROUND_HALF_UP (finance-friendly)
    - Add commas to the integer part
    """
    if value is None:
        return ''

    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return str(value)

    try:
        decimals_int = int(decimals)
    except (ValueError, TypeError):
        decimals_int = 2

    # Guard rails to avoid pathological formats.
    decimals_int = max(0, min(decimals_int, 12))

    quant = Decimal('1').scaleb(-decimals_int)  # 10**(-decimals)
    try:
        d = d.quantize(quant, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        # Fallback: best-effort string format.
        return format(d, 'f')

    return format(d, f",.{decimals_int}f")


def fmt_display_decimal(value, decimals=2):
    """Display-only compact decimal formatting for large UI numbers."""
    d = _to_decimal(value)
    if d is None:
        return '' if value is None else str(value)

    if abs(d) >= COMPACT_DISPLAY_THRESHOLD:
        return _format_compact_decimal(d, decimals)
    return fmt_decimal(d)


def fmt_display_money(value, decimals=2):
    """Display-only compact money formatting for values that can overflow."""
    d = _to_decimal(value)
    if d is None:
        return '' if value is None else str(value)

    if abs(d) >= COMPACT_DISPLAY_THRESHOLD:
        return _format_compact_decimal(d, decimals)
    return fmt_money(d, decimals)


def fmt_display_percent(value, decimals=2, signed=False):
    """Display-only percentage formatter with compact output for huge returns."""
    d = _to_decimal(value)
    if d is None:
        return '—' if value is None else str(value)

    prefix = '+' if signed and d > 0 else ''
    if abs(d) >= COMPACT_PERCENT_THRESHOLD:
        return f"{prefix}{_format_compact_decimal(d, decimals)}%"

    decimals_int = _safe_decimals(decimals)
    quant = Decimal('1').scaleb(-decimals_int)
    try:
        d = d.quantize(quant, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return f"{prefix}{format(d, 'f')}%"
    return f"{prefix}{format(d, f',.{decimals_int}f')}%"
