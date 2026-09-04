"""Layout-tolerant Sentinel-2 SAFE discovery for L1C and official ESA L2A.

The Erken archive spans several processing baselines, and SAFE layouts differ
across them: L1C keeps flat IMG_DATA band rasters while L2A separates R10m /
R20m / R60m, and native QA appears as per-band GML vectors on older baselines
and as multi-band JP2 rasters on newer ones. This module therefore discovers
assets by inspecting what a product actually contains and records the result,
rather than assuming one filename convention for all 2019-2025 products.

Nothing here reads pixels or decides usability. Resolution is never inferred
from a filename alone; it is confirmed from the raster's own affine transform
in :mod:`twinwater_timesat.s2_grid`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

RASTER_SUFFIXES: frozenset[str] = frozenset({".jp2", ".tif", ".tiff"})
VECTOR_MASK_SUFFIXES: frozenset[str] = frozenset({".gml"})

L1C_PRODUCT_NAME_RE = re.compile(
    r"(?P<platform>S2[A-Z0-9])_MSIL1C_"
    r"(?P<acquisition>\d{8}T\d{6})_"
    r"(?P<baseline>N\d{4})_R(?P<orbit>\d{3})_"
    r"(?P<tile>T\d{2}[A-Z]{3})_(?P<generation>\d{8}T\d{6})",
    re.IGNORECASE,
)
L2A_PRODUCT_NAME_RE = re.compile(
    r"(?P<platform>S2[A-Z0-9])_MSIL2A_"
    r"(?P<acquisition>\d{8}T\d{6})_"
    r"(?P<baseline>N\d{4})_R(?P<orbit>\d{3})_"
    r"(?P<tile>T\d{2}[A-Z]{3})_(?P<generation>\d{8}T\d{6})",
    re.IGNORECASE,
)

# Band rasters are named ..._B04.jp2 or ..._B04_20m.jp2 depending on level and
# baseline. The optional trailing resolution token is captured for provenance
# only; the authoritative resolution comes from the raster transform.
BAND_ASSET_RE = re.compile(
    r"(?:^|_)(?P<band>B(?:0[1-9]|1[0-2]|8A))(?:_(?P<resolution>\d{2,3})m)?$",
    re.IGNORECASE,
)

# Native QA families actually distributed inside SAFE QI_DATA directories.
QA_ASSET_RE = re.compile(
    r"^MSK_(?P<family>QUALIT|CLASSI|DETFOO|NODATA|SATURA|DEFECT|TECQUA|CLOUDS"
    r"|CLDPRB|SNWPRB)"
    r"(?:_(?P<band>B(?:0[0-9]|1[0-2]|8A)))?"
    r"(?:_(?P<resolution>\d{2,3})m)?$",
    re.IGNORECASE,
)

SCL_ASSET_RE = re.compile(
    r"(?:^|_)SCL(?:_(?P<resolution>\d{2,3})m)?$", re.IGNORECASE
)


class SAFEDiscoveryError(ValueError):
    """Raised when a SAFE product cannot be interpreted without guessing."""


@dataclass(frozen=True)
class BandAsset:
    """One band raster discovered inside a product."""

    band: str
    path: Path
    relative_path: str
    declared_resolution_m: int | None
    resolution_directory: str | None


@dataclass(frozen=True)
class QAAsset:
    """One native QA asset discovered inside a product."""

    family: str
    path: Path
    relative_path: str
    band: str | None
    declared_resolution_m: int | None
    is_raster: bool
    is_vector: bool


@dataclass(frozen=True)
class SAFEProduct:
    """A discovered SAFE product root with its level and asset inventory."""

    product_id: str
    level: str
    root: Path
    band_assets: tuple[BandAsset, ...] = field(default=())
    qa_assets: tuple[QAAsset, ...] = field(default=())
    scl_assets: tuple[QAAsset, ...] = field(default=())

    def bands_for(self, band: str) -> tuple[BandAsset, ...]:
        """Return every discovered asset for one physical band."""

        wanted = canonical_band_name(band)
        return tuple(asset for asset in self.band_assets if asset.band == wanted)

    def qa_family(self, family: str) -> tuple[QAAsset, ...]:
        """Return every discovered asset for one native QA family."""

        wanted = family.upper()
        return tuple(asset for asset in self.qa_assets if asset.family == wanted)


def canonical_band_name(band: str) -> str:
    """Return the canonical zero-padded MSI band name (``B4`` and ``B04`` agree).

    Discovered assets and requested bands must be canonicalized through this one
    function; comparing raw strings lets a ``B4`` request miss a ``B04`` asset.
    """

    text = str(band).strip().upper()
    if text.endswith("A"):
        stem, suffix = text[:-1], "A"
    else:
        stem, suffix = text, ""
    digits = stem[1:] if stem.startswith("B") else stem
    if not digits.isdigit():
        raise SAFEDiscoveryError(f"Unrecognised Sentinel-2 band name: {band!r}")
    return f"B{int(digits):02d}{suffix}"


def product_level(name: str) -> str | None:
    """Return ``L1C`` or ``L2A`` from a SAFE-style product name, else ``None``."""

    upper = name.upper()
    if "_MSIL1C_" in upper:
        return "L1C"
    if "_MSIL2A_" in upper:
        return "L2A"
    return None


def _product_name(path: Path) -> str:
    name = path.name
    return name[:-5] if name.upper().endswith(".SAFE") else name


def _looks_like_product_directory(path: Path, filenames: Sequence[str]) -> bool:
    upper_names = {filename.upper() for filename in filenames}
    if {"MTD_MSIL1C.XML", "MTD_MSIL2A.XML"} & upper_names:
        return True
    name = path.name.upper()
    if name.endswith(".SAFE") and ("_MSIL1C_" in name or "_MSIL2A_" in name):
        return True
    return bool(
        L1C_PRODUCT_NAME_RE.search(name) or L2A_PRODUCT_NAME_RE.search(name)
    )


def discover_products(
    input_root: str | Path, *, level: str | None = None
) -> list[Path]:
    """Discover SAFE-style or compact-name product roots below an archive root.

    ``level`` optionally restricts the result to ``L1C`` or ``L2A``. Traversal
    stops descending once a product root is identified, so granule
    subdirectories are never mistaken for products.
    """

    root = Path(input_root)
    if not root.is_dir():
        raise FileNotFoundError(f"Sentinel-2 input root is not a directory: {root}")

    wanted_level = level.upper() if level else None

    def keep(candidate: Path) -> bool:
        if wanted_level is None:
            return True
        return product_level(candidate.name) == wanted_level

    root_files = [path.name for path in root.iterdir() if path.is_file()]
    if _looks_like_product_directory(root, root_files):
        return [root] if keep(root) else []

    products: set[Path] = set()
    for current, directory_names, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        if current_path != root and _looks_like_product_directory(
            current_path, filenames
        ):
            if keep(current_path):
                products.add(current_path)
            directory_names[:] = []
            continue

        consumed: list[str] = []
        for directory_name in sorted(directory_names):
            candidate = current_path / directory_name
            if _looks_like_product_directory(candidate, []):
                if keep(candidate):
                    products.add(candidate)
                consumed.append(directory_name)
        if consumed:
            directory_names[:] = [
                name for name in directory_names if name not in consumed
            ]

    return sorted(products, key=lambda path: path.relative_to(root).as_posix())


def _resolution_directory(path: Path, product: Path) -> str | None:
    for part in path.relative_to(product).parts:
        if re.fullmatch(r"R\d{2,3}m", part, re.IGNORECASE):
            return part.upper()
    return None


def discover_band_assets(product_path: str | Path) -> tuple[BandAsset, ...]:
    """Discover every band raster inside a product, across SAFE layouts."""

    product = Path(product_path)
    if not product.is_dir():
        return ()

    assets: list[BandAsset] = []
    for path in sorted(product.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.suffix.lower() not in RASTER_SUFFIXES:
            continue
        posix_upper = path.as_posix().upper()
        if "/QI_DATA/" in posix_upper or "/AUX_DATA/" in posix_upper:
            continue
        match = BAND_ASSET_RE.search(path.stem)
        if not match:
            continue
        declared = match.group("resolution")
        assets.append(
            BandAsset(
                band=canonical_band_name(match.group("band")),
                path=path,
                relative_path=path.relative_to(product).as_posix(),
                declared_resolution_m=int(declared) if declared else None,
                resolution_directory=_resolution_directory(path, product),
            )
        )
    return tuple(assets)


def discover_qa_assets(product_path: str | Path) -> tuple[QAAsset, ...]:
    """Discover every native QA asset inside a product, raster or vector."""

    product = Path(product_path)
    if not product.is_dir():
        return ()

    assets: list[QAAsset] = []
    allowed = RASTER_SUFFIXES | VECTOR_MASK_SUFFIXES
    for path in sorted(product.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        match = QA_ASSET_RE.match(path.stem)
        if not match:
            continue
        declared = match.group("resolution")
        band = match.group("band")
        assets.append(
            QAAsset(
                family=match.group("family").upper(),
                path=path,
                relative_path=path.relative_to(product).as_posix(),
                band=canonical_band_name(band) if band and band.upper() != "B00" else None,
                declared_resolution_m=int(declared) if declared else None,
                is_raster=path.suffix.lower() in RASTER_SUFFIXES,
                is_vector=path.suffix.lower() in VECTOR_MASK_SUFFIXES,
            )
        )
    return tuple(assets)


def discover_scl_assets(product_path: str | Path) -> tuple[QAAsset, ...]:
    """Discover Scene Classification Layer rasters inside an L2A product."""

    product = Path(product_path)
    if not product.is_dir():
        return ()

    assets: list[QAAsset] = []
    for path in sorted(product.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.suffix.lower() not in RASTER_SUFFIXES:
            continue
        match = SCL_ASSET_RE.search(path.stem)
        if not match:
            continue
        declared = match.group("resolution")
        assets.append(
            QAAsset(
                family="SCL",
                path=path,
                relative_path=path.relative_to(product).as_posix(),
                band=None,
                declared_resolution_m=int(declared) if declared else None,
                is_raster=True,
                is_vector=False,
            )
        )
    return tuple(assets)


def load_product(product_path: str | Path) -> SAFEProduct:
    """Inventory one SAFE product without reading pixels or judging usability."""

    product = Path(product_path)
    if not product.is_dir():
        raise SAFEDiscoveryError(f"Product root is not a directory: {product}")

    product_id = _product_name(product)
    level = product_level(product_id)
    if level is None:
        for candidate in ("MTD_MSIL1C.xml", "MTD_MSIL2A.xml"):
            if (product / candidate).is_file():
                level = "L1C" if candidate.endswith("L1C.xml") else "L2A"
                break
    if level is None:
        raise SAFEDiscoveryError(
            f"Cannot determine Sentinel-2 processing level for product "
            f"{product_id!r}; Phase 6A refuses to guess."
        )

    return SAFEProduct(
        product_id=product_id,
        level=level,
        root=product,
        band_assets=discover_band_assets(product),
        qa_assets=discover_qa_assets(product),
        scl_assets=discover_scl_assets(product) if level == "L2A" else (),
    )


def select_band_asset(
    product: SAFEProduct,
    band: str,
    *,
    prefer_resolution_m: int | None = None,
) -> BandAsset:
    """Select one unambiguous band raster, preferring a declared resolution.

    Ambiguity that survives preference is an explicit failure: Phase 6A must not
    silently pick one of several equally plausible assets.
    """

    candidates = product.bands_for(band)
    if not candidates:
        raise SAFEDiscoveryError(
            f"Product {product.product_id!r} contains no raster for band "
            f"{band!r}."
        )

    if prefer_resolution_m is not None:
        preferred = [
            asset
            for asset in candidates
            if asset.declared_resolution_m == prefer_resolution_m
            or asset.resolution_directory == f"R{prefer_resolution_m}M"
        ]
        if preferred:
            candidates = tuple(preferred)

    if len(candidates) == 1:
        return candidates[0]

    raise SAFEDiscoveryError(
        f"Product {product.product_id!r} has {len(candidates)} equally "
        f"preferred rasters for band {band!r}: "
        f"{[asset.relative_path for asset in candidates]}."
    )
