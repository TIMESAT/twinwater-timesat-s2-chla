"""Synthetic-only performance tests; real Vomb data are used only by preflight."""
from pathlib import Path
import importlib.util
import json
import shutil

import numpy as np
import pandas as pd
import pytest

from twinwater_timesat import vombsjon_locked_transfer as v

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return v.load_transfer_v11(ROOT)


@pytest.fixture
def snapshot():
    return v.read_json(ROOT / v.SNAPSHOT)


def observations(n=10, processor='ACOLITE', year=2020):
    dates = pd.date_range(f'{year}-03-01', periods=n, freq='3D')
    values = np.sin(np.arange(n)*0.6)*0.01 + 0.001*np.arange(n)
    return pd.DataFrame(dict(method=processor, processor=processor, date=dates, year=year,
                             value=values, MCI_date_median=values, eligible=True,
                             mci_observation_available=True, input_status='eligible',
                             methods_pooled=False, reprocessings_counted_as_independent_observations=False,
                             support_pixel_count=9, observation_unit='whole_calendar_date',
                             same_day_reduction='median_of_eligible_observation_level_medians'))


def all_processors():
    return pd.concat([observations(10, p) for p in v.PROCESSORS], ignore_index=True)


def fake_core(**kw):
    dates = pd.date_range(f"{kw['year']}-01-01", periods=366 if kw['year'] % 4 == 0 else 365)
    dates = dates[dates.dayofyear != 366]
    y = np.interp(dates.asi8, pd.DatetimeIndex(kw['dates']).asi8, kw['values'])
    return dict(dates=dates, prediction=y.tolist(), status='ok', failure_reason='')


def field_table():
    return pd.DataFrame([dict(method=p, field_date='2020-03-10', primary_support='fixed_pelagic_convex_hull_polygon',
                             primary_support_identical_for_every_date=True, nominal_point_fallback_used=False,
                             coordinate_correction_applied=False, temporal_rule='exact_same_calendar_date',
                             temporal_tolerance_days=0, polygon_minimum_valid_fraction=2/3,
                             mci_matchup_available=True, acquisition_date='2020-03-10',
                             reprocessings_counted_as_independent_observations=False,
                             MCI_date_median=0.012, field_chla_fluorometry_ug_L=4.0) for p in v.PROCESSORS])


def test_loader_pins_v11_and_refuses_mutation(tmp_path, config):
    p=tmp_path/v.FREEZE
    p.parent.mkdir(parents=True)
    shutil.copyfile(ROOT/v.FREEZE,p)
    assert v.load_transfer_v11(tmp_path)['schema_version'].endswith('_v2')
    changed=dict(config, schema_version='erken_vomb_transfer_freeze_config_v1')
    p.write_text(json.dumps(changed))
    with pytest.raises(v.TransferError, match='Frozen v1.1 bytes'):
        v.load_transfer_v11(tmp_path)


def test_no_historical_loader_or_script_change():
    for p in ['scripts/38_prepare_locked_transfer_scenarios.py','src/twinwater_timesat/transfer_freeze.py']:
        assert (ROOT/p).read_bytes() == v.git(ROOT,'show',f'44dfb1186e344d54848819ec215d0623d083645f:{p}')


def test_processor_scenarios_are_independent(config):
    t=pd.concat([observations(10,'ACOLITE'),observations(8,'L2A'),observations(9,'L1C')],ignore_index=True)
    t.loc[t.processor.eq('L2A'),'date'] += pd.Timedelta(days=1)
    s,y=v.prepare_scenarios(t,config)
    assert s.groupby('processor').size().to_dict()=={'ACOLITE':26,'L1C':18,'L2A':11}
    for r in s.to_dict('records'):
        train=set(json.loads(r['training_dates_json'])); held=set(json.loads(r['heldout_dates_json']))
        assert not train&held
        full=t.loc[t.processor.eq(r['processor'])].date.dt.strftime('%Y-%m-%d')
        assert train|held==set(full)
        assert full.min() in train and full.max() in train


def test_duplicate_processor_date_rejected_before_filtering(config):
    t=observations(); duplicate=t.iloc[[0]].copy(); duplicate['eligible']=False
    with pytest.raises(v.TransferError,match='Duplicate'):
        v.prepare_scenarios(pd.concat([t,duplicate]),config)


def test_load_observations_boolean_and_day366(tmp_path,config):
    t=all_processors()
    t.loc[0,'date']=pd.Timestamp('2020-12-31')
    p=tmp_path/v.OBS;p.parent.mkdir(parents=True)
    t.to_csv(p,index=False)
    out=v.load_observations(tmp_path,config)
    assert out.loc[0,'input_status']=='excluded_day_366'
    assert not out.loc[0,'eligible']
    t['mci_observation_available']=t['mci_observation_available'].astype(object)
    t.loc[1,'mci_observation_available']='perhaps'; t.to_csv(p,index=False)
    with pytest.raises(v.TransferError,match='Invalid boolean'):
        v.load_observations(tmp_path,config)


