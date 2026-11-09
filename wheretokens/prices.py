"""List-price tables. Every dollar this tool shows is logged tokens times one of these rates.

It is what the same tokens would cost on the public API. It is not what you paid: a
subscription is billed differently. A model with no rate here is shown as "no price",
never as zero dollars. Add or override rates in your config file (see README).
"""

VALUATION = 'estimate at public list price; not money paid'

# Anthropic. USD per million tokens (input, output). Copied 2026-10-04 from
# platform.claude.com/docs/en/about-claude/pricing.
CLAUDE_PRICE_DATE = '2026-10-04'
CLAUDE_PRICE_SOURCE = 'https://platform.claude.com/docs/en/about-claude/pricing'
CLAUDE = {
    'claude-fable-5-1': (10.0, 50.0),
    'claude-mythos-5-1': (10.0, 50.0),
    'claude-fable-5': (10.0, 50.0),
    'claude-mythos-5': (10.0, 50.0),
    'claude-opus-5-5': (4.0, 20.0),
    'claude-opus-5': (5.0, 25.0),
    'claude-opus-4-8': (5.0, 25.0),
    'claude-opus-4-7': (5.0, 25.0),
    'claude-opus-4-6': (5.0, 25.0),
    'claude-opus-4-5': (5.0, 25.0),
    'claude-sonnet-5-5': (2.0, 10.0),
    'claude-sonnet-5': (2.0, 10.0),
    'claude-sonnet-4-6': (3.0, 15.0),
    'claude-sonnet-4-5': (3.0, 15.0),
    'claude-haiku-5-5': (0.10, 0.50),
    'claude-haiku-4-5': (1.0, 5.0),
}
# Priced by prompt length: a request whose prompt (input, cache reads and cache
# writes together) is over the threshold pays the higher rate.
CLAUDE_TIERED = {'claude-haiku-5-5': (100_000, (0.50, 2.50))}
# Fast mode is the same model at premium rates.
CLAUDE_FAST = {'claude-opus-5-5': (8.0, 40.0), 'claude-opus-5': (10.0, 50.0), 'claude-opus-4-8': (10.0, 50.0)}
CACHE_WRITE_5M, CACHE_WRITE_1H, CACHE_READ = 1.25, 2.0, 0.10
CACHE_READ_BY_MODEL = {'claude-opus-5-5': 0.05, 'claude-sonnet-5-5': 0.05,
                       'claude-fable-5-1': 0.025, 'claude-mythos-5-1': 0.025}

# OpenAI, standard tier. USD per million: ordinary input, cache read, cache write, output.
# Copied 2026-10-04 from developers.openai.com/api/docs/pricing. Explicit model ids only.
CODEX_PRICE_DATE = '2026-10-04'
CODEX_PRICE_SOURCE = 'https://developers.openai.com/api/docs/pricing'
CODEX = {
    'gpt-6-astra': (10., 1., 12.5, 50.),
    'gpt-6.1-sol': (2., .1, 2.5, 10.),
    'gpt-6-sol': (2., .2, 2.5, 10.),
    'gpt-6-luna': (.1, .01, .125, .5),
    'gpt-5.6-sol': (4., .4, 5., 20.),
    'gpt-5.3-codex': (1.75, .175, None, 14.),
}
CODEX_LONG_CONTEXT = 272_000
CODEX_NO_LONG_RATE = {'gpt-5.3-codex'}


def apply_overrides(cfg):
    """Config may add rates: {"prices": {"claude": {"model": [in, out]}, "codex": {"model": [in, read, write, out]}}}."""
    p = (cfg or {}).get('prices') or {}
    for k, v in (p.get('claude') or {}).items():
        CLAUDE[k] = (float(v[0]), float(v[1]))
    for k, v in (p.get('codex') or {}).items():
        CODEX[k] = tuple(None if x is None else float(x) for x in v)


def normalise_model(model):
    """claude-haiku-4-5-20251001 and claude-haiku-4-5 are the same price: strip a -YYYYMMDD suffix."""
    if not model:
        return '(unknown)'
    model = str(model)
    head, _, tail = model.rpartition('-')
    if head and len(tail) == 8 and tail.isdigit():
        return head
    return model


def claude_tokens(usage):
    u = usage or {}
    inp = u.get('input_tokens') or 0
    out = u.get('output_tokens') or 0
    read = u.get('cache_read_input_tokens') or 0
    cc = u.get('cache_creation') or {}
    w1h = cc.get('ephemeral_1h_input_tokens') or 0
    w5m = cc.get('ephemeral_5m_input_tokens') or 0
    if not (w1h or w5m):  # older records carry only the aggregate
        w5m = u.get('cache_creation_input_tokens') or 0
    return {'input': inp, 'output': out, 'cache_read': read, 'cache_write_5m': w5m,
            'cache_write_1h': w1h, 'total': inp + out + read + w5m + w1h}


def price_claude(model, usage):
    """(usd or None, tokens) for one API message."""
    tok = claude_tokens(usage)
    model = normalise_model(model)
    if (usage or {}).get('speed') == 'fast' and model in CLAUDE_FAST:
        rate = CLAUDE_FAST[model]
    else:
        rate = CLAUDE.get(model)
    if rate is None:
        return None, tok
    prompt = tok['input'] + tok['cache_read'] + tok['cache_write_5m'] + tok['cache_write_1h']
    if model in CLAUDE_TIERED and prompt > CLAUDE_TIERED[model][0]:
        rate = CLAUDE_TIERED[model][1]
    pin, pout = rate[0] / 1e6, rate[1] / 1e6
    usd = (tok['input'] * pin + tok['output'] * pout
           + tok['cache_read'] * pin * CACHE_READ_BY_MODEL.get(model, CACHE_READ)
           + tok['cache_write_5m'] * pin * CACHE_WRITE_5M + tok['cache_write_1h'] * pin * CACHE_WRITE_1H)
    return usd, tok


def price_codex(model, u):
    """u is one reconciled request: input_tokens includes cached and cache-write tokens; output includes reasoning."""
    rates = CODEX.get(model)
    if rates is None or (u['cache_write_input_tokens'] and rates[2] is None):
        return None
    # The long-context threshold applies to ONE request, never to a session sum.
    long = model not in CODEX_NO_LONG_RATE and u['input_tokens'] > CODEX_LONG_CONTEXT
    ip, cp, wp, op = rates
    ordinary = u['input_tokens'] - u['cached_input_tokens'] - u['cache_write_input_tokens']
    return ((ordinary * ip + u['cached_input_tokens'] * cp + u['cache_write_input_tokens'] * (wp or 0))
            * (2 if long else 1) + u['output_tokens'] * op * (1.5 if long else 1)) / 1e6
