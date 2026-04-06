"""
Dependency Graph Builder
Builds #include dependency graph to understand impact of interface changes.

Enterprise-grade dependency analysis for embedded software.
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional, Tuple
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DependencyNode:
    """Represents a file in the dependency graph."""
    file_path: str
    relative_path: str
    
    # Direct dependencies (files this file includes)
    includes: Set[str] = field(default_factory=set)
    
    # Reverse dependencies (files that include this file)
    included_by: Set[str] = field(default_factory=set)
    
    # Resolved paths (actual file paths, not just include names)
    resolved_includes: Set[str] = field(default_factory=set)
    
    # Metadata
    is_header: bool = False
    is_source: bool = False
    is_system_include: bool = False
    
    def __hash__(self):
        return hash(self.relative_path)


@dataclass
class DependencyGraph:
    """Complete dependency graph for a codebase."""
    root_path: str
    
    # All nodes indexed by relative path
    nodes: Dict[str, DependencyNode] = field(default_factory=dict)
    
    # Cached analysis results
    _impact_cache: Dict[str, Set[str]] = field(default_factory=dict)
    _circular_deps: List[List[str]] = field(default_factory=list)
    
    def get_node(self, rel_path: str) -> Optional[DependencyNode]:
        """Get node by relative path."""
        return self.nodes.get(rel_path)
    
    def get_dependents(self, rel_path: str, recursive: bool = False) -> Set[str]:
        """
        Get files that depend on the given file.
        
        Args:
            rel_path: Relative path of the file
            recursive: If True, get transitive dependents
            
        Returns:
            Set of relative paths that depend on this file
        """
        node = self.nodes.get(rel_path)
        if not node:
            return set()
        
        if not recursive:
            return node.included_by.copy()
        
        # BFS for transitive dependents
        visited = set()
        queue = list(node.included_by)
        
        while queue:
            dep = queue.pop(0)
            if dep in visited:
                continue
            visited.add(dep)
            
            dep_node = self.nodes.get(dep)
            if dep_node:
                queue.extend(dep_node.included_by - visited)
        
        return visited
    
    def get_dependencies(self, rel_path: str, recursive: bool = False) -> Set[str]:
        """
        Get files that the given file depends on.
        
        Args:
            rel_path: Relative path of the file
            recursive: If True, get transitive dependencies
            
        Returns:
            Set of relative paths this file depends on
        """
        node = self.nodes.get(rel_path)
        if not node:
            return set()
        
        if not recursive:
            return node.resolved_includes.copy()
        
        # BFS for transitive dependencies
        visited = set()
        queue = list(node.resolved_includes)
        
        while queue:
            dep = queue.pop(0)
            if dep in visited:
                continue
            visited.add(dep)
            
            dep_node = self.nodes.get(dep)
            if dep_node:
                queue.extend(dep_node.resolved_includes - visited)
        
        return visited
    
    def get_impact_radius(self, rel_path: str) -> int:
        """
        Calculate impact radius - number of files affected by changes to this file.
        
        Args:
            rel_path: Relative path of the file
            
        Returns:
            Number of files that would be affected
        """
        dependents = self.get_dependents(rel_path, recursive=True)
        return len(dependents)
    
    def find_circular_dependencies(self) -> List[List[str]]:
        """
        Find all circular dependency chains.
        
        Returns:
            List of circular dependency chains (each chain is a list of file paths)
        """
        # Implementation uses DFS with path tracking
        visited = set()
        rec_stack = set()
        path = []
        cycles = []
        
        def dfs(node_path: str):
            visited.add(node_path)
            rec_stack.add(node_path)
            path.append(node_path)
            
            node = self.nodes.get(node_path)
            if node:
                for dep in node.resolved_includes:
                    if dep not in visited:
                        dfs(dep)
                    elif dep in rec_stack:
                        # Found cycle
                        cycle_start = path.index(dep)
                        cycle = path[cycle_start:] + [dep]
                        cycles.append(cycle)
            
            path.pop()
            rec_stack.remove(node_path)
        
        for node_path in self.nodes:
            if node_path not in visited:
                dfs(node_path)
        
        self._circular_deps = cycles
        return cycles


class DependencyGraphBuilder:
    """
    Builds a dependency graph by parsing #include statements.
    
    Features:
    - Parses #include "file.h" and #include <file.h>
    - Resolves include paths to actual files
    - Builds forward and reverse dependency maps
    - Detects circular dependencies
    - Calculates impact radius for each file
    """
    
    # File extensions to scan
    SOURCE_EXTENSIONS = {'.c', '.cc', '.cpp', '.cxx'}
    HEADER_EXTENSIONS = {'.h', '.hh', '.hpp', '.hxx'}
    
    # Include patterns
    INCLUDE_PATTERN = re.compile(
        r'^\s*#\s*include\s+'
        r'(?P<bracket>[<"])(?P<path>[^>"]+)[>"]',
        re.MULTILINE
    )
    
    def __init__(self, include_dirs: List[str] = None):
        """
        Initialize builder.
        
        Args:
            include_dirs: Additional directories to search for includes
        """
        self.include_dirs = include_dirs or []
    
    def build_graph(self, root_path: str) -> DependencyGraph:
        """
        Build dependency graph for a folder.
        
        Args:
            root_path: Path to source folder
            
        Returns:
            DependencyGraph with all dependencies
        """
        logger.info(f"Building dependency graph for: {root_path}")
        
        graph = DependencyGraph(root_path=root_path)
        
        # First pass: collect all files and their direct includes
        all_files = self._collect_files(root_path)
        
        for rel_path, abs_path in all_files.items():
            node = self._parse_file(abs_path, rel_path)
            graph.nodes[rel_path] = node
        
        # Second pass: resolve includes to actual files
        self._resolve_includes(graph, all_files)
        
        # Third pass: build reverse dependencies
        self._build_reverse_deps(graph)
        
        logger.info(f"Dependency graph built: {len(graph.nodes)} files")
        
        # Log some stats
        header_count = sum(1 for n in graph.nodes.values() if n.is_header)
        source_count = sum(1 for n in graph.nodes.values() if n.is_source)
        logger.info(f"  Headers: {header_count}")
        logger.info(f"  Sources: {source_count}")
        
        # Find most impactful headers
        impact_list = [(p, graph.get_impact_radius(p)) for p in graph.nodes if graph.nodes[p].is_header]
        impact_list.sort(key=lambda x: x[1], reverse=True)
        if impact_list:
            logger.info("Top 5 most impactful headers:")
            for path, impact in impact_list[:5]:
                logger.info(f"    {path}: {impact} dependents")
        
        return graph
    
    def _collect_files(self, root_path: str) -> Dict[str, str]:
        """Collect all source and header files."""
        files = {}
        
        for root, dirs, file_list in os.walk(root_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for fname in file_list:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.SOURCE_EXTENSIONS or ext in self.HEADER_EXTENSIONS:
                    abs_path = os.path.join(root, fname)
                    rel_path = os.path.relpath(abs_path, root_path)
                    files[rel_path] = abs_path
        
        return files
    
    def _parse_file(self, abs_path: str, rel_path: str) -> DependencyNode:
        """Parse a file and extract its includes."""
        ext = os.path.splitext(rel_path)[1].lower()
        
        node = DependencyNode(
            file_path=abs_path,
            relative_path=rel_path,
            is_header=(ext in self.HEADER_EXTENSIONS),
            is_source=(ext in self.SOURCE_EXTENSIONS)
        )
        
        try:
            with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"Could not read {rel_path}: {e}")
            return node
        
        # Extract includes
        for match in self.INCLUDE_PATTERN.finditer(content):
            bracket = match.group('bracket')
            path = match.group('path')
            
            # Track if it's a system include
            if bracket == '<':
                node.is_system_include = True
            
            node.includes.add(path)
        
        return node
    
    def _resolve_includes(self, graph: DependencyGraph, all_files: Dict[str, str]):
        """Resolve include paths to actual file paths."""
        
        # Build lookup index for faster resolution
        filename_index = defaultdict(list)
        for rel_path in all_files:
            fname = os.path.basename(rel_path)
            filename_index[fname].append(rel_path)
        
        for rel_path, node in graph.nodes.items():
            file_dir = os.path.dirname(rel_path)
            
            for include_path in node.includes:
                resolved = self._resolve_single_include(
                    include_path, file_dir, filename_index, all_files
                )
                if resolved:
                    node.resolved_includes.add(resolved)
    
    def _resolve_single_include(self, include_path: str, file_dir: str,
                                 filename_index: Dict[str, List[str]],
                                 all_files: Dict[str, str]) -> Optional[str]:
        """Resolve a single include to a file path."""
        
        # Normalize path separators
        include_path = include_path.replace('\\', '/')
        fname = os.path.basename(include_path)
        
        # Strategy 1: Relative to current file
        relative_path = os.path.normpath(os.path.join(file_dir, include_path))
        relative_path = relative_path.replace('\\', '/')
        if relative_path in all_files:
            return relative_path
        
        # Strategy 2: Direct match by filename
        if fname in filename_index:
            candidates = filename_index[fname]
            if len(candidates) == 1:
                return candidates[0]
            
            # If multiple candidates, prefer one in same directory tree
            for candidate in candidates:
                if file_dir in candidate or candidate.startswith(file_dir):
                    return candidate
            
            # Otherwise just return first match
            return candidates[0]
        
        # Strategy 3: Look in include directories
        for inc_dir in self.include_dirs:
            try_path = os.path.join(inc_dir, include_path)
            if try_path in all_files:
                return try_path
        
        # Could not resolve - probably system header
        return None
    
    def _build_reverse_deps(self, graph: DependencyGraph):
        """Build reverse dependency map (who includes me)."""
        
        for rel_path, node in graph.nodes.items():
            for dep in node.resolved_includes:
                dep_node = graph.nodes.get(dep)
                if dep_node:
                    dep_node.included_by.add(rel_path)


@dataclass
class ImpactAnalysis:
    """Result of impact analysis for a file change."""
    changed_file: str
    
    # Direct dependents
    direct_dependents: List[str] = field(default_factory=list)
    
    # Transitive dependents
    all_dependents: List[str] = field(default_factory=list)
    
    # Impact by severity
    headers_affected: int = 0
    sources_affected: int = 0
    
    # Functional areas affected
    functional_areas: Dict[str, int] = field(default_factory=dict)
    
    def __str__(self):
        return (f"Impact: {self.changed_file}\n"
                f"  Direct: {len(self.direct_dependents)} files\n"
                f"  Total:  {len(self.all_dependents)} files")


class ImpactAnalyzer:
    """
    Analyzes the impact of interface changes using dependency graph.
    """
    
    # Functional area patterns (same as InterfaceDiffEngine)
    FUNCTIONAL_PATTERNS = {
        'CAN': ['CAN_', 'can_', 'Can_', '_CAN', '_can'],
        'UART': ['UART_', 'uart_', 'Uart_', '_UART', '_uart', 'Serial_'],
        'SPI': ['SPI_', 'spi_', 'Spi_', '_SPI', '_spi'],
        'I2C': ['I2C_', 'i2c_', 'I2c_', '_I2C', '_i2c', 'TWI_'],
        'GPIO': ['GPIO_', 'gpio_', 'Gpio_', 'Port_', 'Pin_', 'IO_'],
        'ADC': ['ADC_', 'adc_', 'Adc_', 'Analog_'],
        'PWM': ['PWM_', 'pwm_', 'Pwm_'],
        'Timer': ['Timer_', 'timer_', 'TIMER_', 'TMR_', 'Tmr_'],
        'Diagnostics': ['Diag_', 'diag_', 'DIAG_', 'Dcm_', 'Dem_'],
        'Memory': ['NvM_', 'nvm_', 'NVM_', 'Flash_', 'FLASH_', 'Eeprom_'],
        'OS/RTOS': ['Os_', 'os_', 'OS_', 'Task_', 'TASK_', 'Rtos_'],
    }
    
    def __init__(self, graph: DependencyGraph):
        """
        Initialize analyzer.
        
        Args:
            graph: Pre-built dependency graph
        """
        self.graph = graph
    
    def analyze_impact(self, changed_file: str) -> ImpactAnalysis:
        """
        Analyze impact of changes to a file.
        
        Args:
            changed_file: Relative path of changed file
            
        Returns:
            ImpactAnalysis with affected files
        """
        result = ImpactAnalysis(changed_file=changed_file)
        
        # Get direct dependents
        direct = self.graph.get_dependents(changed_file, recursive=False)
        result.direct_dependents = sorted(direct)
        
        # Get all transitive dependents
        all_deps = self.graph.get_dependents(changed_file, recursive=True)
        result.all_dependents = sorted(all_deps)
        
        # Categorize
        for dep in all_deps:
            node = self.graph.get_node(dep)
            if node:
                if node.is_header:
                    result.headers_affected += 1
                if node.is_source:
                    result.sources_affected += 1
                
                # Detect functional area
                area = self._detect_functional_area(dep)
                result.functional_areas[area] = result.functional_areas.get(area, 0) + 1
        
        return result
    
    def analyze_multiple(self, changed_files: List[str]) -> Dict[str, ImpactAnalysis]:
        """
        Analyze impact of multiple file changes.
        
        Args:
            changed_files: List of relative paths
            
        Returns:
            Dict mapping file paths to ImpactAnalysis
        """
        results = {}
        for path in changed_files:
            results[path] = self.analyze_impact(path)
        return results
    
    def _detect_functional_area(self, file_path: str) -> str:
        """Detect functional area from file path."""
        path_lower = file_path.lower()
        
        for area, patterns in self.FUNCTIONAL_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in path_lower:
                    return area
        
        return "General"
    
    def get_high_impact_files(self, min_impact: int = 10) -> List[Tuple[str, int]]:
        """
        Get files with high impact radius (modifying them affects many files).
        
        Args:
            min_impact: Minimum number of dependents to be considered high impact
            
        Returns:
            List of (file_path, impact_count) sorted by impact
        """
        results = []
        
        for rel_path in self.graph.nodes:
            impact = self.graph.get_impact_radius(rel_path)
            if impact >= min_impact:
                results.append((rel_path, impact))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results


# Convenience functions
def build_dependency_graph(root_path: str, include_dirs: List[str] = None) -> DependencyGraph:
    """
    Build dependency graph for a folder.
    
    Args:
        root_path: Path to source folder
        include_dirs: Additional include directories
        
    Returns:
        DependencyGraph
    """
    builder = DependencyGraphBuilder(include_dirs=include_dirs)
    return builder.build_graph(root_path)


def analyze_change_impact(graph: DependencyGraph, changed_file: str) -> ImpactAnalysis:
    """
    Analyze impact of changing a file.
    
    Args:
        graph: Pre-built dependency graph
        changed_file: Relative path of changed file
        
    Returns:
        ImpactAnalysis
    """
    analyzer = ImpactAnalyzer(graph)
    return analyzer.analyze_impact(changed_file)
