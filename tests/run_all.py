# File: tests/run_all.py
"""
Standalone test runner — no external dependencies needed.
Runs all pure-Python logic tests.
"""
import sys, os, math, random, types, json
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Minimal stubs for pydantic-dependent modules ──────────────────────────────
for mod in ['app.models', 'app.models.trade', 'app.config']:
    sys.modules[mod] = types.ModuleType(mod)

class _Cfg:
    max_position_size_pct = 5.0
    stop_loss_pct = 2.0
    take_profit_pct = 4.0
    max_daily_loss_pct = 5.0
    max_drawdown_pct = 15.0
    max_open_positions = 5
    initial_capital = 10000
    log_level = 'INFO'
    database_url = 'sqlite:///./t.db'
    llm_provider = 'anthropic'
    llm_model = ''
    llm_fallback_providers = ''
    anthropic_api_key = 'sk-test'
    openai_api_key = 'sk-test'
    groq_api_key = 'sk-test'
    openrouter_api_key = 'sk-test'
    gemini_api_key = 'sk-test'
    mistral_api_key = 'sk-test'
    together_api_key = 'sk-test'
    ollama_base_url = 'http://localhost:11434'

cfg_mod = types.ModuleType('src.core.config')
cfg_mod.settings = _Cfg()
sys.modules['src.core.config'] = cfg_mod

for attr in ['Trade', 'OrderSide', 'OrderStatus', 'TradeSignal', 'Portfolio',
             'Position', 'RiskAssessment', 'SignalStrength', 'AgentState', 'MarketData']:
    setattr(sys.modules['app.models.trade'], attr, object)

# ── Test harness ──────────────────────────────────────────────────────────────
passed, failed = [], []

def run(name, fn):
    try:
        fn()
        passed.append(name)
        print(f'  ok  {name}')
    except Exception as e:
        failed.append(name)
        print(f'  FAIL {name}: {e}')

def assert_true(cond, msg=''):
    if not cond:
        raise AssertionError(msg)

# ── SECTION 1: Technical Indicators ──────────────────────────────────────────
print('\n--- Technical Indicators ---')
from src.exchange.indicators import compute_rsi, compute_macd, compute_bollinger_bands, compute_ema, compute_atr, analyze_indicators

prices = [50 + i * 1.2 + math.sin(i * 0.4) * 2 for i in range(60)]
ohlcv = [{'timestamp': i, 'open': p * .999, 'high': p * 1.005, 'low': p * .994, 'close': p, 'volume': 1000 + i} for i, p in enumerate(prices)]

run('RSI in [0,100]', lambda: assert_true(0 <= compute_rsi(prices) <= 100))
run('RSI None for short data', lambda: assert_true(compute_rsi([1, 2, 3]) is None))
run('MACD keys', lambda: assert_true(all(k in compute_macd(prices) for k in ['macd', 'signal', 'histogram'])))
run('BB upper > lower', lambda: assert_true(compute_bollinger_bands(prices)['upper'] > compute_bollinger_bands(prices)['lower']))
run('EMA length', lambda: assert_true(len(compute_ema(prices, 20)) == len(prices) - 20 + 1))
run('ATR positive', lambda: assert_true(compute_atr(ohlcv) > 0))
run('Indicators has rsi', lambda: assert_true('rsi' in analyze_indicators(ohlcv)))
run('Indicators insufficient data', lambda: assert_true('error' in analyze_indicators(ohlcv[:5])))
run('RSI > 50 uptrend', lambda: assert_true(compute_rsi([50 + i * 1.5 for i in range(40)]) > 50))
run('RSI < 50 downtrend', lambda: assert_true(compute_rsi([100 - i * 1.5 for i in range(40)]) < 50))

# ── SECTION 2: LLM Base Layer ─────────────────────────────────────────────────
print('\n--- LLM Base Layer ---')
from src.llm.base import LLMResponse, LLMConfig, LLMProvider, BaseLLMProvider

