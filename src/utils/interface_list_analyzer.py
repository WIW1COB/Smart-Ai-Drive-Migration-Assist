"""
Interface List Analyzer - Advanced Interface Analysis Tool
Analyzes interfaces, switches, dependencies, and data types from C/C++ source files
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from pathlib import Path
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


@dataclass
class InterfaceUsage:
    """Represents usage of an interface in source code"""
    interface_name: str
    interface_type: str  # function, variable, struct, enum, etc.
    data_type: str  # uint8, boolean, int32, etc.
    file_path: str
    line_number: int
    context: str  # surrounding code context
    is_declaration: bool = False
    is_definition: bool = False
    is_usage: bool = False


@dataclass
class SwitchInfo:
    """Represents a switch/conditional compilation directive"""
    switch_name: str
    switch_type: str  # ifdef, ifndef, if defined, etc.
    status: str  # enabled, disabled, conditional
    file_path: str
    line_number: int
    condition: str
    affected_code: List[str] = field(default_factory=list)


@dataclass
class DependencyInfo:
    """Represents file dependencies"""
    file_path: str
    includes: List[str] = field(default_factory=list)
    included_by: List[str] = field(default_factory=list)
    uses_functions: List[str] = field(default_factory=list)
    uses_variables: List[str] = field(default_factory=list)
    uses_types: List[str] = field(default_factory=list)
    defines_functions: List[str] = field(default_factory=list)
    defines_variables: List[str] = field(default_factory=list)
    defines_types: List[str] = field(default_factory=list)


@dataclass
class FileFlowInfo:
    """Represents the flow/control flow of a file"""
    file_path: str
    functions: List[str] = field(default_factory=list)
    function_calls: Dict[str, List[str]] = field(default_factory=dict)  # function -> calls
    control_structures: List[Dict] = field(default_factory=list)
    complexity: int = 0


@dataclass
class WorkspaceAnalysis:
    """Complete analysis of a workspace"""
    workspace_path: str
    interfaces: List[InterfaceUsage] = field(default_factory=list)
    switches: List[SwitchInfo] = field(default_factory=list)
    dependencies: Dict[str, DependencyInfo] = field(default_factory=dict)
    flow_info: Dict[str, FileFlowInfo] = field(default_factory=dict)
    data_types_used: Dict[str, int] = field(default_factory=dict)
    total_files: int = 0
    analyzed_files: int = 0


class InterfaceListAnalyzer:
    """Analyzes source code for interfaces, switches, and dependencies"""
    
    SUPPORTED_EXTENSIONS = {'.h', '.hpp', '.c', '.cpp', '.cc', '.cxx', '.hxx'}
    
    # Common data types in embedded systems
    DATA_TYPES = {
        'uint8', 'uint16', 'uint32', 'uint64',
        'int8', 'int16', 'int32', 'int64',
        'sint8', 'sint16', 'sint32', 'sint64',
        'boolean', 'bool', 'Boolean',
        'float', 'double',
        'char', 'void',
        'size_t', 'ptrdiff_t'
    }
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._type_pattern = None
        self._build_type_pattern()
    
    def _build_type_pattern(self):
        """Build regex pattern for data types"""
        types = '|'.join(self.DATA_TYPES)
        self._type_pattern = re.compile(
            rf'\b({types})(?:\s*\*|\s+\w+)',
            re.IGNORECASE
        )
    
    def analyze_workspace(self, workspace_path: str, recursive: bool = True) -> WorkspaceAnalysis:
        """Analyze entire workspace"""
        self.logger.info(f"Starting workspace analysis: {workspace_path}")
        
        analysis = WorkspaceAnalysis(workspace_path=workspace_path)
        
        # Collect all source files
        source_files = self._collect_source_files(workspace_path, recursive)
        analysis.total_files = len(source_files)
        
        self.logger.info(f"Found {len(source_files)} source files")
        
        # Analyze each file
        for file_path in source_files:
            try:
                self._analyze_file(file_path, analysis)
                analysis.analyzed_files += 1
            except Exception as e:
                self.logger.error(f"Error analyzing {file_path}: {e}")
        
        # Build dependency graph
        self._build_dependency_graph(analysis)
        
        # Analyze data type usage
        self._analyze_data_types(analysis)
        
        self.logger.info(f"Analysis complete: {analysis.analyzed_files}/{analysis.total_files} files")
        
        return analysis
    
    def _collect_source_files(self, path: str, recursive: bool) -> List[str]:
        """Collect all source files in the path"""
        files = []
        
        if os.path.isfile(path):
            if Path(path).suffix in self.SUPPORTED_EXTENSIONS:
                return [path]
            return []
        
        if not os.path.isdir(path):
            return []
        
        if recursive:
            for root, dirs, filenames in os.walk(path):
                for filename in filenames:
                    if Path(filename).suffix in self.SUPPORTED_EXTENSIONS:
                        files.append(os.path.join(root, filename))
        else:
            for filename in os.listdir(path):
                full_path = os.path.join(path, filename)
                if os.path.isfile(full_path) and Path(filename).suffix in self.SUPPORTED_EXTENSIONS:
                    files.append(full_path)
        
        return files
    
    def _analyze_file(self, file_path: str, analysis: WorkspaceAnalysis):
        """Analyze a single file"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            self.logger.warning(f"Could not read {file_path}: {e}")
            return
        
        # Extract interfaces
        self._extract_interfaces(file_path, content, analysis)
        
        # Extract switches
        self._extract_switches(file_path, content, analysis)
        
        # Extract dependencies
        self._extract_file_dependencies(file_path, content, analysis)
        
        # Extract flow information
        self._extract_flow_info(file_path, content, analysis)
    
    def _extract_interfaces(self, file_path: str, content: str, analysis: WorkspaceAnalysis):
        """Extract all interfaces from file"""
        lines = content.split('\n')
        
        # Function declarations/definitions
        func_pattern = re.compile(
            r'^\s*(?:(?:static|inline|extern)\s+)*'
            r'(\w+(?:\s*\*)*)\s+'  # return type
            r'(\w+)\s*'  # function name
            r'\((.*?)\)',  # parameters
            re.MULTILINE
        )
        
        for match in func_pattern.finditer(content):
            return_type = match.group(1).strip()
            func_name = match.group(2).strip()
            params = match.group(3).strip()
            
            line_num = content[:match.start()].count('\n') + 1
            context = lines[max(0, line_num-2):min(len(lines), line_num+2)]
            
            # Determine data type
            data_type = self._determine_data_type(return_type)
            
            interface = InterfaceUsage(
                interface_name=func_name,
                interface_type='function',
                data_type=data_type,
                file_path=file_path,
                line_number=line_num,
                context='\n'.join(context),
                is_declaration=True
            )
            analysis.interfaces.append(interface)
        
        # Variable declarations
        var_pattern = re.compile(
            r'^\s*(?:(?:extern|static|const|volatile)\s+)*'
            r'(\w+(?:\s*\*)*)\s+'  # type
            r'(\w+)\s*[;=]',  # variable name
            re.MULTILINE
        )
        
        for match in var_pattern.finditer(content):
            var_type = match.group(1).strip()
            var_name = match.group(2).strip()
            
            line_num = content[:match.start()].count('\n') + 1
            context = lines[max(0, line_num-1):min(len(lines), line_num+1)]
            
            data_type = self._determine_data_type(var_type)
            
            interface = InterfaceUsage(
                interface_name=var_name,
                interface_type='variable',
                data_type=data_type,
                file_path=file_path,
                line_number=line_num,
                context='\n'.join(context),
                is_declaration=True
            )
            analysis.interfaces.append(interface)
        
        # Struct/Enum definitions
        struct_pattern = re.compile(
            r'^\s*(?:typedef\s+)?(?:struct|enum)\s+(\w+)',
            re.MULTILINE
        )
        
        for match in struct_pattern.finditer(content):
            name = match.group(1).strip()
            line_num = content[:match.start()].count('\n') + 1
            context = lines[max(0, line_num-1):min(len(lines), line_num+3)]
            
            interface = InterfaceUsage(
                interface_name=name,
                interface_type='struct/enum',
                data_type='composite',
                file_path=file_path,
                line_number=line_num,
                context='\n'.join(context),
                is_definition=True
            )
            analysis.interfaces.append(interface)
    
    def _extract_switches(self, file_path: str, content: str, analysis: WorkspaceAnalysis):
        """Extract preprocessor switches"""
        lines = content.split('\n')
        
        # Pattern for #ifdef, #ifndef, #if defined
        switch_patterns = [
            (re.compile(r'^\s*#\s*ifdef\s+(\w+)'), 'ifdef'),
            (re.compile(r'^\s*#\s*ifndef\s+(\w+)'), 'ifndef'),
            (re.compile(r'^\s*#\s*if\s+defined\s*\(\s*(\w+)'), 'if defined'),
            (re.compile(r'^\s*#\s*if\s+(.+)'), 'if'),
        ]
        
        for line_num, line in enumerate(lines, 1):
            for pattern, switch_type in switch_patterns:
                match = pattern.match(line)
                if match:
                    switch_name = match.group(1).strip()
                    
                    # Determine status
                    status = self._determine_switch_status(content, switch_name)
                    
                    # Get affected code
                    affected = self._get_affected_code(lines, line_num)
                    
                    switch = SwitchInfo(
                        switch_name=switch_name,
                        switch_type=switch_type,
                        status=status,
                        file_path=file_path,
                        line_number=line_num,
                        condition=line.strip(),
                        affected_code=affected
                    )
                    analysis.switches.append(switch)
                    break
    
    def _determine_switch_status(self, content: str, switch_name: str) -> str:
        """Determine if a switch is enabled, disabled, or conditional"""
        # Check if the switch is defined
        define_pattern = re.compile(rf'^\s*#\s*define\s+{switch_name}\b', re.MULTILINE)
        if define_pattern.search(content):
            return 'enabled'
        
        undef_pattern = re.compile(rf'^\s*#\s*undef\s+{switch_name}\b', re.MULTILINE)
        if undef_pattern.search(content):
            return 'disabled'
        
        return 'conditional'
    
    def _get_affected_code(self, lines: List[str], start_line: int) -> List[str]:
        """Get code affected by a preprocessor directive"""
        affected = []
        depth = 1
        
        for i in range(start_line, len(lines)):
            line = lines[i]
            
            if re.match(r'^\s*#\s*if', line):
                depth += 1
            elif re.match(r'^\s*#\s*endif', line):
                depth -= 1
                if depth == 0:
                    break
            
            if depth == 1:
                affected.append(line.strip())
        
        return affected[:10]  # Limit to first 10 lines
    
    def _extract_file_dependencies(self, file_path: str, content: str, analysis: WorkspaceAnalysis):
        """Extract file dependencies"""
        dep_info = DependencyInfo(file_path=file_path)
        
        # Extract includes
        include_pattern = re.compile(r'^\s*#\s*include\s+[<"](.+?)[>"]', re.MULTILINE)
        for match in include_pattern.finditer(content):
            dep_info.includes.append(match.group(1))
        
        # Extract function definitions (what this file provides)
        func_def_pattern = re.compile(
            r'^\w+\s+(\w+)\s*\([^)]*\)\s*\{',
            re.MULTILINE
        )
        for match in func_def_pattern.finditer(content):
            dep_info.defines_functions.append(match.group(1))
        
        # Extract function calls (what this file uses)
        func_call_pattern = re.compile(r'\b(\w+)\s*\(')
        for match in func_call_pattern.finditer(content):
            func_name = match.group(1)
            if func_name not in dep_info.uses_functions:
                dep_info.uses_functions.append(func_name)
        
        analysis.dependencies[file_path] = dep_info
    
    def _extract_flow_info(self, file_path: str, content: str, analysis: WorkspaceAnalysis):
        """Extract control flow information"""
        flow = FileFlowInfo(file_path=file_path)
        
        # Extract function names
        func_pattern = re.compile(r'^\w+\s+(\w+)\s*\([^)]*\)\s*\{', re.MULTILINE)
        for match in func_pattern.finditer(content):
            flow.functions.append(match.group(1))
        
        # Extract control structures
        control_patterns = [
            (r'\bif\s*\(', 'if'),
            (r'\bfor\s*\(', 'for'),
            (r'\bwhile\s*\(', 'while'),
            (r'\bswitch\s*\(', 'switch'),
        ]
        
        for pattern, ctrl_type in control_patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                flow.control_structures.append({
                    'type': ctrl_type,
                    'line': line_num
                })
                flow.complexity += 1
        
        analysis.flow_info[file_path] = flow
    
    def _build_dependency_graph(self, analysis: WorkspaceAnalysis):
        """Build reverse dependencies (who includes whom)"""
        # Build a map of filename to full path
        file_map = {}
        for file_path in analysis.dependencies.keys():
            filename = os.path.basename(file_path)
            file_map[filename] = file_path
        
        # Build reverse dependencies
        for file_path, dep_info in analysis.dependencies.items():
            for include in dep_info.includes:
                include_basename = os.path.basename(include)
                if include_basename in file_map:
                    included_path = file_map[include_basename]
                    if included_path in analysis.dependencies:
                        analysis.dependencies[included_path].included_by.append(file_path)
    
    def _analyze_data_types(self, analysis: WorkspaceAnalysis):
        """Analyze data type usage statistics"""
        for interface in analysis.interfaces:
            dtype = interface.data_type
            if dtype:
                analysis.data_types_used[dtype] = analysis.data_types_used.get(dtype, 0) + 1
    
    def _determine_data_type(self, type_string: str) -> str:
        """Determine the base data type from a type string"""
        type_string = type_string.strip().replace('*', '').strip()
        
        # Common type mappings
        if 'uint8' in type_string or 'u8' in type_string:
            return 'uint8'
        elif 'uint16' in type_string or 'u16' in type_string:
            return 'uint16'
        elif 'uint32' in type_string or 'u32' in type_string:
            return 'uint32'
        elif 'uint64' in type_string or 'u64' in type_string:
            return 'uint64'
        elif 'int8' in type_string or 's8' in type_string or 'sint8' in type_string:
            return 'int8'
        elif 'int16' in type_string or 's16' in type_string or 'sint16' in type_string:
            return 'int16'
        elif 'int32' in type_string or 's32' in type_string or 'sint32' in type_string:
            return 'int32'
        elif 'int64' in type_string or 's64' in type_string or 'sint64' in type_string:
            return 'int64'
        elif 'bool' in type_string.lower():
            return 'boolean'
        elif 'float' in type_string:
            return 'float'
        elif 'double' in type_string:
            return 'double'
        elif 'char' in type_string:
            return 'char'
        elif 'void' in type_string:
            return 'void'
        else:
            return type_string
    
    def compare_workspaces(self, platform_path: str, project_path: str) -> Dict:
        """Compare two workspaces and identify differences"""
        self.logger.info(f"Comparing workspaces:\n  Platform: {platform_path}\n  Project: {project_path}")
        
        # Analyze both workspaces
        platform_analysis = self.analyze_workspace(platform_path)
        project_analysis = self.analyze_workspace(project_path)
        
        # Compare results
        comparison = {
            'platform': platform_analysis,
            'project': project_analysis,
            'differences': self._compute_differences(platform_analysis, project_analysis)
        }
        
        return comparison
    
    def _compute_differences(self, platform: WorkspaceAnalysis, project: WorkspaceAnalysis) -> Dict:
        """Compute differences between two analyses"""
        differences = {
            'interfaces': {
                'only_in_platform': [],
                'only_in_project': [],
                'modified': []
            },
            'switches': {
                'only_in_platform': [],
                'only_in_project': [],
                'status_changed': []
            },
            'dependencies': {
                'new_dependencies': [],
                'removed_dependencies': []
            }
        }
        
        # Compare interfaces
        platform_interfaces = {(i.interface_name, i.file_path): i for i in platform.interfaces}
        project_interfaces = {(i.interface_name, i.file_path): i for i in project.interfaces}
        
        for key in platform_interfaces:
            if key not in project_interfaces:
                differences['interfaces']['only_in_platform'].append(platform_interfaces[key])
        
        for key in project_interfaces:
            if key not in platform_interfaces:
                differences['interfaces']['only_in_project'].append(project_interfaces[key])
            elif platform_interfaces[key].data_type != project_interfaces[key].data_type:
                differences['interfaces']['modified'].append({
                    'platform': platform_interfaces[key],
                    'project': project_interfaces[key]
                })
        
        # Compare switches
        platform_switches = {(s.switch_name, s.file_path): s for s in platform.switches}
        project_switches = {(s.switch_name, s.file_path): s for s in project.switches}
        
        for key in platform_switches:
            if key not in project_switches:
                differences['switches']['only_in_platform'].append(platform_switches[key])
        
        for key in project_switches:
            if key not in platform_switches:
                differences['switches']['only_in_project'].append(project_switches[key])
            elif platform_switches[key].status != project_switches[key].status:
                differences['switches']['status_changed'].append({
                    'platform': platform_switches[key],
                    'project': project_switches[key]
                })
        
        return differences


def format_relative_path(full_path: str, base_path: str) -> str:
    """Format a relative path for display"""
    try:
        return os.path.relpath(full_path, base_path)
    except ValueError:
        return full_path
