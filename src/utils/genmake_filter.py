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

To handle this mismatch the filter checks whether the normalised rel_path
is an EXACT component-boundary-aligned suffix of any full CSV path:

    csv_path == rel_path            (exact match)
    csv_path.endswith("/" + rel_path)   (rel_path starts at a folder boundary)

This prevents false-positive matches based on short or unrelated sub-paths.
A file is ONLY included if its full path (relative to the selected folder
root) matches a complete trailing segment of the CSV entry — never by
filename alone.

Example:
    CSV path  : rb/as/core/app/dsm/rbrss/src/RBRSS_SupplyLossRequest.h
    User root : rb/                 → rel_path = as/core/app/dsm/rbrss/src/RBRSS_SupplyLossRequest.h  → MATCH
    User root : rb/as/core/         → rel_path = app/dsm/rbrss/src/RBRSS_SupplyLossRequest.h          → MATCH
    Other dir : other/src/RBRSS_SupplyLossRequest.h                                                    → NO MATCH
    Filename  : RBRSS_SupplyLossRequest.h                                                              → NO MATCH
"""

import csv
import os
import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class GenMakeFilter:
    """
    Holds the set of files listed in a Cfg_DBFiles_GenMake CSV and provides
    a membership test used to restrict file comparisons.

    Usage::

        f = GenMakeFilter.from_csv("Cfg_DBFiles_GenMake.csv")
        f.filter_file_types({"PreBuild", "PostBuild"})   # optional restriction
        if f.matches("as/core/.../RBRSS_SupplyLossRequest.h"):
            ...
    """

    def __init__(self):
        # {normalised_full_path: file_type}  – canonical CSV entries
        self._entries: Dict[str, str] = {}
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

        self.all_file_types = sorted(file_types_seen, key=str.lower)
        logger.info(
            f"GenMakeFilter: loaded {rows_loaded} entries, "
            f"{len(file_types_seen)} file types from {csv_path}"
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
        Return True if *rel_path* is a component-boundary-aligned suffix of any
        CSV entry (satisfying any active file-type filter).

        A match requires that the normalised rel_path either:
        - exactly equals a CSV entry's full path, OR
        - is a trailing segment of a CSV entry starting at a folder boundary
          (i.e. ``csv_path.endswith("/" + norm)``).

        This guarantees no false-positive matches by filename alone or by
        short unrelated sub-paths.  The file must reside at the exact location
        specified in the CSV relative to the user-selected comparison root.
        """
        norm = self._normalise(rel_path)
        slash_norm = "/" + norm
        for csv_path, file_type in self._entries.items():
            if not self._type_allowed(file_type):
                continue
            if csv_path == norm or csv_path.endswith(slash_norm):
                return True
        return False

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
