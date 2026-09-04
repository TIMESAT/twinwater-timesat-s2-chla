"""Phase 6A pilot configuration loading and hard scope guards.

This module owns the DRAFT Erken real-Sentinel-2 L1C/L2A observation pilot
configuration and the guards that keep Phase 6A inside its governed boundary:
Lake Erken only, L1C TOA and official ESA L2A only, and writes confined to the
isolated ``results/phase6a/`` namespace.

The guards are deliberately implemented in code rather than left to
convention, because a silent boundary violation is exactly the failure mode the
Phase 6A governance forbids.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .provenance import PROHIBITED_PATH_MARKERS


DEFAULT_PILOT_CONFIG_RELATIVE_PATH = (
    "config/erken_real_s2_l1c_l2a_observation_pilot_v1.0.yaml"
)
EXPECTED_SCHEMA_VERSION = "erken_real_s2_l1c_l2a_observation_pilot_config_v1"

REQUIRED_CONFIG_SECTIONS: tuple[str, ...] = (
    "scope",
    "inherited_frozen",
    "pairing",
    "radiometry",
    "grid",
    "native_qa",
    "indices",
    "spatial_summary",
    "attrition",
    "outputs",
)


class PilotScopeError(RuntimeError):
    """Raised when an action would leave the governed Phase 6A boundary."""


class PilotConfigError(ValueError):
    """Raised when the pilot configuration is missing or internally invalid."""


@dataclass(frozen=True)
class PilotConfig:
    """A validated Phase 6A configuration plus its own identity for provenance."""

    values: Mapping[str, Any]
    source_relative_path: str
    sha256: str

    def section(self, name: str) -> Mapping[str, Any]:
        """Return a required top-level configuration section."""

        try:
            section = self.values[name]
        except KeyError as error:  # pragma: no cover - guarded by validation
            raise PilotConfigError(
                f"Pilot configuration is missing required section '{name}'."
            ) from error
        if not isinstance(section, Mapping):
            raise PilotConfigError(
                f"Pilot configuration section '{name}' must be a mapping."
            )
        return section

    @property
    def pilot_version(self) -> str:
        return str(self.values["pilot_version"])

    @property
    def status(self) -> str:
        return str(self.values["status"])


def sha256_of_file(path: str | Path) -> str:
    """Return the SHA256 of a file, for configuration and governance identity."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pilot_config(
    path: str | Path, *, repository_root: str | Path | None = None
) -> PilotConfig:
    """Load, validate and fingerprint the DRAFT Phase 6A pilot configuration."""

    config_path = Path(path)
    if not config_path.is_file():
        raise PilotConfigError(f"Pilot configuration not found: {config_path}")

    with config_path.open(encoding="utf-8") as handle:
        values = yaml.safe_load(handle)
    if not isinstance(values, Mapping):
        raise PilotConfigError("Pilot configuration must be a YAML mapping.")

    schema_version = str(values.get("schema_version", ""))
    if schema_version != EXPECTED_SCHEMA_VERSION:
        raise PilotConfigError(
            "Unexpected pilot configuration schema_version "
            f"{schema_version!r}; expected {EXPECTED_SCHEMA_VERSION!r}."
        )

    missing = [name for name in REQUIRED_CONFIG_SECTIONS if name not in values]
    if missing:
        raise PilotConfigError(
            f"Pilot configuration is missing required section(s): {missing}."
        )

    if repository_root is not None:
        try:
            relative = config_path.resolve().relative_to(
                Path(repository_root).resolve()
            )
            relative_path = relative.as_posix()
        except ValueError:
            relative_path = config_path.name
    else:
        relative_path = config_path.name

    return PilotConfig(
        values=values,
        source_relative_path=relative_path,
        sha256=sha256_of_file(config_path),
    )


def default_pilot_config_path(repository_root: str | Path) -> Path:
    """Return the repository-relative default configuration location."""

    return Path(repository_root) / DEFAULT_PILOT_CONFIG_RELATIVE_PATH


