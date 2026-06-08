"""
GenMake / Cfg_DBFiles CSV Filter
=================================
Parses MTC-output Cfg_DBFiles_GenMake.csv files and exposes a filter that
restricts comparisons to only those files that are taken for compilation.

CSV format (semicolon-separated, no header):
    FileType;RelativeFilePath;ModuleName
    e.g.
    PreBuildPostBuildConfig;rb\\as\\core\\hwp\\hsw\\ucbase\\functional\\rbsys\\tools\\PrePostBuild\\RBSYS_PrePostBuild_Config.mk;ModuleA

Matching strategy
-----------------
The CSV stores workspace-relative paths (e.g. ``rb/as/core/.../foo.c``).
The comparison engine produces paths relative to the *selected* folder root,
which may not be the workspace root (e.g. a user who selected ``rb/`` as the
comparison folder would see ``as/core/.../foo.c``).

To handle this mismatch robustly the filter builds a *suffix index*:
for each CSV path every trailing sub-path of depth ≥ MIN_SUFFIX_DEPTH is
stored.  A comparison rel_path matches if its normalised form appears in
that index.

Example:
    CSV path  : rb/as/core/hwp/rbsys/RBSYS_Config.mk   (5 components)
    Index keys: rb/as/core/hwp/rbsys/rbsys_config.mk
                as/core/hwp/rbsys/rbsys_config.mk
                core/hwp/rbsys/rbsys_config.mk
                hwp/rbsys/rbsys_config.mk
                (rbsys_config.mk alone is NOT stored — too short, causes
                 false positives with common filenames)

    rel_path = "as/core/hwp/rbsys/RBSYS_Config.mk"  → normalised →
               "as/core/hwp/rbsys/rbsys_config.mk"  → found in index → MATCH
    rel_path = "other/path/RBSYS_Config.mk"          → normalised →
               "other/path/rbsys_config.mk"          → NOT in index → NO MATCH
"""

import csv
import os
import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Minimum number of path components a suffix must have to be indexed.
# Prevents single-filename keys like "config.h" that cause false positives.
MIN_SUFFIX_DEPTH = 2


class GenMakeFilter:
    """
    Holds the set of files listed in a Cfg_DBFiles_GenMake CSV and provides
    a membership test used to restrict file comparisons.

    Usage::

        f = GenMakeFilter.from_csv("Cfg_DBFiles_GenMake.csv")
        f.filter_file_types({"PreBuild", "PostBuild"})   # optional restriction
        if f.matches("rb/as/core/.../RBSYS_PrePostBuild_Config.mk"):
            ...
    """

    def __init__(self):
        # {normalised_full_path: file_type}  – canonical CSV entries
        self._entries: Dict[str, str] = {}
        # suffix index: {normalised_suffix: file_type}  – for depth-aware matching
        # Only suffixes with >= MIN_SUFFIX_DEPTH components are stored.
        self._suffix_index: Dict[str, str] = {}
        self._active_file_types: Optional[Set[str]] = None  # None = all types
        self.csv_path: str = ""
        self.all_file_types: List[str] = []  # sorted list of every type found

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_csv(cls, csv_path: str) -> "GenMakeFilter":
        """Parse a Cfg_DBFiles_GenMake CSV file and return a ready filter."""
        obj = cls()
        obj.csv_path = csv_path
        obj._parse(csv_path)
        return obj

    def _parse(self, csv_path: str) -> None:
        file_types_seen: Set[str] = set()
        rows_loaded = 0

        with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as fh:
            reader = csv.reader(fh, delimiter=";")
            for row in reader:
                if not row or row[0].startswith("#"):
                    continue
                if len(row) < 2:
                    continue

                file_type = row[0].strip()
                raw_path  = row[1].strip()
                if not raw_path:
                    continue

                norm = self._normalise(raw_path)
                self._entries[norm] = file_type
                file_types_seen.add(file_type)
                rows_loaded += 1

                # Build suffix index: store every trailing sub-path whose
                # depth (number of path components) >= MIN_SUFFIX_DEPTH.
                # The full path itself is always stored regardless of depth.
                parts = norm.split("/")
                n = len(parts)
                for i in range(n):
                    depth = n - i          # components remaining
                    suffix = "/".join(parts[i:])
                    # Always store if this is the FULL path or depth >= threshold.
                    # For single-component entries (just a filename) we still store
                    # them — the CSV author explicitly listed just the filename.
                    if depth >= MIN_SUFFIX_DEPTH or n == 1:
                        if suffix not in self._suffix_index:
                            self._suffix_index[suffix] = file_type

        self.all_file_types = sorted(file_types_seen, key=str.lower)
        logger.info(
            f"GenMakeFilter: loaded {rows_loaded} entries, "
            f"{len(file_types_seen)} file types, "
            f"{len(self._suffix_index)} suffix-index keys from {csv_path}"
        )

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def filter_file_types(self, types: Optional[Set[str]]) -> None:
        """
        Restrict matching to entries whose FileType is in *types*.
        Pass None to allow all file types.
        """
        if types:
            self._active_file_types = {t.strip() for t in types}
        else:
            self._active_file_types = None

    # ------------------------------------------------------------------
    # Matching
    # ------------------------------------------------------------------

    def matches(self, rel_path: str) -> bool:
        """
        Return True if *rel_path* exists in the CSV (satisfying any active
        file-type filter).

        Matching is done via the suffix index:
        - If the normalised rel_path appears as a suffix key of any CSV entry
          the file is considered a match.
        - This correctly handles workspace-root differences: a CSV path
          ``rb/as/core/foo.c`` will match a rel_path ``as/core/foo.c`` (when
          the user selected the ``rb/`` sub-folder as the comparison root).
        - Filename-only matches (single component) are only possible if the
          CSV itself listed a single-component path.
        """
        norm = self._normalise(rel_path)
        found_type = self._suffix_index.get(norm)
        if found_type is None:
            return False
        return self._type_allowed(found_type)

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(path: str) -> str:
        """Convert any path to lowercase forward-slash form.

        Handles both single-backslash (``rb\\foo``) and double-backslash
        (``rb\\\\foo``) Windows paths by replacing every backslash with ``/``
        and then collapsing any resulting consecutive slashes.
        """
        result = path.replace("\\", "/").lower()
        # Collapse double-slashes that arise from '\\' → '//'
        while "//" in result:
            result = result.replace("//", "/")
        return result.strip("/")

    def _type_allowed(self, file_type: str) -> bool:
        if self._active_file_types is None:
            return True
        return file_type in self._active_file_types
