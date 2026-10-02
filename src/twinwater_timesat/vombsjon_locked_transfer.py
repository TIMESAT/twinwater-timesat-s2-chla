"""Locked v1.1 transfer; read-only preflight is separate from performance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .phase3_contract import sha256_file, load_timesat_defaults_snapshot
from .reconstruction_metrics import global_peak
from .transfer_freeze import enumerate_holdout_scenarios, fit_training_affine_scale
from .timesat_adapter import _run_timesat_core
from .vombsjon_execution_gates import default_timesat_runtime_probe

FREEZE = Path('config/erken_vomb_transfer_freeze_v1.1.json')
FREEZE_SHA = '477cb4890daa07073cc55c24a66150dd63a9cdf9b9c949756b08c01215dc0983'
SNAPSHOT = Path('config/timesat_double_logistic_defaults_v4.4.1.json')
SPEC = Path('docs/Vombsjon_Locked_Transfer_Execution_v1.0.md')
SPEC_SHA = '87e9dadb7915b9c2a28e671467c82e5495b91bc2582ebbc17665fdaad59cdc61'
AUDIT = Path('results/vombsjon/satellite_input_audit/v1.2')
CLOSURE = Path('results/vombsjon/execution_gate_closure/v1.0')
OUTPUT = Path('results/vombsjon/locked_transfer/v1.0')
OBS = AUDIT / 'vombsjon_same_day_observation_master.csv'
FIELD = AUDIT / 'vombsjon_field_satellite_matchup_master.csv'
CLOSURE_HASHES = {
    'vombsjon_execution_gate_manifest.json': '7a4be4042c8cba4f8381f58a956a45c0a3a85b53d935a678f63c43d59cc699be',
    'vombsjon_execution_gate_status.csv': '7ac6f2740b48a5feace116505f9955519a14633709f408383401d6e83553fcdc',
    'vombsjon_timesat_runtime_validation.json': '9bc95df6e8f0175a2024caeeb33d4fd18246af3332a806a3bfc9bb8c955e9559',
}
PRIMARY = ('linear_interpolation', 'timesat_double_logistic', 'timesat_smoothing_spline')
SENSITIVITY = 'timesat_double_logistic_cv_sensitivity'
METHODS = (*PRIMARY, SENSITIVITY)
PROCESSORS = ('ACOLITE', 'L2A', 'L1C')
KEY = ['processor', 'year', 'scenario_kind', 'block_size_observed_dates']
METRICS = ('bias_native_mci', 'mae_native_mci', 'rmse_native_mci', 'nrmse_training_q95_minus_q05')
TABLES = ('input_audit', 'year_eligibility', 'holdout_scenarios', 'training_scales',
          'method_status', 'daily_predictions', 'withheld_predictions', 'scenario_metrics',
          'peak_metrics', 'date_collapsed_predictions', 'year_summary', 'equal_year_summary',
          'field_consistency')
CODE = (Path('scripts/43_vombsjon_locked_transfer.py'), Path('scripts/44_validate_vombsjon_locked_transfer.py'),
        Path('src/twinwater_timesat/vombsjon_locked_transfer.py'),
        Path('src/twinwater_timesat/transfer_freeze.py'), Path('src/twinwater_timesat/timesat_adapter.py'),
        Path('src/twinwater_timesat/reconstruction_metrics.py'), Path('src/twinwater_timesat/reconstruction_support.py'),
        Path('src/twinwater_timesat/phase3_contract.py'), Path('src/twinwater_timesat/vombsjon_execution_gates.py'))


class TransferError(ValueError):
    """Fail closed on inconsistent provenance, rules or data."""


def require(condition, message):
    if not condition:
        raise TransferError(message)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def strict_bool(series):
    # CSV booleans only; never astype(bool) on strings such as 'False'.
    mapped = series.astype(str).map({'True': True, 'False': False, 'true': True, 'false': False})
    require(mapped.notna().all(), f'Invalid boolean in {series.name}')
    return mapped.astype(bool)


def read_json(path):
    return json.loads(Path(path).read_text())


def load_transfer_v11(root):
    """No alternate path, fallback to v1.0, or science-setting overrides."""
    path = Path(root) / FREEZE
    require(sha256_file(path) == FREEZE_SHA, 'Frozen v1.1 bytes changed')
    config = read_json(path)
    require(config['schema_version'] == 'erken_vomb_transfer_freeze_config_v2', 'Expected v2 schema')
    require(config['freeze_version'] == 'erken_vomb_transfer_freeze_v1.1', 'Expected v1.1 freeze')
    require(config['scope']['vombsjon_performance_execution_authorized'] is False, 'Historical authorization changed')
    require(config['reconstruction_methods']['primary_order'] == list(PRIMARY), 'Primary methods changed')
    return config


def processor_roles(config):
    primary = config['observation_layer']['primary_processing_product']
    return {primary['method']: primary['role'], **{r['method']: r['role'] for r in config['observation_layer']['processing_sensitivities']}}


def verify_evidence(root):
    root = Path(root)
    load_transfer_v11(root)
    require(sha256_file(root / SPEC) == SPEC_SHA, 'Execution specification changed; requires a new version')
    for name, digest in CLOSURE_HASHES.items():
        path = CLOSURE / name
        require(sha256_file(root / path) == digest, f'Closure artifact changed: {path}')
        require(git(root, 'show', f'HEAD:{path}') == (root / path).read_bytes(), f'Closure not committed: {path}')
    closure = read_json(root / CLOSURE / 'vombsjon_execution_gate_manifest.json')
    require(closure['gate_closure_complete'] is True and closure['n_pass'] == 7 and closure['n_fail'] == 0
            and closure['n_blocked'] == 0 and closure['repository_worktree_dirty_at_start'] is False,
            'Committed closure is not clean-start 7/7 PASS')
    baseline = closure['repository_commit_at_start']
    subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', baseline, 'HEAD'], check=True)
    paths = [FREEZE, SNAPSHOT, *sorted(p.relative_to(root) for p in (root / AUDIT).iterdir() if p.is_file()),
             *sorted(p.relative_to(root) for p in (root / 'provenance/vombsjon').rglob('*') if p.is_file())]
    for path in paths:
        require((root / path).read_bytes() == git(root, 'show', f'{baseline}:{path}'), f'Closure-baseline input changed: {path}')
    paths += [CLOSURE / n for n in CLOSURE_HASHES]
    return {str(p): sha256_file(root / p) for p in paths}


def load_observations(root, config):
    table = pd.read_csv(Path(root) / OBS, float_precision='round_trip')
    table['date'] = pd.to_datetime(table['date'], errors='raise')
    require(table['date'].eq(table['date'].dt.normalize()).all(), 'Non-calendar observation date')
    require(not table.duplicated(['method', 'date']).any(), 'Duplicate (method, date) observations')
    require(set(table['method']) == set(PROCESSORS), 'Unexpected or missing processor')
    require(table['year'].eq(table.date.dt.year).all(), 'Year/date mismatch')
    for col in ['methods_pooled', 'reprocessings_counted_as_independent_observations']:
        require(not strict_bool(table[col]).any(), f'Forbidden {col}')
    require(table['support_pixel_count'].eq(config['spatial_and_qc']['window_pixel_count']).all(), 'Not fixed temporal 3x3 support')
    require(table['observation_unit'].eq('whole_calendar_date').all(), 'Wrong observation unit')
    require(table['same_day_reduction'].eq('median_of_eligible_observation_level_medians').all(), 'Same-day rule changed')
    available = strict_bool(table['mci_observation_available'])
    table['value'] = pd.to_numeric(table['MCI_date_median'], errors='raise')
    require(np.isfinite(table.loc[available, 'value']).all(), 'Eligible observation has nonfinite MCI')
    table['processor'] = table['method']
    table['processor_role'] = table.processor.map(processor_roles(config))
    table['eligible'] = available & table.date.dt.dayofyear.ne(366)
    table['input_status'] = np.where(~available, 'audit_unavailable', np.where(table.date.dt.dayofyear.eq(366), 'excluded_day_366', 'eligible'))
    return table


def prepare_scenarios(table, config):
    """Independent processor calendars; never collapse or intersect processors."""
    require(not table.duplicated(['processor', 'date']).any(), 'Duplicate (method, date) observations')
    hold = config['holdout_design']
    frames, years = [], []
    for processor in PROCESSORS:
        observations = table.loc[table.processor.eq(processor)]
        scenarios = enumerate_holdout_scenarios(
            observations[['date', 'value', 'eligible']],
            minimum_full_year_dates=hold['minimum_full_year_eligible_dates'],
            minimum_training_dates=hold['minimum_retained_training_dates'],
            block_sizes=tuple(hold['consecutive']['block_sizes_observed_dates']))
        if not scenarios.empty:
            scenarios.insert(0, 'processor', processor)
            scenarios['scenario_id'] = processor + '_' + scenarios['scenario_id']
            frames.append(scenarios)
        for year, group in observations.groupby('year', sort=True):
            accepted = group.loc[group.eligible].sort_values('date')
            n = len(accepted)
            for design, size in [('isolated', 1), *[('consecutive', b) for b in hold['consecutive']['block_sizes_observed_dates']]]:
                ok = n >= hold['minimum_full_year_eligible_dates'] and n-size >= hold['minimum_retained_training_dates']
                count = max(n-size-1, 0) if ok else 0
                years.append(dict(processor=processor, year=int(year), scenario_kind=design,
                                  block_size_observed_dates=size, n_eligible_dates=n,
                                  n_day366_excluded=int(group.input_status.eq('excluded_day_366').sum()),
                                  eligible=ok, n_scenarios=count,
                                  reason='eligible' if ok else 'insufficient_dates',
                                  support_start=accepted.date.min(), support_end=accepted.date.max()))
    columns = ['processor', 'scenario_id', 'year', 'scenario_kind', 'block_size_observed_dates',
               'heldout_dates_json', 'training_dates_json', 'support_start', 'support_end']
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)), pd.DataFrame(years)


FIELD_META = ['method', 'field_date', 'primary_support', 'primary_support_identical_for_every_date',
              'nominal_point_fallback_used', 'coordinate_correction_applied', 'temporal_rule',
              'temporal_tolerance_days', 'polygon_minimum_valid_fraction', 'mci_matchup_available',
              'acquisition_date', 'reprocessings_counted_as_independent_observations']


def validate_field_metadata(table, config):
    rule = config['spatial_and_qc']['field_validation_support']
    require(not table.duplicated(['method', 'field_date']).any(), 'Duplicate polygon matchup (method, date)')
    require(table.primary_support.eq(rule['primary_support']).all(), 'Field input must use fixed pelagic polygon')
    require(strict_bool(table.primary_support_identical_for_every_date).all(), 'Moving polygon support')
    for col in ['nominal_point_fallback_used', 'coordinate_correction_applied']:
        require(not strict_bool(table[col]).any(), f'Forbidden field flag: {col}')
    require(table.temporal_rule.eq(rule['temporal_rule']).all() and table.temporal_tolerance_days.eq(0).all(), 'Non-exact field matching')
    require(np.allclose(table.polygon_minimum_valid_fraction, rule['polygon_minimum_valid_fraction'], rtol=0, atol=1e-15), 'Field validity fraction changed')
    available = strict_bool(table.mci_matchup_available)
    independent = table.reprocessings_counted_as_independent_observations
    require(independent.loc[available].notna().all(), 'Available field pair lacks deduplication flag')
    require(not strict_bool(independent.dropna()).any(), 'Field reprocessings treated as independent')
    require(pd.to_datetime(table.loc[available, 'acquisition_date']).eq(pd.to_datetime(table.loc[available, 'field_date'])).all(), 'Field matchup date mismatch')
    return available


def preflight(root):
    root = Path(root)
    config = load_transfer_v11(root)
    evidence = verify_evidence(root)
    table = load_observations(root, config)
    scenarios, years = prepare_scenarios(table, config)
    field_meta = pd.read_csv(root / FIELD, usecols=FIELD_META)
    validate_field_metadata(field_meta, config)
    runtime = default_timesat_runtime_probe(root / SNAPSHOT, transfer_config=config)
    require(runtime['all_runtime_checks_passed'] is True and runtime['registered_build_artifact'] is True, f'Runtime gate failed: {runtime}')
    require(len(scenarios) == int(years.n_scenarios.sum()), 'Scenario count arithmetic mismatch')
    checks = [
        'pinned_v11_bytes_v2_schema_and_version', 'execution_specification_sha256',
        'committed_clean_start_7_of_7_closure', 'closure_ancestor_and_immutable_input_bytes',
        'unique_method_date_before_filtering', 'strict_availability_and_finite_mci',
        'fixed_temporal_3x3_and_frozen_same_day_rule', 'independent_processor_calendars_and_roles',
        'day366_exclusions_and_year_eligibility', 'exhaustive_internal_holdout_counts',
        'fixed_polygon_exact_date_field_metadata_only', 'registered_timesat_runtime_defaults_and_smoke',
        'synthetic_affine_equivariance_both_methods', 'no_performance_executed']
    report = dict(schema_version='vombsjon_transfer_preflight_v1', checks={c: 'PASS' for c in checks},
                  repository_commit=git(root, 'rev-parse', 'HEAD').decode().strip(),
                  repository_clean=not bool(git(root, 'status', '--porcelain').strip()),
                  execution_specification_sha256=SPEC_SHA, evidence_sha256=evidence,
                  scenario_counts=years.to_dict('records'), n_scenarios=len(scenarios),
                  performance_executed=False, runtime=runtime)
    return report, config, table, scenarios, years


def fit_scenario(training, config, snapshot, core=_run_timesat_core):
    """Only retained training data enters this function, never heldout or field data."""
    training = training.sort_values('date')
    dates = pd.date_range(training.date.min(), training.date.max(), freq='D')
    dates = dates[dates.dayofyear != 366]
    predictions = pd.DataFrame({'date': dates})
    statuses = []
    values = training.value.to_numpy(float)
    qs = np.quantile(values, config['evaluation']['nrmse_scale']['quantiles'], method='linear')
    scale_row = dict(training_q05=float(qs[0]), training_q95=float(qs[1]), nrmse_scale=float(qs[1]-qs[0]),
                     training_minimum=float(values.min()), training_maximum=float(values.max()),
                     multiplier=np.nan, offset=np.nan, status='unavailable')
    try:
        scale = fit_training_affine_scale(values, scaled_minimum=config['scale_handling']['scaled_training_minimum'],
                                         scaled_maximum=config['scale_handling']['scaled_training_maximum'])
        scale_row.update(multiplier=scale.multiplier, offset=scale.offset, status='ok')
    except ValueError as error:
        for method in METHODS:
            predictions[method] = np.nan
            statuses.append(dict(reconstruction_method=method, status='unavailable', failure_reason=str(error)))
        return predictions, statuses, scale_row
    for method in METHODS:
        try:
            if method == 'linear_interpolation':
                y = np.interp(dates.asi8, pd.DatetimeIndex(training.date).asi8, values)
                status, reason = 'ok', ''
            else:
                parameters = dict(snapshot['effective_runtime_parameters'])
                if method == SENSITIVITY:
                    parameters['p_seapar'] = config['reconstruction_methods'][SENSITIVITY]['p_seapar']
                result = core(year=int(training.date.iloc[0].year), dates=training.date.tolist(),
                              values=scale.transform(values).tolist(),
                              method='timesat_double_logistic' if method == SENSITIVITY else method,
                              smoothing=config['reconstruction_methods']['timesat_smoothing_spline']['p_smooth'] if method == 'timesat_smoothing_spline' else None,
                              parameters=parameters)
                series = pd.Series(result['prediction'], index=pd.to_datetime(result['dates']), dtype=float)
                require(series.index.is_unique, 'Duplicate runtime dates')
                y = scale.inverse(series.reindex(dates).to_numpy())
                status, reason = result['status'], result['failure_reason']
                if not np.isfinite(y).all():
                    status, reason = 'failed', 'missing_or_nonfinite_support_prediction'
            predictions[method] = y
            statuses.append(dict(reconstruction_method=method, status=status, failure_reason=reason))
        except Exception as error:  # retain scenario failure, never substitute or retry settings
            predictions[method] = np.nan
            statuses.append(dict(reconstruction_method=method, status='failed', failure_reason=f'{type(error).__name__}: {error}'))
    return predictions, statuses, scale_row


def evaluate_scenario(observed, predictions, statuses, scale_row):
    joined = observed[['date', 'value']].merge(predictions, on='date', how='left', validate='one_to_one')
    status = {s['reconstruction_method']: s['status'] for s in statuses}
    paired = np.isfinite(joined[list(PRIMARY)]).all(axis=1) & np.isfinite(joined.value)
    if any(status[m] != 'ok' for m in PRIMARY):
        paired[:] = False
    rows, metrics = [], []
    for method in METHODS:
        valid = paired.copy()
        if status[method] != 'ok' or (method == SENSITIVITY and not np.isfinite(joined.loc[paired, method]).all()):
            valid[:] = False
        errors = (joined.loc[valid, method] - joined.loc[valid, 'value']).to_numpy(float)
        rmse = float(np.sqrt(np.mean(errors**2))) if len(errors) else np.nan
        denom = scale_row['nrmse_scale']
        metrics.append(dict(reconstruction_method=method, n_requested_dates=len(joined), n_evaluable_dates=int(valid.sum()),
                            method_failed=status[method] != 'ok', primary_paired_unavailable=not bool(paired.any()),
                            bias_native_mci=float(errors.mean()) if len(errors) else np.nan,
                            mae_native_mci=float(np.abs(errors).mean()) if len(errors) else np.nan,
                            rmse_native_mci=rmse, nrmse_training_q95_minus_q05=rmse/denom if np.isfinite(denom) and denom > 0 else np.nan))
        for i, r in joined.iterrows():
            rows.append(dict(reconstruction_method=method, date=r.date, observed_mci=r.value, prediction=r[method],
                             paired_evaluable=bool(valid.loc[i]), error=float(r[method]-r.value) if valid.loc[i] else np.nan))
    return rows, metrics


def peak_metrics(full_year, heldout, predictions, statuses):
    reference = global_peak(full_year.date, full_year.value)
    reference_ok = reference.peak_time is not None and not reference.boundary_peak
    eligible = reference_ok and reference.peak_time in set(pd.to_datetime(heldout))
    peaks = {m: global_peak(predictions.date, predictions[m]) for m in METHODS}
    status = {r['reconstruction_method']: r['status'] for r in statuses}
    valid = {m: status[m] == 'ok' and peaks[m].peak_time is not None and not peaks[m].boundary_peak for m in METHODS}
    common = all(valid[m] for m in PRIMARY)
    rows = []
    for method in METHODS:
        ok = bool(eligible and common and valid[method])
        signed = (peaks[method].peak_time-reference.peak_time).total_seconds()/86400 if ok else np.nan
        row = dict(reconstruction_method=method, reference_eligible=bool(eligible), peak_available=ok,
                   reference_peak_date=reference.peak_time, reference_peak_status=reference.status,
                   reference_peak_reason=reference.reason, reference_boundary_peak=reference.boundary_peak,
                   reconstructed_peak_date=peaks[method].peak_time, reconstructed_peak_status=peaks[method].status,
                   reconstructed_peak_reason=peaks[method].reason, reconstructed_boundary_peak=peaks[method].boundary_peak,
                   signed_peak_error_days=signed, absolute_peak_error_days=abs(signed),
                   unavailability_reason='' if ok else ('reference_not_identifiable_or_not_held_out' if not eligible else 'primary_or_own_fit_or_peak_unavailable'))
        for tolerance in (5, 10, 15):
            row[f'peak_success_{tolerance}d'] = float(ok and abs(signed) <= tolerance) if eligible else np.nan
        rows.append(row)
    return rows


def summarize_outputs(scenario_metrics, withheld, peaks, config):
    """Year-first long-form estimates with explicit denominator columns."""
    group_cols = KEY + ['reconstruction_method']
    summaries, collapsed = [], []
    for key, group in scenario_metrics.groupby(group_cols, sort=True):
        meta = dict(zip(group_cols, key))
        subset = withheld
        peak = peaks
        for k, v in meta.items():
            subset = subset.loc[subset[k].eq(v)]
            peak = peak.loc[peak[k].eq(v)]
        valid = subset.loc[subset.paired_evaluable]
        bydate = valid.groupby('date', sort=True).agg(prediction=('prediction', 'median'), observed_mci=('observed_mci', 'first'), n_predictions=('prediction', 'size')).reset_index()
        collapsed.extend([{**meta, **r} for r in bydate.to_dict('records')])
        r = np.nan
        if len(bydate) >= 3 and bydate.prediction.nunique() > 1 and bydate.observed_mci.nunique() > 1:
            r = float(bydate.prediction.corr(bydate.observed_mci))
        series = {m: group[m] for m in METRICS}
        series.update({m: peak[m] for m in ['signed_peak_error_days', 'absolute_peak_error_days', 'peak_success_5d', 'peak_success_10d', 'peak_success_15d']})
        series['trajectory_pearson_r'] = pd.Series([r])
        for metric, values in series.items():
            finite = values[np.isfinite(values)]
            summaries.append({**meta, 'metric': metric, 'estimate': float(finite.mean()) if len(finite) else np.nan,
                              'n_scenarios_total': len(group), 'n_scenarios_available': int(len(finite)) if metric != 'trajectory_pearson_r' else int(valid.scenario_id.nunique()),
                              'n_method_failed': int(group.method_failed.sum()),
                              'n_primary_paired_unavailable': int(group.primary_paired_unavailable.sum()),
                              'n_requested_dates': int(group.n_requested_dates.sum()), 'n_evaluable_dates': int(group.n_evaluable_dates.sum()),
                              'n_unique_evaluable_dates': len(bydate), 'n_reference_peak_eligible': int(peak.reference_eligible.sum()),
                              'n_peak_unavailable_reference_eligible': int((peak.reference_eligible & ~peak.peak_available).sum())})
    year_table = pd.DataFrame(summaries)
    equal = []
    strata = ['processor', 'scenario_kind', 'block_size_observed_dates']
    hold = config['holdout_design']
    for stratum, group in year_table.groupby(strata, sort=True):
        years = sorted(group.year.unique())
        indices = np.random.Generator(np.random.PCG64(hold['random_seed_for_year_cluster_bootstrap'])).integers(0, len(years), (hold['year_cluster_bootstrap_replicates'], len(years)))
        for (method, metric), g in group.groupby(['reconstruction_method', 'metric'], sort=True):
            values = g.set_index('year').estimate.reindex(years).to_numpy(float)
            sampled = values[indices]
            counts = np.isfinite(sampled).sum(axis=1)
            draws = np.divide(np.nansum(sampled, axis=1), counts, out=np.full(len(indices), np.nan), where=counts > 0)
            finite = values[np.isfinite(values)]
            limits = np.quantile(draws[np.isfinite(draws)], [0.025, 0.975], method='linear') if len(finite) >= 2 else [np.nan, np.nan]
            equal.append({**dict(zip(strata, stratum)), 'reconstruction_method': method, 'metric': metric,
                          'estimate': float(finite.mean()) if len(finite) else np.nan,
                          'ci_lower': limits[0], 'ci_upper': limits[1], 'n_years_total': len(years), 'n_years_available': len(finite),
                          'n_bootstrap_finite': int(np.isfinite(draws).sum()),
                          'n_scenarios_total': int(g.n_scenarios_total.sum()), 'n_scenarios_available': int(g.n_scenarios_available.sum())})
    return pd.DataFrame(collapsed, columns=group_cols+['date', 'prediction', 'observed_mci', 'n_predictions']), year_table, pd.DataFrame(equal)


def field_consistency(root, config):
    table = pd.read_csv(Path(root) / FIELD, float_precision='round_trip')
    available = validate_field_metadata(table, config)
    table['processor'] = table['method']
    table['processor_role'] = table.processor.map(processor_roles(config))
    table['analysis_role'] = 'complementary_fixed_polygon_exact_date_proxy_consistency_only'
    table['pair_available'] = available & np.isfinite(table.MCI_date_median) & np.isfinite(table.field_chla_fluorometry_ug_L)
    table['used_for_tuning'] = False
    return table


def execute_tables(table, scenarios, years, config, snapshot, core=_run_timesat_core):
    buckets = {name: [] for name in ['training_scales', 'method_status', 'daily_predictions', 'withheld_predictions', 'scenario_metrics', 'peak_metrics']}
    for scenario in scenarios.to_dict('records'):
        meta = {k: scenario[k] for k in [*KEY, 'scenario_id']}
        full = table.loc[table.processor.eq(meta['processor']) & table.year.eq(meta['year']) & table.eligible].sort_values('date')
        train_dates = pd.to_datetime(json.loads(scenario['training_dates_json']))
        test_dates = pd.to_datetime(json.loads(scenario['heldout_dates_json']))
        training = full.loc[full.date.isin(train_dates), ['date', 'value']]
        observed = full.loc[full.date.isin(test_dates), ['date', 'value']]
        predictions, statuses, scale = fit_scenario(training, config, snapshot, core)
        withheld, metrics = evaluate_scenario(observed, predictions, statuses, scale)
        peaks = peak_metrics(full, test_dates, predictions, statuses)
        buckets['training_scales'].append({**meta, **scale})
        for name, records in [('method_status', statuses), ('withheld_predictions', withheld), ('scenario_metrics', metrics), ('peak_metrics', peaks)]:
            buckets[name].extend({**meta, **r} for r in records)
        for method in METHODS:
            buckets['daily_predictions'].extend({**meta, 'reconstruction_method': method, 'date': d, 'prediction': y} for d, y in zip(predictions.date, predictions[method]))
    result = {k: pd.DataFrame(v) for k, v in buckets.items()}
    result['date_collapsed_predictions'], result['year_summary'], result['equal_year_summary'] = summarize_outputs(result['scenario_metrics'], result['withheld_predictions'], result['peak_metrics'], config)
    result.update(input_audit=table, year_eligibility=years, holdout_scenarios=scenarios)
    return result


def annotate_roles(tables, config):
    for table in tables.values():
        if 'processor' in table:
            table['processor_role'] = table.processor.map(processor_roles(config))
        if 'reconstruction_method' in table:
            table['analysis_role'] = table.reconstruction_method.map({m: config['reconstruction_methods'][m]['analysis_role'] for m in METHODS})


def json_write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, default=str, allow_nan=False)+'\n')


def output_path(root):
    root = Path(root).resolve()
    path = root / OUTPUT
    require(path.resolve() == path, 'Symlinked output namespace is forbidden')
    return path


def run_performance(root):
    root = Path(root)
    report, config, table, scenarios, years = preflight(root)
    require(report['repository_clean'], 'Performance requires a clean committed implementation/specification')
    destination = output_path(root)
    require(not destination.exists(), 'Output namespace already exists; never overwrite')
    require(not scenarios.empty, 'No eligible holdout scenarios')
    # Every file used for execution is committed before performance starts.
    for path in [SPEC, *CODE]:
        require(git(root, 'show', f'HEAD:{path}') == (root / path).read_bytes(), f'Uncommitted execution input: {path}')
    input_hashes = {**report['evidence_sha256'], str(SPEC): SPEC_SHA}
    code_hashes = {str(p): sha256_file(root / p) for p in CODE}
    snapshot = load_timesat_defaults_snapshot(root / SNAPSHOT)
    tables = execute_tables(table, scenarios, years, config, snapshot)
    tables['field_consistency'] = field_consistency(root, config)
    annotate_roles(tables, config)
    # Recheck after computation and before any output is created.
    require(all(sha256_file(root / p) == h for p, h in {**input_hashes, **code_hashes}.items()), 'Execution input changed during run')
    destination.mkdir(parents=True, exist_ok=False)
    for name in TABLES:
        tables[name].to_csv(destination / f'vombsjon_transfer_{name}.csv', index=False, lineterminator='\n')
    json_write(destination / 'vombsjon_transfer_runtime_validation.json', report['runtime'])
    manifest = dict(schema_version='vombsjon_locked_transfer_v1', repository_commit_at_start=report['repository_commit'],
                    repository_worktree_dirty_at_start=False, execution_specification_sha256=SPEC_SHA,
                    input_sha256=input_hashes, code_sha256=code_hashes,
                    processing_timestamp_utc=datetime.now(timezone.utc).isoformat(), invocation=sys.argv,
                    historical_freeze_performance_execution_authorized=False,
                    explicit_run_performance_requested=True, performance_executed=True,
                    parameters_tuned=False, field_used_for_tuning=False, units='native_MCI',
                    processor_roles=processor_roles(config), validation_complete=False)
    manifest['output_sha256'] = {p.name: sha256_file(p) for p in destination.iterdir() if p.is_file()}
    manifest_path = destination / 'vombsjon_transfer_manifest.json'
    json_write(manifest_path, manifest)
    checks = validate_outputs(root, require_complete=False)
    pd.DataFrame(checks).to_csv(destination / 'vombsjon_transfer_validation.csv', index=False, lineterminator='\n')
    manifest['output_sha256']['vombsjon_transfer_validation.csv'] = sha256_file(destination / 'vombsjon_transfer_validation.csv')
    manifest['validation_complete'] = True
    json_write(manifest_path, manifest)
    validate_outputs(root)
    return manifest


def assert_table_equal(actual, expected, label):
    """Compare CSV-normalized data, tolerating only numeric serialization roundoff."""
    import io
    expected = pd.read_csv(io.StringIO(expected.to_csv(index=False)))
    try:
        pd.testing.assert_frame_equal(actual.reset_index(drop=True), expected.reset_index(drop=True), check_dtype=False, rtol=1e-10, atol=1e-12)
    except AssertionError as exc:
        raise TransferError(f'{label} differs from independently derived records: {exc}') from exc


def validate_outputs(root, require_complete=True):
    """No TIMESAT execution: derive scenarios, masks and reductions from saved curves."""
    root = Path(root)
    config = load_transfer_v11(root)
    evidence = verify_evidence(root)
    destination = output_path(root)
    manifest = read_json(destination / 'vombsjon_transfer_manifest.json')
    require(manifest['schema_version'] == 'vombsjon_locked_transfer_v1', 'Unexpected performance manifest schema')
    require(manifest['execution_specification_sha256'] == SPEC_SHA, 'Manifest specification mismatch')
    require(manifest['repository_worktree_dirty_at_start'] is False and manifest['performance_executed'] is True, 'Invalid run provenance')
    if require_complete:
        require(manifest['validation_complete'] is True, 'Incomplete performance output')
    expected_files = {f'vombsjon_transfer_{n}.csv' for n in TABLES} | {'vombsjon_transfer_runtime_validation.json'}
    if require_complete:
        expected_files.add('vombsjon_transfer_validation.csv')
    require(set(manifest['output_sha256']) == expected_files, 'Missing or unexpected output coverage')
    require({p.name for p in destination.iterdir()} == expected_files | {'vombsjon_transfer_manifest.json'}, 'Unexpected output files')
    for name, digest in manifest['output_sha256'].items():
        require(sha256_file(destination / name) == digest, f'Output checksum mismatch: {name}')
    require(set(manifest['input_sha256']) == set(evidence) | {str(SPEC)}, 'Incomplete manifest input coverage')
    require(set(manifest['code_sha256']) == {str(p) for p in CODE}, 'Incomplete manifest code coverage')
    require(manifest['historical_freeze_performance_execution_authorized'] is False
            and manifest['explicit_run_performance_requested'] is True
            and manifest['parameters_tuned'] is False and manifest['field_used_for_tuning'] is False, 'Invalid scope assertions')
    runtime = read_json(destination / 'vombsjon_transfer_runtime_validation.json')
    require(runtime.get('all_runtime_checks_passed') is True and runtime.get('registered_build_artifact') is True, 'Saved runtime validation failed')
    for field in ['input_sha256', 'code_sha256']:
        for path, digest in manifest[field].items():
            require(sha256_file(root / path) == digest, f'{field} mismatch: {path}')
            require(hashlib.sha256(git(root, 'show', f"{manifest['repository_commit_at_start']}:{path}")).hexdigest() == digest, f'Run commit identity mismatch: {path}')
    saved = {n: pd.read_csv(destination / f'vombsjon_transfer_{n}.csv', float_precision='round_trip') for n in TABLES}
    inputs = load_observations(root, config)
    scenarios, years = prepare_scenarios(inputs, config)
    expected = {'input_audit': inputs, 'holdout_scenarios': scenarios, 'year_eligibility': years}
    annotate_roles(expected, config)
    for name, table in expected.items():
        assert_table_equal(saved[name], table, name)
    # Every curve/status key must exist once for every scenario and method.
    expected_pairs = {(s, m) for s in scenarios.scenario_id for m in METHODS}
    statuses = saved['method_status']
    require(not statuses.duplicated(['scenario_id', 'reconstruction_method']).any(), 'Duplicate method status')
    require(set(zip(statuses.scenario_id, statuses.reconstruction_method)) == expected_pairs, 'Missing method status')
    for name in ['method_status', 'daily_predictions']:
        data = saved[name]
        joined = data.merge(scenarios[['scenario_id', *KEY]], on='scenario_id', how='left', suffixes=('', '_expected'), validate='many_to_one')
        require(all(joined[k].eq(joined[k+'_expected']).all() for k in KEY), f'{name} scenario metadata mismatch')
        require(data.processor_role.eq(data.processor.map(processor_roles(config))).all(), f'{name} processor role changed')
        require(data.analysis_role.eq(data.reconstruction_method.map({m: config['reconstruction_methods'][m]['analysis_role'] for m in METHODS})).all(), f'{name} analysis role changed')
    require(set(statuses.status).issubset({'ok', 'failed', 'unavailable'}), 'Unknown method status')
    curves = saved['daily_predictions']
    require(not curves.duplicated(['scenario_id', 'reconstruction_method', 'date']).any(), 'Duplicate daily prediction')
    require(set(zip(curves.scenario_id, curves.reconstruction_method)) == expected_pairs, 'Missing/extra daily curve')
    require(set(saved['training_scales'].scenario_id) == set(scenarios.scenario_id) and not saved['training_scales'].scenario_id.duplicated().any(), 'Training scale coverage')
    withheld_rows, metric_rows, peak_rows, scales = [], [], [], []
    for scenario in scenarios.to_dict('records'):
        meta = {k: scenario[k] for k in [*KEY, 'scenario_id']}
        full = inputs.loc[inputs.processor.eq(meta['processor']) & inputs.year.eq(meta['year']) & inputs.eligible]
        train = full.loc[full.date.isin(pd.to_datetime(json.loads(scenario['training_dates_json'])))].sort_values('date')
        observed = full.loc[full.date.isin(pd.to_datetime(json.loads(scenario['heldout_dates_json'])))].sort_values('date')
        q = np.quantile(train.value, [0.05, 0.95], method='linear')
        scale = dict(training_q05=q[0], training_q95=q[1], nrmse_scale=q[1]-q[0], training_minimum=train.value.min(), training_maximum=train.value.max(), multiplier=np.nan, offset=np.nan, status='unavailable')
        try:
            fitted = fit_training_affine_scale(train.value, scaled_minimum=config['scale_handling']['scaled_training_minimum'], scaled_maximum=config['scale_handling']['scaled_training_maximum'])
            scale.update(multiplier=fitted.multiplier, offset=fitted.offset, status='ok')
        except ValueError:
            pass
        scales.append({**meta, **scale})
        sub = curves.loc[curves.scenario_id.eq(meta['scenario_id'])]
        predictions = sub.pivot(index='date', columns='reconstruction_method', values='prediction').reset_index()
        predictions.date = pd.to_datetime(predictions.date)
        dates = pd.date_range(train.date.min(), train.date.max())
        dates = dates[dates.dayofyear != 366]
        require(pd.DatetimeIndex(predictions.date).equals(dates), 'Prediction support differs from training support')
        ss = statuses.loc[statuses.scenario_id.eq(meta['scenario_id'])].to_dict('records')
        for method in METHODS:
            if next(s for s in ss if s['reconstruction_method'] == method)['status'] == 'ok':
                require(np.isfinite(predictions[method]).all(), 'Successful fit contains unavailable values')
        if scale['status'] == 'ok':
            require(np.allclose(predictions['linear_interpolation'], np.interp(dates.asi8, pd.DatetimeIndex(train.date).asi8, train.value), rtol=1e-10, atol=1e-12), 'Linear baseline changed')
        else:
            require(all(s['status'] != 'ok' for s in ss), 'Invalid training range accepted')
        w, m = evaluate_scenario(observed, predictions, ss, scale)
        p = peak_metrics(full, observed.date, predictions, ss)
        for target, rows in [(withheld_rows, w), (metric_rows, m), (peak_rows, p)]:
            target.extend({**meta, **r} for r in rows)
    expected = {'training_scales': pd.DataFrame(scales), 'withheld_predictions': pd.DataFrame(withheld_rows),
                'scenario_metrics': pd.DataFrame(metric_rows), 'peak_metrics': pd.DataFrame(peak_rows)}
    expected['date_collapsed_predictions'], expected['year_summary'], expected['equal_year_summary'] = summarize_outputs(expected['scenario_metrics'], expected['withheld_predictions'], expected['peak_metrics'], config)
    expected['field_consistency'] = field_consistency(root, config)
    annotate_roles(expected, config)
    for name, table in expected.items():
        assert_table_equal(saved[name], table, name)
    return [{'check': c, 'status': 'PASS'} for c in ['committed_inputs_code_and_specification', 'complete_output_hashes', 'exhaustive_scenario_coverage', 'training_only_scales', 'curve_support_and_linear_baseline', 'paired_masks_and_scenario_metrics', 'peak_rules_and_denominators', 'year_equal_year_and_bootstrap_reductions', 'fixed_polygon_field_consistency']]
