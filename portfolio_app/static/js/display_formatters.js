/* Shared browser-side display formatting for canvas and live previews.
   Python/Jinja filters remain authoritative for server-rendered values. */
(function (global) {
  'use strict';

  var moneyFormatter = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });

  function finite(value) {
    var number = Number(value);
    if (!Number.isFinite(number) || number === 0) return 0;
    return number;
  }

  function money(value, signed) {
    var number = finite(value);
    return (signed && number > 0 ? '+' : '') + moneyFormatter.format(number);
  }

  function percentage(value, digits, signed) {
    var number = finite(value);
    var precision = Number.isInteger(digits) ? digits : 2;
    return (signed && number > 0 ? '+' : '') + number.toFixed(precision) + '%';
  }

  function compactMoney(value) {
    var number = finite(value);
    var magnitude = Math.abs(number);

    if (magnitude >= 1e9) return (number / 1e9).toFixed(2) + 'B';
    if (magnitude >= 1e6) return (number / 1e6).toFixed(2) + 'M';
    return money(number, false);
  }

  global.OnePortfolioDisplay = Object.freeze({
    money: money,
    percentage: percentage,
    compactMoney: compactMoney
  });
}(window));