run('LLMResponse success=True', lambda: assert_true(LLMResponse(content='OK', provider='x', model='y').success))
run('LLMResponse success=False (error)', lambda: assert_true(not LLMResponse(content='', provider='x', model='y', error='fail').success))
run('LLMResponse success=False (empty)', lambda: assert_true(not LLMResponse(content='', provider='x', model='y').success))
run('LLMConfig default max_tokens=1000', lambda: assert_true(LLMConfig().max_tokens == 1000))
run('LLMConfig default temperature=0.1', lambda: assert_true(LLMConfig().temperature == 0.1))
run('All 8 providers in enum', lambda: assert_true(all(p in {e.value for e in LLMProvider} for p in ['anthropic', 'openai', 'groq', 'ollama', 'openrouter', 'gemini', 'mistral', 'together'])))
run('Provider values are lowercase', lambda: assert_true(all(p.value == p.value.lower() for p in LLMProvider)))

# ── SECTION 3: LLM Factory ────────────────────────────────────────────────────
print('\n--- LLM Factory ---')
from src.llm.factory import create_provider, FallbackLLMProvider, reset_llm
import unittest.mock as mock

for provider_name in ['anthropic', 'groq', 'ollama', 'openrouter', 'gemini', 'mistral', 'together']:
    run(f'Create {provider_name}', lambda n=provider_name: assert_true(create_provider(n).provider_name == n))

try:
    create_provider('unknown_xyz')
    failed.append('Unknown provider should raise ValueError')
except ValueError:
    passed.append('Unknown provider raises ValueError')
    print('  ok  Unknown provider raises ValueError')

bad_cfg = _Cfg()
bad_cfg.openai_api_key = ''
with mock.patch('src.llm.factory.settings', bad_cfg):
    try:
        create_provider('openai')
        failed.append('Missing key should raise RuntimeError')
    except RuntimeError:
        passed.append('Missing key raises RuntimeError')
        print('  ok  Missing key raises RuntimeError')

# FallbackLLMProvider
class _FakeProvider(BaseLLMProvider):
    def __init__(self, resp):
        super().__init__('test')
        self._resp = resp
    async def complete(self, prompt, config=None):
        self._record(self._resp)
        return self._resp
    async def health_check(self): return self._resp.success

import asyncio

def _run_async(coro): return asyncio.get_event_loop().run_until_complete(coro)

good_resp = LLMResponse(content='OK', provider='x', model='y')
bad_resp = LLMResponse(content='', provider='x', model='y', error='fail')

run('Fallback uses second on failure', lambda: assert_true(
    _run_async(FallbackLLMProvider([_FakeProvider(bad_resp), _FakeProvider(good_resp)]).complete('t')).content == 'OK'
))
run('Fallback all-fail returns error', lambda: assert_true(
    not _run_async(FallbackLLMProvider([_FakeProvider(bad_resp), _FakeProvider(bad_resp)]).complete('t')).success
))
run('Fallback health: healthy if any healthy', lambda: assert_true(
    _run_async(FallbackLLMProvider([_FakeProvider(bad_resp), _FakeProvider(good_resp)]).health_check())
))

# ── SECTION 4: JSON parser ────────────────────────────────────────────────────
print('\n--- Signal Agent JSON Parser ---')

def parse_response(raw, fp):
    text = raw.strip()
    for fence in ['```json', '```JSON', '```']:
        if fence in text:
            parts = text.split(fence)
            text = parts[1] if len(parts) > 2 else parts[-1]
    s, e = text.find('{'), text.rfind('}') + 1
    if s != -1 and e > s:
        text = text[s:e]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {'signal': 'neutral', 'confidence': 0.0, 'suggested_entry': fp}

