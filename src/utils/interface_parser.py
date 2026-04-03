"""
Interface Parser - Extract interfaces from C/C++ source files
Analyzes functions, structs, enums, macros, typedefs for baseline comparison
"""

import os
import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class InterfaceType(Enum):
    """Types of interfaces that can be extracted."""
    FUNCTION = "function"
    STRUCT = "struct"
    ENUM = "enum"
    MACRO = "macro"
    TYPEDEF = "typedef"
    EXTERN_VAR = "extern_var"
    INCLUDE = "include"
    DEFINE_GUARD = "define_guard"


@dataclass
class Parameter:
    """Function parameter representation."""
    name: str
    type: str
    default_value: Optional[str] = None
    
    def __str__(self):
        if self.default_value:
            return f"{self.type} {self.name} = {self.default_value}"
        return f"{self.type} {self.name}"


@dataclass
class StructField:
    """Struct/union field representation."""
    name: str
    type: str
    array_size: Optional[str] = None
    bit_field: Optional[int] = None
    comment: Optional[str] = None
    
    def __str__(self):
        result = f"{self.type} {self.name}"
        if self.array_size:
            result += f"[{self.array_size}]"
        if self.bit_field:
            result += f" : {self.bit_field}"
        return result


@dataclass
class EnumValue:
    """Enum value representation."""
    name: str
    value: Optional[str] = None
    comment: Optional[str] = None
    
    def __str__(self):
        if self.value:
            return f"{self.name} = {self.value}"
        return self.name


@dataclass
class InterfaceElement:
    """Represents a single interface element extracted from source code."""
    name: str
    type: InterfaceType
    file_path: str
    line_number: int
    signature: str
    raw_text: str = ""
    
    # Function-specific
    return_type: Optional[str] = None
    parameters: List[Parameter] = field(default_factory=list)
    is_static: bool = False
    is_inline: bool = False
    is_declaration: bool = True  # vs definition
    
    # Struct/Union-specific
    fields: List[StructField] = field(default_factory=list)
    is_union: bool = False
    
    # Enum-specific
    values: List[EnumValue] = field(default_factory=list)
    
    # Macro-specific
    macro_value: Optional[str] = None
    macro_params: List[str] = field(default_factory=list)
    
    # Typedef-specific
    typedef_target: Optional[str] = None
    
    # Comments/Documentation
    doxygen_comment: Optional[str] = None
    brief: Optional[str] = None
    
    def get_hash_key(self) -> str:
        """Generate unique key for this element."""
        return f"{self.type.value}:{self.name}:{self.signature[:50]}"


@dataclass
class FileInterfaces:
    """All interfaces extracted from a single file."""
    file_path: str
    relative_path: str
    functions: List[InterfaceElement] = field(default_factory=list)
    structs: List[InterfaceElement] = field(default_factory=list)
    enums: List[InterfaceElement] = field(default_factory=list)
    macros: List[InterfaceElement] = field(default_factory=list)
    typedefs: List[InterfaceElement] = field(default_factory=list)
    extern_vars: List[InterfaceElement] = field(default_factory=list)
    includes: List[str] = field(default_factory=list)
    
    def all_elements(self) -> List[InterfaceElement]:
        """Return all interface elements."""
        return (self.functions + self.structs + self.enums + 
                self.macros + self.typedefs + self.extern_vars)
    
    def count(self) -> int:
        """Total number of interface elements."""
        return len(self.all_elements())