def assert_no_prohibited_site(
    value: Any, config: PilotConfig, *, context: str = "value"
) -> None:
    """Refuse any path or identifier referring to a prohibited site.

    Phase 6A is Lake Erken only. Vombsjon data, results, files, directories and
    products must not be accessed, inspected, loaded, searched, summarized or
    modified.
    """

    tokens = [
        str(token).strip().lower()
        for token in config.section("scope").get("prohibited_site_tokens", [])
        if str(token).strip()
    ]
    if not tokens:
        return
    text = str(value).lower()
    detected = sorted({token for token in tokens if token in text})
    if detected:
        raise PilotScopeError(
            f"Phase 6A is restricted to Lake Erken; {context} refers to a "
            f"prohibited site: {detected} in {value!r}."
        )


def assert_permitted_product_level(level: str, config: PilotConfig) -> None:
    """Refuse any product level outside L1C TOA and official ESA L2A."""

    permitted = {
        str(item).upper()
        for item in config.section("scope").get("permitted_product_levels", [])
    }
    if str(level).upper() not in permitted:
        raise PilotScopeError(
            f"Product level {level!r} is outside the Phase 6A scope "
            f"{sorted(permitted)}; atmospheric-correction processors are owned "
            "by the separate s2-inlandwater-ac repository."
        )


def assert_no_prohibited_processor(value: Any, config: PilotConfig) -> None:
    """Refuse identifiers naming an atmospheric-correction processor."""

    prohibited = [
        str(name).strip().upper()
        for name in config.section("scope").get("prohibited_processors", [])
        if str(name).strip()
    ]
    text = str(value).upper()
    detected = sorted({name for name in prohibited if name in text})
    if detected:
        raise PilotScopeError(
            "Phase 6A must not implement or execute atmospheric-correction "
            f"processors; {value!r} names {detected}. These belong to the "
            "s2-inlandwater-ac repository."
        )


def assert_output_path_allowed(
    path: str | Path, config: PilotConfig, *, repository_root: str | Path
) -> Path:
    """Confine every Phase 6A write to the isolated results/phase6a namespace.

    Frozen Phase 3/4/5 outputs, the frozen data and config namespaces, and the
    governing documents must never be overwritten or revised by this pilot.
    """

    outputs = config.section("outputs")
    root = Path(repository_root).resolve()
    target = Path(path)
    resolved = (root / target if not target.is_absolute() else target).resolve()

    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as error:
        raise PilotScopeError(
            f"Phase 6A output path escapes the repository root: {resolved}."
        ) from error

    allowed_root = str(outputs.get("root", "results/phase6a")).strip("/")
    if not (relative == allowed_root or relative.startswith(f"{allowed_root}/")):
        raise PilotScopeError(
            f"Phase 6A may only write under '{allowed_root}/'; refused: "
            f"'{relative}'."
        )

    for prefix in outputs.get("protected_prefixes", []):
        protected = str(prefix).strip("/")
        if relative == protected or relative.startswith(f"{protected}/"):
            raise PilotScopeError(
                f"Refusing to write into frozen/protected namespace "
                f"'{protected}': '{relative}'."
            )

    assert_no_prohibited_site(relative, config, context="output path")
    return resolved


def assert_portable_value(value: Any, *, context: str = "value") -> None:
    """Fail if a repository output would embed a machine-specific absolute path."""

    text = str(value)
    detected = [marker for marker in PROHIBITED_PATH_MARKERS if marker in text]
    if detected:
        raise PilotScopeError(
            f"{context} contains machine-specific absolute path marker(s) "
            f"{detected}; real archive roots must remain runtime inputs."
        )


def assert_portable_rows(
    rows: Iterable[Mapping[str, Any]], *, context: str = "output rows"
) -> None:
    """Fail if any output row would embed a machine-specific absolute path."""

    for index, row in enumerate(rows):
        for column, value in row.items():
            if value is None:
                continue
            assert_portable_value(
                value, context=f"{context} row {index} column '{column}'"
            )
