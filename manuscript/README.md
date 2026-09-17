# Manuscript package

This directory contains the repository-derived manuscript for the Lake Erken
Sentinel-2 temporal-reconstruction study.

- `manuscript.md` is the version-controlled scientific source.
- `manuscript.docx` is the editable submission-oriented document generated
  from the Markdown source.
- `references.bib` contains the cited literature and data record.
- `source_map.md` maps headline manuscript results to committed result files.
- `manuscript_manifest.json` records artifact hashes and final verification
  outcomes.

The scientific draft is complete. Author names, affiliations, contribution
statements, funding disclosures and journal-specific formatting are not
encoded in the repository and therefore are not asserted here.

Rebuild the Word document from the repository root with:

```bash
python scripts/31_build_manuscript_docx.py
```

Audit the headline values against the committed result products with:

```bash
python scripts/32_validate_manuscript.py
```

The manuscript uses existing committed figures. The builder does not rerun a
reconstruction, recalculate CHLF results, change a frozen protocol or access
Vombsjön.
