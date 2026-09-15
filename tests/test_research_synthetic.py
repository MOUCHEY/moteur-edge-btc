"""Regressions des commandes et du journal, jamais de serie de marche."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml

from engine import attack, calibrate, data, journal, run, spec
from data import collect_forward, seal_vault
from engine.validation import permutation, synthetic


def frame(n=600):
    c = 100 * np.exp(np.cumsum(np.random.default_rng(83).normal(0, .001, n)))
    df = pd.DataFrame({'ts': pd.date_range('2020-01-01', periods=n, freq='h', tz='UTC'),
                       'open': c, 'high': c*1.01, 'low': c*.99, 'close': c,
                       'volume': 10., 'quote_volume': c*10, 'trades': 20, 'taker_buy_base': 5.})
    df.attrs['data_sha256'] = 'ab' * 32
    return df


def setup_spec(root):
    path = root/'spec.yaml'
    path.write_text(yaml.safe_dump({'id':'SYNTHETIC-CONTROL', 'signal': {'entry_long':'ret_1 > {x}'},
                                   'exit': {'mode':'horizon','horizon':1}, 'params': {'x':[1,2,3]}, 'budget_essais':3}))
    sp = spec.load(path)
    g0 = {'spec_hash':sp.hash, 'hypothesis':'Fixture only', 'mechanism':'Generated numbers only',
          'predictions':['No claim about markets'], 'abandonment_rule':'Fixture only',
          'budget_configs':3, 'central_params':{'x':2}, 'min_trades':100}
    (root/'G0.json').write_text(json.dumps(g0))
    return path


def fake_backtest(df, feats, sp, params, *args, **kwargs):
    n = 120
    ts = pd.date_range('2020-01-01', periods=n, freq='2h', tz='UTC')
    x = np.sin(np.arange(n)) + params['x']
    return pd.DataFrame({'net_bps':x, 'gross_bps':x+6, 'cost_bps':6., 'bars_held':1,
                         'entry_ts':ts, 'exit_ts':ts+pd.Timedelta(hours=1)})


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_chain_detects_modified_and_deleted_history(self):
        for i in range(3):
            journal.append(self.root, 'fixture', {'i':i})
        paths = sorted(self.root.glob('*.json'))
        old = paths[1].read_text()
        changed = json.loads(old)
        changed['payload']['i'] = 99
        paths[1].write_text(json.dumps(changed))
        with self.assertRaises(journal.JournalError):
            journal.read_events(self.root)
        paths[1].write_text(old)
        paths[0].unlink()
        with self.assertRaises(journal.JournalError):
            journal.read_events(self.root)

    def test_atomic_result_is_never_overwritten(self):
        p = self.root/'result.json'
        journal.write_once(p, {'first':True})
        with self.assertRaises(FileExistsError):
            journal.write_once(p, {'second':True})
        self.assertEqual(json.loads(p.read_text()), {'first':True})

    def test_journal_rejects_symbolic_files_before_read(self):
        outside = self.root/'outside'
        outside.write_text('not an event')
        (self.root/'00000001-link.json').symlink_to(outside)
        with self.assertRaises(journal.JournalError):
            journal.read_events(self.root)

    def test_contract_freeze_is_shared_across_commands_and_atomic(self):
        contract={'hypothesis':'fixture'}
        effective={'id':'FIXTURE','horizon':1}
        with journal.Session(self.root,'discovery','spec','IS',{}) as session:
            session.bind_contract(contract,effective,{'cost':1})
        with self.assertRaises(journal.JournalError):
            with journal.Session(self.root,'attack','spec','IS',{}) as session:
                session.bind_contract({'hypothesis':'changed'},effective,{'cost':1})
        with journal.Session(self.root,'attack','spec','IS',{}) as session:
            session.bind_contract(contract,effective,{'cost':1})
        self.assertEqual(sum(e['kind']=='contract_bound' for e in journal.read_events(self.root)),2)

    def test_concurrent_writers_have_one_chain(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: journal.append(self.root, 'fixture', {'i':i}), range(12)))
        events = journal.read_events(self.root)
        self.assertEqual(len(events),12)
        self.assertEqual({e['payload']['i'] for e in events}, set(range(12)))

    def test_failed_evaluation_and_run_remain_visible(self):
        def fail():
            raise ValueError('generated failure')
        with self.assertRaises(ValueError):
            with journal.Session(self.root, 'fixture', 'spec', 'IS', {}) as session:
                session.evaluate({'x':1}, 'grid', fail)
        self.assertEqual([e['kind'] for e in journal.read_events(self.root)],
                         ['run_started','evaluation_started','evaluation_failed','run_failed'])
        self.assertEqual(journal.summary(self.root)['new_is_evaluations_completed'],0)

    def test_interrupted_run_remains_unfinished(self):
        session = journal.Session(self.root, 'fixture', 'spec', 'IS', {})
        session.__enter__()
        self.assertEqual(journal.summary(self.root)['attempts_unfinished'],1)

    def test_simulations_not_added_to_market_config_count(self):
        with journal.Session(self.root, 'fixture', 'spec', 'IS', {}) as session:
            session.bind_data('ab'*32)
            for _ in range(2):
                session.evaluate({'x':1}, 'grid', lambda: {'mean':1.})
            session.evaluate({}, 'bootstrap', lambda: 1., domain='simulation')
        s=journal.summary(self.root)
        self.assertEqual(s['new_is_evaluations_completed'],2)
        self.assertEqual(s['new_distinct_is_evaluation_identities'],1)
        self.assertIsNone(s['independent_trials'])


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.path=setup_spec(self.root)
        self.events=self.root/'events'
        self.addCleanup(self.tmp.cleanup)

    def invoke(self, module, args):
        with patch.object(module,'EVENTS',self.events), patch.object(module,'provenance',return_value={'fixture':True}), \
             patch('sys.argv',[module.__name__,str(self.path),*args]), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return module.main()

    def test_all_entrypoints_refuse_reserved_access_before_load(self):
        for module in (run, attack, calibrate):
            for split in ('OOS','VAULT'):
                with self.subTest(module=module.__name__,split=split), patch.object(module,'load') as loader:
                    self.assertEqual(self.invoke(module,['--split',split]),2)
                    loader.assert_not_called()
        events=journal.read_events(self.events)
        self.assertEqual(sum(e['kind']=='run_failed' for e in events),6)

    def test_no_ledger_switch_removed(self):
        with patch.object(run,'load') as loader, self.assertRaises(SystemExit) as ex:
            self.invoke(run,['--no-ledger'])
        self.assertEqual(ex.exception.code,2)
        loader.assert_not_called()

    def test_missing_or_mismatched_g0_refused_before_load(self):
        (self.root/'G0.json').unlink()
        with patch.object(run,'load') as loader:
            self.assertEqual(self.invoke(run,[]),2)
            loader.assert_not_called()
        setup_spec(self.root)
        contract=json.loads((self.root/'G0.json').read_text())
        contract['spec_hash']='wrong'
        (self.root/'G0.json').write_text(json.dumps(contract))
        with patch.object(run,'load') as loader:
            self.assertEqual(self.invoke(run,[]),2)
            loader.assert_not_called()

    def test_out_of_grid_attack_refused_before_load(self):
        with patch.object(attack,'load') as loader:
            self.assertEqual(self.invoke(attack,['--params','{"x":999}']),2)
            loader.assert_not_called()

    def test_load_failure_is_logged(self):
        with patch.object(run,'load',side_effect=RuntimeError('fixture')):
            self.assertEqual(self.invoke(run,[]),2)
        kinds=[e['kind'] for e in journal.read_events(self.events)]
        self.assertEqual(kinds[-1],'run_failed')
        self.assertIn('contract_bound',kinds)

    def test_changed_g0_is_refused_before_second_data_access(self):
        with patch.object(run,'load',side_effect=RuntimeError('fixture')):
            self.assertEqual(self.invoke(run,[]),2)
        p=self.root/'G0.json'
        contract=json.loads(p.read_text())
        contract['central_params']={'x':3}
        p.write_text(json.dumps(contract))
        with patch.object(run,'load') as loader:
            self.assertEqual(self.invoke(run,[]),2)
            loader.assert_not_called()

    def test_unplanned_bootstrap_refused_before_data_access(self):
        with patch.object(calibrate,'load') as loader:
            self.assertEqual(self.invoke(calibrate,['--sims','1']),2)
            loader.assert_not_called()

    def test_success_is_traceable_preserves_runs_and_typed_parameters(self):
        with patch.object(run,'load',return_value=frame()), patch.object(run.backtest,'run',side_effect=fake_backtest), \
             patch.object(run.metrics,'deployment',return_value={}), patch.object(run.montecarlo,'run',return_value={}):
            self.assertEqual(self.invoke(run,[]),0)
            self.assertEqual(self.invoke(run,[]),0)
        reports=[json.loads(p.read_text()) for p in (self.root/'results').glob('*.json')]
        self.assertEqual(len(reports),2)
        for r in reports:
            self.assertEqual(r['best_exploratory_params'],{'x':3})
            self.assertIs(type(r['best_exploratory_params']['x']),int)
            self.assertEqual(r['central_params'],{'x':2})
            self.assertFalse(r['strategy_validated'])
            self.assertFalse(r['deflated_sharpe']['qualified'])
            self.assertEqual(r['journal_snapshot']['stage'],'before_report_publication_and_run_close')
        self.assertEqual(journal.summary(self.events)['attempts_unfinished'],0)
        self.assertGreater(journal.summary(self.events)['new_is_evaluations_completed'],6)

    def test_real_pipeline_on_temporary_synthetic_csv(self):
        proc=self.root/'processed'
        (proc/'IS').mkdir(parents=True)
        frame().to_csv(proc/'IS'/'BTCUSDT-1h.csv.gz',index=False,compression='gzip')
        with patch.object(data,'PROC',proc):
            self.assertEqual(self.invoke(run,[]),0)
        report=json.loads(next((self.root/'results').glob('*.json')).read_text())
        self.assertTrue(report['central_trades'])
        self.assertEqual(len(report['data_sha256']),64)
        self.assertFalse(report['strategy_validated'])
        self.assertEqual(journal.summary(self.events)['attempts_unfinished'],0)

    def test_legacy_collection_and_sealing_are_unavailable(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('forbidden read')), \
             patch.object(Path,'read_text',side_effect=AssertionError('forbidden read')), redirect_stdout(io.StringIO()):
            self.assertEqual(seal_vault.main(),2)
            self.assertEqual(collect_forward.main(),2)
            with self.assertRaises(RuntimeError):
                collect_forward.fetch('1h',0)

    def test_nonmeasurable_grid_cell_stays_in_denominator(self):
        report=run.famille(pd.DataFrame({'t_net':[1.,1.,np.nan,-1.]}))
        self.assertEqual(report['n_configs_declared'],4)
        self.assertEqual(report['part_configs_positives'],.5)
        self.assertFalse(report['voisinage_descriptif_75pct'])


class BootstrapTests(unittest.TestCase):
    def test_permutation_refuses_resizing_unequal_clusters(self):
        with self.assertRaises(ValueError):
            permutation.permute_labels(pd.Series([0,1,1]),pd.Series(['a','b','b']),np.random.default_rng(1))

    def test_no_sample_size_can_qualify_unknown_null(self):
        floor=synthetic.noise_floor(frame(),lambda _:1.,block=24,n_sims=1)
        self.assertFalse(synthetic.verdict(2.,floor)['passe'])
        self.assertFalse(floor['qualified_null'])

    def test_errors_and_seed_retained(self):
        def fail(_):
            raise ValueError('fixture')
        floor=synthetic.noise_floor(frame(),fail,24,n_sims=3,seed=37)
        self.assertEqual(floor['n_sims_failed'],3)
        self.assertEqual(floor['seed'],37)
        self.assertEqual([x['error_type'] for x in floor['outcomes']],['ValueError']*3)
        self.assertIsNone(floor['p95'])
        self.assertFalse(synthetic.verdict(2.,floor)['passe'])

    def test_rebuilt_quote_volume_remains_consistent(self):
        rebuilt=synthetic.block_bootstrap(frame(),24,np.random.default_rng(29))
        np.testing.assert_allclose(rebuilt.quote_volume,rebuilt.volume*rebuilt.close)


if __name__=='__main__':
    unittest.main()