class InterfaceParser:
    """Parse C/C++ source files to extract interface definitions."""
    
    SUPPORTED_EXTENSIONS = {'.h', '.hpp', '.c', '.cpp', '.cc', '.cxx', '.hxx'}
    
    def __init__(self, ignore_patterns: List[str] = None):
        self.ignore_patterns = ignore_patterns or []
        self._cache = {}
    
    def parse_file(self, file_path: str, base_folder: str = None) -> FileInterfaces:
        """Parse a single file and extract all interfaces."""
        if base_folder:
            rel_path = os.path.relpath(file_path, base_folder)
        else:
            rel_path = os.path.basename(file_path)
        
        result = FileInterfaces(file_path=file_path, relative_path=rel_path)
        
        # Check cache
        cache_key = f"{file_path}:{os.path.getmtime(file_path)}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            logger.warning(f"Could not read {file_path}: {e}")
            return result
        
        # Preprocess: remove string literals and comments to avoid false matches
        clean_content = self._preprocess_content(content)
        
        # Extract interfaces
        result.includes = self._extract_includes(content)
        result.functions = self._extract_functions(content, file_path)
        result.structs = self._extract_structs(content, file_path)
        result.enums = self._extract_enums(content, file_path)
        result.macros = self._extract_macros(content, file_path)
        result.typedefs = self._extract_typedefs(content, file_path)
        result.extern_vars = self._extract_extern_vars(content, file_path)
        
        # Cache result
        self._cache[cache_key] = result
        
        logger.debug(f"Parsed {rel_path}: {result.count()} interfaces")
        return result
    
    def parse_folder(self, folder_path: str, recursive: bool = True) -> Dict[str, FileInterfaces]:
        """Parse all source files in a folder."""
        results = {}
        
        if not os.path.isdir(folder_path):
            return results
        
        for root, dirs, files in os.walk(folder_path):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in self.SUPPORTED_EXTENSIONS:
                    continue
                
                if self._should_ignore(fname):
                    continue
                
                file_path = os.path.join(root, fname)
                rel_path = os.path.relpath(file_path, folder_path)
                
                try:
                    interfaces = self.parse_file(file_path, folder_path)
                    results[rel_path] = interfaces
                except Exception as e:
                    logger.error(f"Error parsing {rel_path}: {e}")
        
        total_interfaces = sum(fi.count() for fi in results.values())
        logger.info(f"Parsed {len(results)} files, found {total_interfaces} interfaces")
        return results
    
    def _should_ignore(self, filename: str) -> bool:
        """Check if file should be ignored based on patterns."""
        import fnmatch
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False
    
    def _preprocess_content(self, content: str) -> str:
        """Remove string literals and comments to avoid false regex matches."""
        # Remove string literals
        content = re.sub(r'"(?:[^"\\]|\\.)*"', '""', content)
        # Remove character literals
        content = re.sub(r"'(?:[^'\\]|\\.)*'", "''", content)
        # Remove multi-line comments
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # Remove single-line comments
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)
        return content
    
    def _get_line_number(self, content: str, match_start: int) -> int:
        """Get line number from character position."""
        return content[:match_start].count('\n') + 1
    
    def _extract_includes(self, content: str) -> List[str]:
        """Extract #include statements."""
        includes = []
        include_pattern = re.compile(r'^\s*#\s*include\s+[<"](?P<path>[^>"]+)[>"]', re.MULTILINE)
        for match in include_pattern.finditer(content):
            includes.append(match.group('path'))
        return includes
    
    def _extract_functions(self, content: str, file_path: str) -> List[InterfaceElement]:
        """Extract function declarations and definitions."""
        functions = []
        func_pattern = re.compile(
            r'^\s*(?P<static>static\s+)?(?P<inline>inline\s+)?'
            r'(?P<return>[\w\s\*]+?)\s+(?P<name>\b[A-Z_a-z]\w*\b)\s*'
            r'\((?P<params>[^)]*)\)\s*(?P<end>[;{])',
            re.MULTILINE
        )
        
        for match in func_pattern.finditer(content):
            name = match.group('name')
            if name in ('if', 'while', 'for', 'switch', 'return', 'sizeof'):
                continue
            
            return_type = match.group('return').strip()
            params_str = match.group('params').strip()
            parameters = self._parse_parameters(params_str)
            
            func = InterfaceElement(
                name=name,
                type=InterfaceType.FUNCTION,
                file_path=file_path,
                line_number=self._get_line_number(content, match.start()),
                signature=f"{return_type} {name}({params_str})",
                return_type=return_type,
                parameters=parameters,
                is_static=bool(match.group('static')),
                is_inline=bool(match.group('inline')),
                is_declaration=(match.group('end') == ';')
            )
            functions.append(func)
        
        return functions
    
    def _parse_parameters(self, params_str: str) -> List[Parameter]:
        """Parse function parameter string into Parameter objects."""
        params = []
        
        if not params_str or params_str.strip() == 'void':
            return params
        
        # Split by comma (careful with nested templates/function pointers)
        depth = 0
        current = ""
        for char in params_str:
            if char in '([{':
                depth += 1
            elif char in ')]}':
                depth -= 1
            elif char == ',' and depth == 0:
                if current.strip():
                    params.append(self._parse_single_param(current))
                current = ""
                continue
            current += char
        
        if current.strip():
            params.append(self._parse_single_param(current))
        
        return params
    
    def _parse_single_param(self, param_str: str) -> Parameter:
        """Parse a single parameter string."""
        # Handle default values
        default = None
        if '=' in param_str:
            param_str, default = param_str.split('=', 1)
            default = default.strip()
        
        # Split type and name
        parts = param_str.rsplit(None, 1)
        if len(parts) == 2:
            ptype, pname = parts
            return Parameter(name=pname.strip(), type=ptype.strip(), default_value=default)
        else:
            pname = param_str.strip()
            return Parameter(name=pname, type="auto", default_value=default)
    
    def _extract_structs(self, content: str, file_path: str) -> List[InterfaceElement]:
        """Extract struct definitions."""
        structs = []
        struct_pattern = re.compile(
            r'(?:typedef\s+)?(?P<keyword>struct|union)\s+(?P<name>\w+)?\s*'
            r'\{(?P<body>[^}]*)\}\s*(?P<typedef_name>\w+)?\s*;',
            re.DOTALL
        )
        
        for match in struct_pattern.finditer(content):
            name = match.group('name') or match.group('typedef_name') or ""
            if not name:
                continue
            
            struct = InterfaceElement(
                name=name,
                type=InterfaceType.STRUCT,
                file_path=file_path,
                line_number=self._get_line_number(content, match.start()),
                signature=f"{match.group('keyword')} {name}",
                is_union=(match.group('keyword') == 'union')
            )
            structs.append(struct)
        
        return structs
    
    def _extract_enums(self, content: str, file_path: str) -> List[InterfaceElement]:
        """Extract enum definitions."""
        enums = []
        enum_pattern = re.compile(
            r'(?:typedef\s+)?enum\s+(?P<name>\w+)?\s*'
            r'\{(?P<body>[^}]*)\}\s*(?P<typedef_name>\w+)?\s*;',
            re.DOTALL
        )
        
        for match in enum_pattern.finditer(content):
            name = match.group('name') or match.group('typedef_name') or ""
            if not name:
                continue
            
            enum = InterfaceElement(
                name=name,
                type=InterfaceType.ENUM,
                file_path=file_path,
                line_number=self._get_line_number(content, match.start()),
                signature=f"enum {name}"
            )
            enums.append(enum)
        
        return enums
    
    def _extract_macros(self, content: str, file_path: str) -> List[InterfaceElement]:
        """Extract #define macros."""
        macros = []
        macro_pattern = re.compile(
            r'^\s*#\s*define\s+(?P<name>\w+)(?:\((?P<params>[^)]*)\))?\s*(?P<value>(?:[^\n\\]|\\\n)*)',
            re.MULTILINE
        )
        
        for match in macro_pattern.finditer(content):
            name = match.group('name')
            
            # Skip include guards
            if (name.endswith('_H') or name.endswith('_H_') or 
                name.endswith('_HPP_')) and name.startswith('_'):
                continue
            
            value = match.group('value').strip()
            
            macro = InterfaceElement(
                name=name,
                type=InterfaceType.MACRO,
                file_path=file_path,
                line_number=self._get_line_number(content, match.start()),
                signature=f"#define {name}",
                macro_value=value
            )
            macros.append(macro)
        
        return macros
    
    def _extract_typedefs(self, content: str, file_path: str) -> List[InterfaceElement]:
        """Extract typedef declarations."""
        typedefs = []
        typedef_pattern = re.compile(
            r'^\s*typedef\s+(?!struct|union|enum)(?P<target>[\w\s\*]+?)\s+(?P<name>\w+)\s*;',
            re.MULTILINE
        )
        
        for match in typedef_pattern.finditer(content):
            typedef = InterfaceElement(
                name=match.group('name'),
                type=InterfaceType.TYPEDEF,
                file_path=file_path,
                line_number=self._get_line_number(content, match.start()),
                signature=f"typedef {match.group('target')} {match.group('name')}",
                typedef_target=match.group('target').strip()
            )
            typedefs.append(typedef)
        
        return typedefs
    
    def _extract_extern_vars(self, content: str, file_path: str) -> List[InterfaceElement]:
        """Extract extern variable declarations."""
        extern_vars = []
        extern_pattern = re.compile(
            r'^\s*extern\s+(?P<type>[\w\s\*]+?)\s+(?P<name>\w+)\s*;',
            re.MULTILINE
        )
        
        for match in extern_pattern.finditer(content):
            extern_var = InterfaceElement(
                name=match.group('name'),
                type=InterfaceType.EXTERN_VAR,
                file_path=file_path,
                line_number=self._get_line_number(content, match.start()),
                signature=f"extern {match.group('type')} {match.group('name')}"
            )
            extern_vars.append(extern_var)
        
        return extern_vars
