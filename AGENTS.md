# Repository working agreement

This file is the common entry point for ChatGPT, Codex, and human contributors.
It governs the whole repository. It does not replace any scientific protocol.

## Required reading order

Before planning scientific work, changing analysis documentation, interpreting
results, or editing the manuscript, read these files in order and read the
relevant files in full:

1. `docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md`
   — the single active scientific master and the only active project plan.
2. `docs/STATUS.md` — the current implementation ledger; it records progress
   against the master but cannot add or change scientific scope.
3. `docs/Reconstruction_Analysis_Contract_v1.0.1.md` — the frozen primary
   Erken reconstruction contract.
4. `docs/decisions.md` — accepted project decisions and later governance
   clarifications.
5. `docs/DATA_INVENTORY.md` — repository data, external inputs, evidence
   products, and availability boundaries.
6. `docs/experiment_design.md` — a concise orientation to the study design;
   it is not a competing plan.
7. `manuscript/README.md`, `manuscript/source_map.md`, and
   `manuscript/manuscript.md` — the current Erken-only manuscript package and
   its evidence map.

For phase-specific work, also read the applicable versioned protocol and its
machine-readable configuration before touching code, results, or claims. In
particular, consult the frozen event, double-logistic sensitivity,
observation-selection, Sentinel-2–CHLF matchup, and processing-baseline
protocols under `docs/`.

## Planning authority and document precedence

- `docs/Incomplete_S2_Chla_Reconstruction_RSE_Project_Master_v4.3.1.md` is
  the sole active scientific plan. Do not create another roadmap, master, or
  reviewer-response plan that competes with it.
- A frozen protocol controls the exact analysis within its stated scope. It is
  an execution contract, not a replacement for the project master.
- `docs/STATUS.md` is the sole current progress ledger. README files,
  historical task briefs, configuration phase labels, and old stop-boundary
  text are not evidence that a completed phase is still pending.
- `docs/decisions.md` records accepted decisions. `docs/experiment_design.md`
  and `README.md` are navigation and explanation layers only.
- If two documents appear inconsistent, stop before changing scientific work.
  Record the conflict in `docs/STATUS.md` under “To verify” and resolve it by
  an explicit decision or a versioned protocol/master update.

## Frozen-analysis change control

Do not overwrite, rename, or edit in place any frozen master, protocol,
machine-readable contract/configuration, committed analysis result, audit,
manifest, or file referenced by checksum.

After performance has been inspected, a scientific-rule change requires all
of the following:

1. an explicit scientific reason and classification;
2. a new versioned protocol or contract with a change log;
3. preservation of the original protocol, configuration, results, and
   manifests;
4. an update to `docs/decisions.md` and `docs/STATUS.md`; and
5. clear labelling of the affected work as confirmatory, sensitivity, or
   exploratory.

Do not rerun analysis, inspect Vombsjön performance, or start the transfer
stage unless the task explicitly authorizes it and the prerequisite freeze is
present. Documentation maintenance alone never authorizes a scientific run.

## Scientific-review triage

Compare every review suggestion with the active master before adding it to
project documentation. Assign exactly one status:

- **Original-plan pending** — already required by the active master but not
  yet completed.
- **Necessary correction** — required to repair an evidenced scientific,
  provenance, reproducibility, or internal-consistency problem. It still
  needs explicit acceptance and versioned change control when frozen work is
  affected.
- **Optional enhancement** — potentially useful but not required by the
  active master.

An unaccepted suggestion remains a proposal. Never rewrite it as an approved
task, a frozen decision, or completed work. Record accepted changes in
`docs/decisions.md`; keep optional ideas in the optional section of
`docs/STATUS.md` until accepted.

## Data and status discipline

- Keep field reference, observed satellite proxy, and reconstructed daily
  estimate as distinct data layers.
- Treat repository-external files as external. State whether their existence,
  content, checksum, licence, and current accessibility were actually
  verified; do not infer any of them.
- Update `docs/STATUS.md` when a phase changes state and update
  `docs/DATA_INVENTORY.md` when a canonical input or output changes.
- A task is not complete until relative Markdown links resolve, status claims
  point to committed evidence, and frozen/checksummed files remain untouched.
