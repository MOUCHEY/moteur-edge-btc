"""Recherche IS tracee. Les sorties sont descriptives, sans promotion finale."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from . import backtest, features, metrics, spec as spec_mod
from .costs import DEFAULT
from .data import STEP_SECONDS, data_fingerprint, load
from .journal import Session, clean, digest
from .research import EVENTS, ResearchError, g0_contract, gate_status, provenance, require_is
from .validation import montecarlo, walkforward


def sweep(df, feats, sp, costs=DEFAULT, session=None) -> pd.DataFrame:
    rows = []
    for p in sp.grid():
        params = dict(p)
        def measure():
            return metrics.research(backtest.run(df, feats, sp, params, costs), STEP_SECONDS[sp.interval])
        m = session.evaluate(params, 'grid', measure) if session else measure()
        rows.append({'params': params, **m})
    return pd.DataFrame(rows)


def famille(sw: pd.DataFrame) -> dict:
    t = pd.to_numeric(sw['t_net'], errors='coerce')
    finite = np.isfinite(t)
    pos = float((t.fillna(-np.inf) > 0).sum() / len(t)) if len(t) else 0.0
    median = float(t.median()) if finite.all() and len(t) else None
    return {'n_configs_declared': len(t), 'n_configs_measurable': int(finite.sum()),
            'mediane_t': median, 'part_configs_positives': pos,
            'all_configs_measurable': bool(finite.all() and len(t)),
            'voisinage_descriptif_75pct': bool(len(t) and finite.all() and pos >= .75),
            'note': 'Grille dependante ; aucune p-valeur de Wilcoxon ni certification de porte.'}


def main() -> int:
    ap = argparse.ArgumentParser(description='Recherche IS avec journal obligatoire')
    ap.add_argument('spec')
    ap.add_argument('--split', default='IS', choices=['IS', 'OOS', 'VAULT'])
    ap.add_argument('--walkforward', action='store_true')
    a = ap.parse_args()
    sp = spec_mod.load(a.spec)
    try:
        with Session(EVENTS, 'discovery', sp.hash, a.split, {'provenance': provenance()}) as session:
            require_is(a.split)
            errors = sp.validate()
            if errors:
                raise ResearchError('; '.join(errors))
            g0 = g0_contract(sp, a.spec)
            session.bind_contract(g0, sp.to_dict(), asdict(DEFAULT))
            if a.walkforward and g0.get('walkforward') is not True:
                raise ResearchError('Walk-forward absent du plan G0 preenregistre.')
            df = load(sp.interval, a.split)
            session.bind_data(data_fingerprint(df))
            feats = features.build(df)
            features.assert_causal(df, feats)
            sw = sweep(df, feats, sp, session=session)
            fam = famille(sw)
            central = dict(g0['central_params'])
            central_row = next(r for r in sw.to_dict('records') if r['params'] == central)
            valid = sw.loc[np.isfinite(sw['t_net'])]
            best = dict(valid.loc[valid['t_net'].idxmax(), 'params']) if len(valid) else None
            descriptive = {'central_t_positive': bool(np.isfinite(central_row['t_net']) and central_row['t_net'] > 0),
                           'family_median_positive': bool(fam['mediane_t'] is not None and fam['mediane_t'] > 0),
                           'enough_trades': central_row['n_trades'] >= g0['min_trades'],
                           'margin_3x_assumed_spread': bool(central_row['net_bps'] >= 3 * DEFAULT.spread_bps)}
            report = {'exp': sp.id, 'spec_hash': sp.hash, 'split': a.split,
                      'data_sha256': data_fingerprint(df), 'provenance': provenance(),
                      'g0': g0, 'costs_assumed': asdict(DEFAULT),
                      'balayage': sw.to_dict('records'), 'test_de_famille': fam,
                      'central_params': central, 'best_exploratory_params': best,
                      'G1_diagnostic': descriptive, 'G1_descriptive_pass': all(descriptive.values()),
                      'gates': gate_status(), 'strategy_validated': False,
                      'deflated_sharpe': {'qualified': False, 'dsr': None,
                                          'reason': 'Historique unique/independant et variance entre essais non etablis.'}}
            if len(valid):
                tr = session.evaluate(central, 'central_trades',
                                      lambda: backtest.run(df, feats, sp, central))
                report['central_trades'] = tr.assign(entry_ts=tr.entry_ts.astype(str), exit_ts=tr.exit_ts.astype(str)).to_dict('records')
                report['deploiement_hypothetique'] = metrics.deployment(tr, STEP_SECONDS[sp.interval])
                report['monte_carlo_sequence'] = montecarlo.run(tr)
                halves = {}
                for name, sl in [('first', slice(0, len(df)//2)), ('second', slice(len(df)//2, None))]:
                    halves[name] = session.evaluate(central, f'half_{name}', lambda sl=sl:
                        metrics.research(backtest.run(df.iloc[sl], feats.iloc[sl], sp, central), STEP_SECONDS[sp.interval]))
                report['halves'] = halves
                report['cost_sensitivity'] = {str(f): session.evaluate(central, f'costs_x{f}', lambda f=f:
                    metrics.research(backtest.run(df, feats, sp, central, DEFAULT.scaled(f)), STEP_SECONDS[sp.interval]))
                    for f in (1.5, 2.0)}
                if a.walkforward:
                    calls = 0
                    def measured_backtest(d, f, spec, p):
                        nonlocal calls
                        calls += 1
                        return session.evaluate(dict(p), f'walkforward_call_{calls}', lambda: backtest.run(d, f, spec, p))
                    report['walkforward_diagnostic'] = walkforward.run(df, feats, sp, measured_backtest,
                        lambda t: metrics.research(t, STEP_SECONDS[sp.interval])['t_net'])
            report, output = session.publish(Path(a.spec).parent / 'results', report)
            print(json.dumps(clean({k: v for k, v in report.items() if k not in ('balayage', 'central_trades')}), indent=2, allow_nan=False))
            print(f'-> {output}', file=sys.stderr)
            return 0 if len(valid) else 1
    except (ResearchError, ValueError, RuntimeError) as exc:
        print(f'Recherche refusee/echouee : {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