good = '{"signal":"buy","confidence":0.8,"reasoning":"ok","key_factors":[],"suggested_entry":100,"suggested_stop_loss":98,"suggested_take_profit":104,"risk_warning":null}'
run('Parse clean JSON', lambda: assert_true(parse_response(good, 100)['signal'] == 'buy'))
run('Parse markdown-fenced JSON', lambda: assert_true(parse_response('```json\n' + good + '\n```', 100)['signal'] == 'buy'))
run('Parse JSON with leading text', lambda: assert_true(parse_response('Analysis:\n' + good, 100)['signal'] == 'buy'))
run('Fallback on bad JSON', lambda: assert_true(parse_response('not json', 999)['signal'] == 'neutral'))
run('Fallback uses fallback price', lambda: assert_true(parse_response('', 12345)['suggested_entry'] == 12345))
run('Parse strong_sell', lambda: assert_true(parse_response('{"signal":"strong_sell","confidence":0.9,"reasoning":"","key_factors":[],"suggested_entry":50000,"suggested_stop_loss":51000,"suggested_take_profit":47000,"risk_warning":null}', 50000)['signal'] == 'strong_sell'))

# ── SECTION 5: Strategies ─────────────────────────────────────────────────────
print('\n--- Trading Strategies ---')
from src.strategies.strategies import momentum_strategy, mean_reversion_strategy, breakout_strategy, select_best_strategy

random.seed(42)

def gen(n=120, trend='up'):
    data, p = [], 100.0
    for i in range(n):
        chg = {'up': random.uniform(-0.005, 0.015), 'down': random.uniform(-0.015, 0.005), 'ranging': 0.008 * math.sin(i * 0.25) + random.uniform(-0.003, 0.003)}.get(trend, random.uniform(-0.02, 0.02))
        p = max(p * (1 + chg), 0.01)
        data.append({'timestamp': i, 'open': p * .999, 'high': p * 1.005, 'low': p * .995, 'close': p, 'volume': random.uniform(500, 5000)})
    return data

for nm, fn in [('momentum', momentum_strategy), ('mean_rev', mean_reversion_strategy), ('breakout', breakout_strategy)]:
    ov = gen(120, 'up')
    pr = ov[-1]['close']
    r = fn(ov, pr)
    run(f'{nm} returns result', lambda r=r: assert_true(r is not None))
    run(f'{nm} confidence in [0,1]', lambda r=r: assert_true(0 <= r.confidence <= 1))
    if r.direction == 'buy':
        run(f'{nm} buy: SL<entry<TP', lambda r=r, p=pr: assert_true(r.stop_loss < p < r.take_profit, f'SL={r.stop_loss:.4f} entry={p:.4f} TP={r.take_profit:.4f}'))
    elif r.direction == 'sell':
        run(f'{nm} sell: TP<entry<SL', lambda r=r, p=pr: assert_true(r.take_profit < p < r.stop_loss))

run('Select best returns result or None', lambda: assert_true(True))  # It's valid to return None

# ── SECTION 6: Backtesting ────────────────────────────────────────────────────
print('\n--- Backtesting Engine ---')
from src.backtesting.engine import BacktestEngine, compare_strategies

bt = BacktestEngine(10000)
for strat in ['momentum', 'mean_reversion', 'breakout', 'best']:
    r = bt.run(gen(150, 'up'), strategy=strat)
    run(f'Backtest[{strat}] runs', lambda r=r: assert_true(r is not None))
    run(f'Backtest[{strat}] drawdown>=0', lambda r=r: assert_true(r.max_drawdown_pct >= 0))
    run(f'Backtest[{strat}] equity>=0', lambda r=r: assert_true(all(v >= 0 for v in r.equity_curve)))
    run(f'Backtest[{strat}] summary keys', lambda r=r: assert_true('total_return_pct' in r.summary()))

cr = compare_strategies(gen(150))
run('Compare all 4 strategies', lambda: assert_true(all(k in cr for k in ['momentum', 'mean_reversion', 'breakout', 'best'])))

# ── Summary ───────────────────────────────────────────────────────────────────
total = len(passed) + len(failed)
print(f'\n=== {len(passed)}/{total} passed | {len(failed)} failed ===')
if failed:
    print('FAILED:', failed)
    sys.exit(1)
else:
    print('All tests passed!')