def test_zero_years_and_unsupported_blocks_retained(config):
    s,y=v.prepare_scenarios(observations(7),config)
    assert s.empty and y.n_scenarios.eq(0).all() and not y.eligible.any()


def test_heldout_mutation_cannot_change_fit_or_scale(config,snapshot):
    t=observations(); train=t.drop(index=[4,5])[['date','value']]
    calls=[]
    def core(**kw):
        calls.append(kw)
        return fake_core(**kw)
    a,sa,scale_a=v.fit_scenario(train,config,snapshot,core)
    t.loc[[4,5],'value']=[1000,-1000]
    b,sb,scale_b=v.fit_scenario(t.drop(index=[4,5])[['date','value']],config,snapshot,core)
    pd.testing.assert_frame_equal(a,b)
    assert scale_a==scale_b and sa==sb
    assert len(calls)==6
    assert all(max(c['values'])<=9000.0000001 and min(c['values'])>=999.9999999 for c in calls)
    assert calls[0]['parameters']['p_seapar']==1
    assert calls[1]['smoothing']==10
    assert calls[2]['parameters']['p_seapar']==0


def test_invalid_scale_does_not_call_core(config,snapshot):
    t=observations();t['value']=1.0
    def forbidden(**kw):
        pytest.fail('No fit for zero range')
    p,status,scale=v.fit_scenario(t,config,snapshot,forbidden)
    assert scale['status']=='unavailable' and p[list(v.METHODS)].isna().all().all()
    assert all(r['status']=='unavailable' for r in status)


def test_paired_failure_and_sensitivity_isolation():
    dates=pd.date_range('2020-01-01',periods=2)
    obs=pd.DataFrame({'date':dates,'value':[1.,2.]})
    pred=pd.DataFrame({'date':dates,**{m:[2.,4.] for m in v.METHODS}})
    statuses=[dict(reconstruction_method=m,status='ok') for m in v.METHODS]
    rows,metrics=v.evaluate_scenario(obs,pred,statuses,{'nrmse_scale':2.})
    assert metrics[0]['bias_native_mci']==1.5
    assert metrics[0]['rmse_native_mci']==np.sqrt(2.5)
    statuses[-1]['status']='failed'
    _,metrics=v.evaluate_scenario(obs,pred,statuses,{'nrmse_scale':0.})
    assert metrics[0]['n_evaluable_dates']==2 and metrics[-1]['n_evaluable_dates']==0
    assert np.isnan(metrics[0]['nrmse_training_q95_minus_q05'])
    statuses[1]['status']='failed'
    _,metrics=v.evaluate_scenario(obs,pred,statuses,{'nrmse_scale':2.})
    assert all(m['n_evaluable_dates']==0 for m in metrics)


def test_common_finite_date_intersection():
    dates=pd.date_range('2020-01-01',periods=2)
    obs=pd.DataFrame({'date':dates,'value':[1.,2.]})
    pred=pd.DataFrame({'date':dates,**{m:[2.,4.] for m in v.METHODS}})
    pred.loc[1,v.PRIMARY[1]]=np.nan
    statuses=[dict(reconstruction_method=m,status='ok') for m in v.METHODS]
    _,metrics=v.evaluate_scenario(obs,pred,statuses,{'nrmse_scale':2.})
    assert all(m['n_evaluable_dates']==1 for m in metrics)


def test_peak_unavailable_failure_counts_as_nonsuccess():
    dates=pd.Series(pd.date_range('2020-01-01',periods=5))
    full=pd.DataFrame({'date':dates,'value':[1.,2.,3.,2.,1.]})
    pred=pd.DataFrame({'date':dates,**{m:full.value for m in v.METHODS}})
    status=[dict(reconstruction_method=m,status='ok') for m in v.METHODS]
    out=v.peak_metrics(full,[dates.iloc[2]],pred,status)
    assert out[0]['peak_success_10d']==1 and out[0]['absolute_peak_error_days']==0
    status[1]['status']='failed'
    out=v.peak_metrics(full,[dates.iloc[2]],pred,status)
    assert all(r['reference_eligible'] and r['peak_success_10d']==0 and np.isnan(r['absolute_peak_error_days']) for r in out)
    full['value']=[3.,2.,1.,2.,3.]
    out=v.peak_metrics(full,[dates.iloc[2]],pred,status)
    assert all(not r['reference_eligible'] for r in out)
    assert all(r['reference_peak_reason']=='ambiguous_equal_global_maxima' for r in out)
    full['value']=[3.,2.,1.,1.,1.]
    out=v.peak_metrics(full,[dates.iloc[0]],pred,status)
    assert all(r['reference_boundary_peak'] and not r['reference_eligible'] for r in out)


