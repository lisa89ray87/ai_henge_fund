from types import SimpleNamespace

from ai_henge_fund.market_data.market_regime import classify_market_regime


def _candles(values):
    return tuple({"close": value} for value in values)


def test_market_regime_risk_off():
    regime = classify_market_regime(
        _candles([100, 99.8, 99.6, 99.4, 99.2, 99.0]),
        _candles([100, 99.7, 99.4, 99.1, 98.8, 98.5]),
    )
    assert regime.label == "RISK_OFF"


def test_market_regime_risk_on():
    regime = classify_market_regime(
        _candles([100, 100.3, 100.6, 100.9, 101.2, 101.5]),
        _candles([100, 100.4, 100.8, 101.2, 101.6, 102.0]),
    )
    assert regime.label == "RISK_ON"


def test_market_regime_supports_native_moomoo_rows():
    regime = classify_market_regime(
        tuple(SimpleNamespace(close=value) for value in [100, 100.3, 100.6, 100.9, 101.2, 101.5]),
        tuple(SimpleNamespace(close=value) for value in [100, 100.4, 100.8, 101.2, 101.6, 102.0]),
    )
    assert regime.label == "RISK_ON"
    assert regime.spy_return_pct is not None
    assert regime.qqq_return_pct is not None


def test_market_regime_unknown_without_data():
    regime = classify_market_regime([], [])
    assert regime.label == "UNKNOWN"
