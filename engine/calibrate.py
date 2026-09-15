"""Sensibilite descriptive au bootstrap ; G4 reste non qualifiee."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from . import backtest, features, metrics, spec as spec_mod
from .costs import DEFAULT
from .data import STEP_SECONDS, data_fingerprint, load
from .journal import Session, clean, digest
from .research import EVENTS, ResearchError, g0_contract, gate_status, provenance, require_is
from .run import sweep
from .validation import synthetic


def max_t(df, sp) -> float:
    f = features.build(df)
    features.assert_causal(df, f)
    best = -np.inf
    for p in sp.grid():
        tr = backtest.run(df, f, sp, p)
        if len(tr) < 30:
            continue
        t = metrics.research(tr, STEP_SECONDS[sp.interval])['t_net']
        if np.isfinite(t):
            best = max(best, t)
    return best if np.isfinite(best) else np.nan


def main() -> int:
    ap = argparse.ArgumentParser(description='Sensibilite de recherche, aucune validation finale')
    ap.add_argument('spec')
    ap.add_argument('--sims', type=int, default=200)
    ap.add_argument('--block', type=int, default=24)
    ap.add_argument('--split', default='IS')
    ap.add_argument('--seed', type=int, default=12345)
    ap.add_argument('--remove-drift', action='store_true', help='centrage marginal, pas suppression de toute previsibilite')
    a = ap.parse_args()
    sp = spec_mod.load(a.spec)
    try:
        with Session(EVENTS, 'bootstrap_sensitivity', sp.hash, a.split, {'provenance': provenance()}) as session:
            require_is(a.split)
            if sp.validate():
                raise ResearchError('; '.join(sp.validate()))
            if a.sims < 1 or a.block < 1:
                raise ResearchError('Nombre de simulations et taille des blocs positifs requis.')
            g0 = g0_contract(sp, a.spec)
            plan = {'sims': a.sims, 'block': a.block, 'seed': a.seed, 'remove_drift': a.remove_drift}
            if g0.get('bootstrap') != plan:
                raise ResearchError('Le plan bootstrap doit etre fixe dans G0 avant la premiere mesure.')
            session.bind_contract(g0, sp.to_dict(), asdict(DEFAULT), simulation_plan=plan)
            df = load(sp.interval, a.split)
            session.bind_data(data_fingerprint(df))
            feats = features.build(df)
            features.assert_causal(df, feats)
            sw = sweep(df, feats, sp, session=session)
            valid = sw.loc[(sw.n_trades >= 30) & np.isfinite(sw.t_net), 't_net']
            real = float(valid.max()) if len(valid) else np.nan
            simulation = 0
            def measured_max(d):
                nonlocal simulation
                simulation += 1
                return session.evaluate({}, f'bootstrap_simulation_{simulation}', lambda: max_t(d, sp), domain='simulation')
            floor = synthetic.noise_floor(df, measured_max, a.block, a.sims, seed=a.seed,
                                          horizon=sp.horizon, remove_drift=a.remove_drift)
            report = {'exp': sp.id, 'spec_hash': sp.hash, 'split': a.split,
                      'data_sha256': data_fingerprint(df), 'provenance': provenance(),
                      'g0': g0, 'simulation_plan': plan, 'real_grid': sw.to_dict('records'),
                      'max_t_real_descriptive': real, 'sensitivity': floor,
                      'verdict': synthetic.verdict(real, floor), 'gates': gate_status()}
            report, output = session.publish(Path(a.spec).parent / 'results', report)
            print(json.dumps(clean(report), indent=2, allow_nan=False))
            return 0 if len(valid) and not floor['n_sims_failed'] else 1
    except (ResearchError, ValueError, RuntimeError) as exc:
        print(f'Sensibilite refusee/echouee : {exc}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