@pytest.mark.parametrize('column,value',[('primary_support','fixed_station_3x3'),('nominal_point_fallback_used',True),('acquisition_date','2020-03-11')])
def test_field_rejects_wrong_support_or_date(config,column,value):
    t=field_table();t.loc[0,column]=value
    with pytest.raises(v.TransferError):
        v.validate_field_metadata(t,config)


def test_specification_and_closure_immutability():
    evidence=v.verify_evidence(ROOT)
    assert v.sha256_file(ROOT/v.SPEC)==v.SPEC_SHA
    assert str(v.FREEZE) in evidence


def test_default_cli_cannot_run_performance(monkeypatch,capsys):
    path=ROOT/'scripts/43_vombsjon_locked_transfer.py'
    spec=importlib.util.spec_from_file_location('script43',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'preflight',lambda root: ({'performance_executed':False},))
    monkeypatch.setattr(module,'run_performance',lambda root: pytest.fail('Performance called'))
    assert module.main([])==0
    assert json.loads(capsys.readouterr().out)['performance_executed'] is False


def test_preflight_no_real_reconstruction_or_field_values(monkeypatch,config):
    monkeypatch.setattr(v,'execute_tables',lambda *a,**k: pytest.fail('Performance called'))
    monkeypatch.setattr(v,'field_consistency',lambda *a,**k: pytest.fail('Field values loaded'))
    read=pd.read_csv
    def guarded(path,*args,**kwargs):
        if Path(path)==ROOT/v.FIELD:
            assert kwargs.get('usecols')==v.FIELD_META
        return read(path,*args,**kwargs)
    monkeypatch.setattr(pd,'read_csv',guarded)
    monkeypatch.setattr(v,'default_timesat_runtime_probe',lambda *a,**k: {'all_runtime_checks_passed':True,'registered_build_artifact':True})
    report,*_=v.preflight(ROOT)
    assert not report['performance_executed'] and report['n_scenarios']>0


def test_year_aggregation_is_mean_scenario_rmse_not_pooled(config):
    rows=[];withheld=[];peaks=[]
    for year,errors in [(2020,[1.,9.]),(2021,[3.,3.])]:
        for i,error in enumerate(errors):
            meta=dict(processor='ACOLITE',year=year,scenario_kind='isolated',block_size_observed_dates=1,
                      reconstruction_method=v.PRIMARY[0],scenario_id=f'{year}_{i}')
            rows.append({**meta,**{m:error for m in v.METRICS},'n_requested_dates':1,'n_evaluable_dates':1,'method_failed':False,'primary_paired_unavailable':False})
            withheld.append({**meta,'date':pd.Timestamp(f'{year}-03-0{i+1}'),'prediction':error,'observed_mci':0.,'paired_evaluable':True})
            peaks.append({**meta,'reference_eligible':False,'peak_available':False,**{m:np.nan for m in ['signed_peak_error_days','absolute_peak_error_days','peak_success_5d','peak_success_10d','peak_success_15d']}})
    _,y,e=v.summarize_outputs(pd.DataFrame(rows),pd.DataFrame(withheld),pd.DataFrame(peaks),config)
    rm=y.loc[y.metric.eq('rmse_native_mci')]
    assert rm.estimate.tolist()==[5.,3.]
    equal=e.loc[e.metric.eq('rmse_native_mci')].iloc[0]
    assert equal.estimate==4 and equal.ci_lower==3 and equal.ci_upper==5
    assert equal.n_bootstrap_finite==10000


