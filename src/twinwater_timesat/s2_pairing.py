"""Deterministic L1C / official L2A product pairing on acquisition metadata.

Phase 6A starts from the already-frozen L2A observation-mask provenance and
never re-selects products using reflectance, NDCI, MCI, native QA
attractiveness, CHLF or downstream performance. L1C is paired to the frozen
representative L2A product on the underlying acquisition identity - platform,
sensing datetime, MGRS tile, and relative orbit where both sides declare it -
rather than on loose filename substring matching.

Pairing that is not exact and unique is a recorded failure, never a silent
substitution. Every frozen representative/candidate date survives into the
audit, including failures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .s2_safe import (
    L1C_PRODUCT_NAME_RE,
    L2A_PRODUCT_NAME_RE,
    SAFEDiscoveryError,
    product_level,
)


PAIRING_EXACT_UNIQUE = "exact_unique"
PAIRING_AMBIGUOUS = "ambiguous_multiple_candidates"
PAIRING_UNMATCHED = "unmatched_no_candidate"
PAIRING_METADATA_INCOMPLETE = "metadata_incomplete"
PAIRING_ROOT_NOT_PROVIDED = "l1c_root_not_provided"
# A date whose frozen SCL gate produced no representative L2A product has
# nothing to pair against. That is distinct from an L1C pairing failure and
# must not be reported as incomplete acquisition metadata.
PAIRING_NO_L2A_REPRESENTATIVE = "no_l2a_representative_for_date"


class PairingError(ValueError):
    """Raised when pairing inputs are structurally unusable."""


@dataclass(frozen=True)
class AcquisitionIdentity:
    """The metadata identity used to pair one acquisition across levels."""

    product_id: str
    level: str
    platform: str | None
    sensing_datetime_utc: str | None
    tile_id: str | None
    relative_orbit: int | None
    processing_baseline: str | None
    generation_time_utc: str | None

    @property
    def complete(self) -> bool:
        """True when the required key fields are all present."""

        return bool(self.platform and self.sensing_datetime_utc and self.tile_id)


@dataclass(frozen=True)
class PairingResult:
    """The outcome of pairing one L2A representative product with L1C."""

    status: str
    l1c: AcquisitionIdentity | None
    candidate_product_ids: tuple[str, ...]
    detail: str | None = None


def normalise_datetime(value: str | None) -> str | None:
    """Return a UTC ``YYYY-MM-DDTHH:MM:SSZ`` string, or ``None`` if unparseable."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{8}T\d{6}", text):
        parsed = datetime.strptime(text, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds_between(first: str, second: str) -> float:
    left = datetime.strptime(first, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    right = datetime.strptime(second, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return abs((left - right).total_seconds())


def identity_from_product_name(name: str) -> AcquisitionIdentity | None:
    """Parse an acquisition identity from a compact SAFE product name."""

    level = product_level(name)
    if level is None:
        return None
    pattern = L1C_PRODUCT_NAME_RE if level == "L1C" else L2A_PRODUCT_NAME_RE
    match = pattern.search(name)
    if not match:
        return None
    stem = name[:-5] if name.upper().endswith(".SAFE") else name
    return AcquisitionIdentity(
        product_id=stem,
        level=level,
        platform=match.group("platform").upper(),
        sensing_datetime_utc=normalise_datetime(match.group("acquisition")),
        tile_id=match.group("tile").upper(),
        relative_orbit=int(match.group("orbit")),
        processing_baseline=match.group("baseline").upper(),
        generation_time_utc=normalise_datetime(match.group("generation")),
    )


def build_identity(
    *,
    product_id: str,
    level: str,
    name_fallback: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AcquisitionIdentity:
    """Build an acquisition identity from XML metadata, then the product name.

    Metadata values take precedence because Phase 6A must not rely on filename
    substrings alone; the compact name fills only fields the XML did not supply.
    """

    from_name = identity_from_product_name(name_fallback or product_id)
    metadata = metadata or {}

    platform = metadata.get("spacecraft_name")
    if platform:
        upper = str(platform).upper()
        sentinel = re.search(r"SENTINEL[-_ ]?2[-_ ]?([A-Z0-9])", upper)
        compact = re.search(r"S2[A-Z0-9]", upper)
        platform = (
            f"S2{sentinel.group(1)}"
            if sentinel
            else compact.group(0)
            if compact
            else None
        )
    platform = platform or (from_name.platform if from_name else None)

    sensing = normalise_datetime(metadata.get("sensing_datetime_raw")) or (
        from_name.sensing_datetime_utc if from_name else None
    )

    tile = metadata.get("tile_id")
    if tile:
        match = re.search(r"T\d{2}[A-Z]{3}", str(tile).upper())
        tile = match.group(0) if match else None
    tile = tile or (from_name.tile_id if from_name else None)

    orbit = metadata.get("relative_orbit")
    orbit = int(orbit) if isinstance(orbit, int) else (
        from_name.relative_orbit if from_name else None
    )

    baseline = metadata.get("processing_baseline")
    if baseline:
        text = str(baseline).strip().upper()
        decimal = re.fullmatch(r"(\d{2})\.(\d{2})", text)
        baseline = f"N{decimal.group(1)}{decimal.group(2)}" if decimal else text
    baseline = baseline or (from_name.processing_baseline if from_name else None)

    generation = normalise_datetime(metadata.get("generation_time")) or (
        from_name.generation_time_utc if from_name else None
    )

    return AcquisitionIdentity(
        product_id=product_id,
        level=level.upper(),
        platform=platform,
        sensing_datetime_utc=sensing,
        tile_id=tile,
        relative_orbit=orbit,
        processing_baseline=baseline,
        generation_time_utc=generation,
    )


def _keys_match(
    l2a: AcquisitionIdentity,
    l1c: AcquisitionIdentity,
    *,
    tolerance_seconds: float,
    compare_orbit: bool,
) -> bool:
    if l2a.platform != l1c.platform or l2a.tile_id != l1c.tile_id:
        return False
    if not (l2a.sensing_datetime_utc and l1c.sensing_datetime_utc):
        return False
    if (
        _seconds_between(l2a.sensing_datetime_utc, l1c.sensing_datetime_utc)
        > tolerance_seconds
    ):
        return False
    if (
        compare_orbit
        and l2a.relative_orbit is not None
        and l1c.relative_orbit is not None
        and l2a.relative_orbit != l1c.relative_orbit
    ):
        return False
    return True


def pair_l1c_to_l2a(
    l2a: AcquisitionIdentity,
    l1c_candidates: Sequence[AcquisitionIdentity],
    *,
    tolerance_seconds: float = 1.0,
    compare_orbit: bool = True,
    l1c_root_provided: bool = True,
) -> PairingResult:
    """Pair one representative L2A product with exactly one L1C acquisition."""

    if not l1c_root_provided:
        return PairingResult(
            status=PAIRING_ROOT_NOT_PROVIDED,
            l1c=None,
            candidate_product_ids=(),
            detail="No L1C archive root was supplied for this run.",
        )

    if not l2a.complete:
        missing = [
            name
            for name, value in (
                ("platform", l2a.platform),
                ("sensing_datetime_utc", l2a.sensing_datetime_utc),
                ("tile_id", l2a.tile_id),
            )
            if not value
        ]
        return PairingResult(
            status=PAIRING_METADATA_INCOMPLETE,
            l1c=None,
            candidate_product_ids=(),
            detail=f"L2A acquisition metadata incomplete: missing {missing}.",
        )

    usable = [candidate for candidate in l1c_candidates if candidate.complete]
    incomplete = [
        candidate for candidate in l1c_candidates if not candidate.complete
    ]

    matches = [
        candidate
        for candidate in usable
        if _keys_match(
            l2a,
            candidate,
            tolerance_seconds=tolerance_seconds,
            compare_orbit=compare_orbit,
        )
    ]
    matches.sort(key=lambda candidate: candidate.product_id)

    if len(matches) == 1:
        return PairingResult(
            status=PAIRING_EXACT_UNIQUE,
            l1c=matches[0],
            candidate_product_ids=(matches[0].product_id,),
        )

    if len(matches) > 1:
        return PairingResult(
            status=PAIRING_AMBIGUOUS,
            l1c=None,
            candidate_product_ids=tuple(
                candidate.product_id for candidate in matches
            ),
            detail=(
                f"{len(matches)} L1C products share the acquisition identity "
                "(platform, sensing datetime, tile, orbit); Phase 6A does not "
                "select one silently."
            ),
        )

    detail = "No L1C product matches the L2A acquisition identity."
    if incomplete:
        detail += (
            f" {len(incomplete)} candidate(s) were skipped for incomplete "
            "acquisition metadata."
        )
    return PairingResult(
        status=PAIRING_UNMATCHED,
        l1c=None,
        candidate_product_ids=(),
        detail=detail,
    )


def pairing_audit_row(
    *,
    date: str,
    year: int | None,
    l2a_representative_status: str,
    scl_gate_pass: bool | None,
    l2a: AcquisitionIdentity | None,
    result: PairingResult,
) -> dict[str, Any]:
    """Build one auditable pairing row, preserving failures explicitly."""

    l1c = result.l1c
    return {
        "date": date,
        "year": year,
        "l2a_representative_status": l2a_representative_status,
        "scl_gate_pass": scl_gate_pass,
        "l2a_product_id": l2a.product_id if l2a else None,
        "l2a_platform": l2a.platform if l2a else None,
        "l2a_sensing_datetime": l2a.sensing_datetime_utc if l2a else None,
        "l2a_tile": l2a.tile_id if l2a else None,
        "l2a_relative_orbit": l2a.relative_orbit if l2a else None,
        "l2a_processing_baseline": l2a.processing_baseline if l2a else None,
        "l2a_generation_time": l2a.generation_time_utc if l2a else None,
        "l1c_pairing_status": result.status,
        "l1c_product_id": l1c.product_id if l1c else None,
        "l1c_platform": l1c.platform if l1c else None,
        "l1c_sensing_datetime": l1c.sensing_datetime_utc if l1c else None,
        "l1c_tile": l1c.tile_id if l1c else None,
        "l1c_relative_orbit": l1c.relative_orbit if l1c else None,
        "l1c_processing_baseline": l1c.processing_baseline if l1c else None,
        "l1c_generation_time": l1c.generation_time_utc if l1c else None,
        "l1c_candidate_count": len(result.candidate_product_ids),
        "l1c_candidate_product_ids": ";".join(result.candidate_product_ids)
        or None,
        "pairing_detail": result.detail,
    }