def test_synthetic_end_to_end_output_validator(tmp_path,monkeypatch,config,snapshot):
    t=all_processors()
    (tmp_path/v.OBS).parent.mkdir(parents=True)
    t.to_csv(tmp_path/v.OBS,index=False)
    field_table().to_csv(tmp_path/v.FIELD,index=False)
    (tmp_path/v.FREEZE).parent.mkdir(parents=True)
    shutil.copyfile(ROOT/v.FREEZE,tmp_path/v.FREEZE)
    shutil.copyfile(ROOT/v.SNAPSHOT,tmp_path/v.SNAPSHOT)
    (tmp_path/v.SPEC).parent.mkdir(parents=True)
    shutil.copyfile(ROOT/v.SPEC,tmp_path/v.SPEC)
    for p in v.CODE:
        (tmp_path/p).parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/p,tmp_path/p)
    table=v.load_observations(tmp_path,config)
    scenarios,years=v.prepare_scenarios(table,config)
    monkeypatch.setattr(v,'verify_evidence',lambda root: {})
    monkeypatch.setattr(v,'git',lambda root,*args: (tmp_path/args[-1].split(':',1)[1]).read_bytes())
    report=dict(repository_clean=True,repository_commit='synthetic_fixture',evidence_sha256={},runtime={'all_runtime_checks_passed':True,'registered_build_artifact':True})
    monkeypatch.setattr(v,'preflight',lambda root: (report,config,table,scenarios,years))
    execute=v.execute_tables
    monkeypatch.setattr(v,'execute_tables',lambda *a,**k: execute(*a,**k,core=fake_core))
    manifest=v.run_performance(tmp_path)
    assert manifest['validation_complete']
    assert len(v.validate_outputs(tmp_path))>=8
    p=tmp_path/v.OUTPUT/'vombsjon_transfer_scenario_metrics.csv'
    bad=pd.read_csv(p);bad.loc[0,'rmse_native_mci']=999;bad.to_csv(p,index=False)
    with pytest.raises(v.TransferError,match='Output checksum'):
        v.validate_outputs(tmp_path)
    # Even refreshing the output digest cannot conceal incorrect numerical reductions.
    mp=tmp_path/v.OUTPUT/'vombsjon_transfer_manifest.json'
    m=v.read_json(mp);m['output_sha256'][p.name]=v.sha256_file(p);v.json_write(mp,m)
    with pytest.raises(v.TransferError,match='scenario_metrics differs'):
        v.validate_outputs(tmp_path)


def test_output_symlink_refused(tmp_path):
    parent=tmp_path/v.OUTPUT.parent;parent.mkdir(parents=True)
    (tmp_path/'elsewhere').mkdir()
    (tmp_path/v.OUTPUT).symlink_to(tmp_path/'elsewhere',target_is_directory=True)
    with pytest.raises(v.TransferError,match='Symlinked'):
        v.output_path(tmp_path)


def test_bootstrap_retains_unavailable_years_in_sampling_frame(config):
    rows=[]; withheld=[]; peaks=[]
    for year, error in [(2020, 2.0), (2021, np.nan)]:
        meta=dict(processor='ACOLITE', year=year, scenario_kind='isolated', block_size_observed_dates=1,
                  reconstruction_method=v.PRIMARY[0], scenario_id=str(year))
        ok=np.isfinite(error)
        rows.append({**meta, **{m:error for m in v.METRICS}, 'n_requested_dates':1,
                     'n_evaluable_dates':int(ok), 'method_failed':not ok, 'primary_paired_unavailable':not ok})
        withheld.append({**meta, 'date':pd.Timestamp(f'{year}-03-01'), 'prediction':error,
                         'observed_mci':0.0, 'paired_evaluable':ok})
        peaks.append({**meta, 'reference_eligible':True, 'peak_available':False,
                      'signed_peak_error_days':np.nan, 'absolute_peak_error_days':np.nan,
                      'peak_success_5d':0.0, 'peak_success_10d':0.0, 'peak_success_15d':0.0})
    _,years,equal=v.summarize_outputs(pd.DataFrame(rows),pd.DataFrame(withheld),pd.DataFrame(peaks),config)
    r=equal.loc[equal.metric.eq('rmse_native_mci')].iloc[0]
    assert r.n_years_total==2 and r.n_years_available==1 and r.estimate==2.0
    assert 0<r.n_bootstrap_finite<10000 and np.isnan(r.ci_lower)
    assert r.n_scenarios_total==2 and r.n_scenarios_available==1
    reliability=equal.loc[equal.metric.eq('peak_success_10d')].iloc[0]
    assert reliability.estimate==0 and reliability.n_scenarios_available==2


def test_performance_refuses_dirty_checkout_before_computation(tmp_path,monkeypatch):
    monkeypatch.setattr(v,'preflight',lambda root: ({'repository_clean':False},None,None,None,None))
    monkeypatch.setattr(v,'execute_tables',lambda *a,**k: pytest.fail('Should stop before fitting'))
    with pytest.raises(v.TransferError,match='clean committed'):
        v.run_performance(tmp_path)
    assert not (tmp_path/v.OUTPUT).exists()


def test_performance_refuses_existing_output_before_computation(tmp_path,monkeypatch):
    (tmp_path/v.OUTPUT).mkdir(parents=True)
    marker=tmp_path/v.OUTPUT/'keep';marker.write_text('unchanged')
    monkeypatch.setattr(v,'preflight',lambda root: ({'repository_clean':True},None,None,None,None))
    with pytest.raises(v.TransferError,match='never overwrite'):
        v.run_performance(tmp_path)
    assert marker.read_text()=='unchanged'
