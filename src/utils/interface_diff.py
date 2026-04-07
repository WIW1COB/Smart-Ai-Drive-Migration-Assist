"""
Interface Diff Engine
Compares interfaces between two baselines and categorizes changes.

Enterprise-grade interface comparison for embedded software migration.
"""

import os
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple
from enum import Enum

from .interface_parser import (
    InterfaceParser, InterfaceElement, InterfaceType, 
    FileInterfaces, Parameter, StructField, EnumValue
)

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Type of change detected."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


class Severity(Enum):
    """Severity of the change for migration impact."""
    BREAKING = "breaking"      # Will break dependent code
    REVIEW = "review"          # Needs manual review
    SAFE = "safe"              # Safe to auto-merge
    INFO = "info"              # Informational only


@dataclass
class InterfaceDiff:
    """Represents a difference in a single interface element."""
    element_name: str
    interface_type: InterfaceType
    change_type: ChangeType
    severity: Severity
    
    # File information
    file_path: str
    line_baseline: Optional[int] = None
    line_target: Optional[int] = None
    
    # The elements being compared
    baseline_element: Optional[InterfaceElement] = None
    target_element: Optional[InterfaceElement] = None
    
    # Diff details
    diff_summary: str = ""
    diff_details: List[str] = field(default_factory=list)
    
    # Impact analysis
    functional_area: str = ""
    impact_description: str = ""
    
    def __str__(self):
        severity_icon = {
            Severity.BREAKING: "🔴",
            Severity.REVIEW: "🟡",
            Severity.SAFE: "🟢",
            Severity.INFO: "ℹ️"
        }.get(self.severity, "")
        
        return f"{severity_icon} [{self.change_type.value.upper()}] {self.interface_type.value}: {self.element_name}"


@dataclass
class FileDiff:
    """All interface differences for a single file."""
    relative_path: str
    file_path_baseline: Optional[str] = None
    file_path_target: Optional[str] = None
    
    # File-level status
    file_status: str = "unchanged"  # added, removed, modified, unchanged
    
    # Interface diffs
    diffs: List[InterfaceDiff] = field(default_factory=list)
    
    # Summary counts
    breaking_count: int = 0
    review_count: int = 0
    safe_count: int = 0
    
    def count_by_severity(self):
        """Update counts by severity."""
        self.breaking_count = sum(1 for d in self.diffs if d.severity == Severity.BREAKING)
        self.review_count = sum(1 for d in self.diffs if d.severity == Severity.REVIEW)
        self.safe_count = sum(1 for d in self.diffs if d.severity == Severity.SAFE)


@dataclass
class BaselineDiff:
    """Complete diff between two baselines."""
    baseline_path: str
    target_path: str
    
    # File diffs
    file_diffs: Dict[str, FileDiff] = field(default_factory=dict)
    
    # Summary
    total_files: int = 0
    files_added: int = 0
    files_removed: int = 0
    files_modified: int = 0
    files_unchanged: int = 0
    
    total_interfaces: int = 0
    interfaces_added: int = 0
    interfaces_removed: int = 0
    interfaces_modified: int = 0
    
    breaking_changes: int = 0
    review_needed: int = 0
    safe_changes: int = 0
    
    # By functional area
    by_functional_area: Dict[str, List[InterfaceDiff]] = field(default_factory=dict)
    
    # By interface type
    by_type: Dict[InterfaceType, List[InterfaceDiff]] = field(default_factory=dict)


class InterfaceDiffEngine:
    """
    Compares interfaces between two baselines.
    
    Detects:
    - New interfaces (functions, structs, enums, macros)
    - Removed interfaces
    - Modified interfaces (signature changes, field changes, etc.)
    - Categorizes by severity (BREAKING, REVIEW, SAFE)
    """
    
    # Patterns for functional area detection
    FUNCTIONAL_PATTERNS = {
        'CAN': ['CAN_', 'can_', 'Can_', '_CAN', '_can'],
        'UART': ['UART_', 'uart_', 'Uart_', '_UART', '_uart', 'Serial_'],
        'SPI': ['SPI_', 'spi_', 'Spi_', '_SPI', '_spi'],
        'I2C': ['I2C_', 'i2c_', 'I2c_', '_I2C', '_i2c', 'TWI_'],
        'GPIO': ['GPIO_', 'gpio_', 'Gpio_', 'Port_', 'Pin_', 'IO_'],
        'ADC': ['ADC_', 'adc_', 'Adc_', 'Analog_'],
        'PWM': ['PWM_', 'pwm_', 'Pwm_'],
        'Timer': ['Timer_', 'timer_', 'TIMER_', 'TMR_', 'Tmr_'],
        'DMA': ['DMA_', 'dma_', 'Dma_'],
        'Interrupt': ['IRQ_', 'irq_', 'ISR_', 'isr_', 'Int_', 'Interrupt_'],
        'Diagnostics': ['Diag_', 'diag_', 'DIAG_', 'Dcm_', 'Dem_'],
        'Memory': ['NvM_', 'nvm_', 'NVM_', 'Flash_', 'FLASH_', 'Eeprom_', 'EEPROM_'],
        'OS/RTOS': ['Os_', 'os_', 'OS_', 'Task_', 'TASK_', 'Rtos_'],
        'Communication': ['Com_', 'com_', 'COM_', 'Msg_', 'Message_'],
        'Safety': ['Safe_', 'safe_', 'SAFE_', 'Wdg_', 'WDG_', 'Watchdog_'],
        'Calibration': ['Cal_', 'cal_', 'CAL_', 'Calib_'],
        'Application': ['App_', 'app_', 'APP_', 'Main_'],
    }
    
    def __init__(self, ignore_patterns: List[str] = None):
        """
        Initialize diff engine.
        
        Args:
            ignore_patterns: Patterns for files to ignore
        """
        self.ignore_patterns = ignore_patterns or ['*_test.c', '*_mock.c', 'test_*.c']
        self.parser = InterfaceParser(ignore_patterns=self.ignore_patterns)
    
    def compare_baselines(self, baseline_path: str, target_path: str,
                          baseline_scope: Optional[str] = None,
                          target_scope: Optional[str] = None) -> BaselineDiff:
        """
        Compare all interfaces between two baselines.
        
        Args:
            baseline_path: Path to baseline folder (Stream 1)
            target_path: Path to target folder (Stream 2)
            
        Returns:
            BaselineDiff with all differences
        """
        logger.info(f"Comparing baselines:")
        logger.info(f"  Baseline root: {baseline_path}")
        logger.info(f"  Target root:   {target_path}")
        logger.info(f"  Baseline scope: {baseline_scope or 'full'}")
        logger.info(f"  Target scope:   {target_scope or 'full'}")

        result = BaselineDiff(baseline_path=baseline_path, target_path=target_path)

        # Determine actual paths to parse based on scope
        baseline_parse_path = baseline_scope if baseline_scope else baseline_path
        target_parse_path = target_scope if target_scope else target_path

        # Parse both baselines
        logger.info("Parsing baseline interfaces...")
        baseline_interfaces = self.parser.parse_folder(baseline_parse_path)

        logger.info("Parsing target interfaces...")
        target_interfaces = self.parser.parse_folder(target_parse_path)

        # Adjust relative paths to be root-relative if parsing subfolder
        if baseline_scope and baseline_scope != baseline_path:
            baseline_interfaces = self._adjust_relative_paths(baseline_interfaces, baseline_scope, baseline_path)
        if target_scope and target_scope != target_path:
            target_interfaces = self._adjust_relative_paths(target_interfaces, target_scope, target_path)
        
        # Get all file paths
        baseline_files = set(baseline_interfaces.keys())
        target_files = set(target_interfaces.keys())
        all_files = baseline_files | target_files
        
        result.total_files = len(all_files)
        
        # Compare each file
        for rel_path in sorted(all_files):
            file_diff = self._compare_file(
                rel_path,
                baseline_interfaces.get(rel_path),
                target_interfaces.get(rel_path)
            )
            
            if file_diff.diffs or file_diff.file_status != "unchanged":
                result.file_diffs[rel_path] = file_diff
            
            # Update counts
            if file_diff.file_status == "added":
                result.files_added += 1
            elif file_diff.file_status == "removed":
                result.files_removed += 1
            elif file_diff.file_status == "modified":
                result.files_modified += 1
            else:
                result.files_unchanged += 1
            
            # Aggregate interface changes
            for diff in file_diff.diffs:
                if diff.change_type == ChangeType.ADDED:
                    result.interfaces_added += 1
                elif diff.change_type == ChangeType.REMOVED:
                    result.interfaces_removed += 1
                elif diff.change_type == ChangeType.MODIFIED:
                    result.interfaces_modified += 1
                
                if diff.severity == Severity.BREAKING:
                    result.breaking_changes += 1
                elif diff.severity == Severity.REVIEW:
                    result.review_needed += 1
                elif diff.severity == Severity.SAFE:
                    result.safe_changes += 1
                
                # Group by functional area
                area = diff.functional_area or "Other"
                if area not in result.by_functional_area:
                    result.by_functional_area[area] = []
                result.by_functional_area[area].append(diff)
                
                # Group by type
                if diff.interface_type not in result.by_type:
                    result.by_type[diff.interface_type] = []
                result.by_type[diff.interface_type].append(diff)
        
        result.total_interfaces = (result.interfaces_added + 
                                   result.interfaces_removed + 
                                   result.interfaces_modified)
        
        self._log_summary(result)
        return result
    
    def _compare_file(self, rel_path: str, 
                      baseline: Optional[FileInterfaces], 
                      target: Optional[FileInterfaces]) -> FileDiff:
        """Compare interfaces in a single file."""
        
        file_diff = FileDiff(relative_path=rel_path)
        
        if baseline:
            file_diff.file_path_baseline = baseline.file_path
        if target:
            file_diff.file_path_target = target.file_path
        
        # Determine file status
        if not baseline and target:
            file_diff.file_status = "added"
            # All interfaces are new
            for elem in target.all_elements():
                diff = self._create_added_diff(elem, rel_path)
                file_diff.diffs.append(diff)
        
        elif baseline and not target:
            file_diff.file_status = "removed"
            # All interfaces are removed
            for elem in baseline.all_elements():
                diff = self._create_removed_diff(elem, rel_path)
                file_diff.diffs.append(diff)
        
        elif baseline and target:
            # Compare interfaces
            file_diff.file_status = "unchanged"  # May change to "modified"
            
            # Compare by interface type
            diffs = []
            diffs.extend(self._compare_elements(baseline.functions, target.functions, rel_path))
            diffs.extend(self._compare_elements(baseline.structs, target.structs, rel_path))
            diffs.extend(self._compare_elements(baseline.enums, target.enums, rel_path))
            diffs.extend(self._compare_elements(baseline.macros, target.macros, rel_path))
            diffs.extend(self._compare_elements(baseline.typedefs, target.typedefs, rel_path))
            diffs.extend(self._compare_elements(baseline.extern_vars, target.extern_vars, rel_path))
            
            file_diff.diffs = diffs
            if diffs:
                file_diff.file_status = "modified"
        
        file_diff.count_by_severity()
        return file_diff
    
    def _compare_elements(self, baseline_list: List[InterfaceElement],
                          target_list: List[InterfaceElement],
                          rel_path: str) -> List[InterfaceDiff]:
        """Compare lists of interface elements."""
        diffs = []
        
        # Index by name
        baseline_map = {e.name: e for e in baseline_list}
        target_map = {e.name: e for e in target_list}
        
        all_names = set(baseline_map.keys()) | set(target_map.keys())
        
        for name in sorted(all_names):
            baseline_elem = baseline_map.get(name)
            target_elem = target_map.get(name)
            
            if not baseline_elem and target_elem:
                # New interface
                diff = self._create_added_diff(target_elem, rel_path)
                diffs.append(diff)
            
            elif baseline_elem and not target_elem:
                # Removed interface
                diff = self._create_removed_diff(baseline_elem, rel_path)
                diffs.append(diff)
            
            elif baseline_elem and target_elem:
                # Compare the two versions
                diff = self._compare_single_element(baseline_elem, target_elem, rel_path)
                if diff:
                    diffs.append(diff)
        
        return diffs
    
    def _create_added_diff(self, elem: InterfaceElement, rel_path: str) -> InterfaceDiff:
        """Create diff for a new interface."""
        return InterfaceDiff(
            element_name=elem.name,
            interface_type=elem.type,
            change_type=ChangeType.ADDED,
            severity=Severity.SAFE,
            file_path=rel_path,
            line_target=elem.line_number,
            target_element=elem,
            diff_summary=f"New {elem.type.value}: {elem.signature[:80]}",
            functional_area=self._detect_functional_area(elem.name, rel_path)
        )
    
    def _create_removed_diff(self, elem: InterfaceElement, rel_path: str) -> InterfaceDiff:
        """Create diff for a removed interface."""
        return InterfaceDiff(
            element_name=elem.name,
            interface_type=elem.type,
            change_type=ChangeType.REMOVED,
            severity=Severity.BREAKING,
            file_path=rel_path,
            line_baseline=elem.line_number,
            baseline_element=elem,
            diff_summary=f"Removed {elem.type.value}: {elem.signature[:80]}",
            diff_details=[f"⚠️ Any code using {elem.name} will fail to compile"],
            functional_area=self._detect_functional_area(elem.name, rel_path),
            impact_description=f"Breaking change - {elem.name} no longer exists"
        )
    
    def _compare_single_element(self, baseline: InterfaceElement,
                                target: InterfaceElement,
                                rel_path: str) -> Optional[InterfaceDiff]:
        """Compare two versions of the same interface element."""
        
        # Compare based on type
        if baseline.type == InterfaceType.FUNCTION:
            return self._compare_functions(baseline, target, rel_path)
        elif baseline.type == InterfaceType.STRUCT:
            return self._compare_structs(baseline, target, rel_path)
        elif baseline.type == InterfaceType.ENUM:
            return self._compare_enums(baseline, target, rel_path)
        elif baseline.type == InterfaceType.MACRO:
            return self._compare_macros(baseline, target, rel_path)
        elif baseline.type == InterfaceType.TYPEDEF:
            return self._compare_typedefs(baseline, target, rel_path)
        
        return None
    
    def _compare_functions(self, baseline: InterfaceElement,
                           target: InterfaceElement,
                           rel_path: str) -> Optional[InterfaceDiff]:
        """Compare two function declarations."""
        
        changes = []
        severity = Severity.SAFE
        
        # Compare return type
        if baseline.return_type != target.return_type:
            changes.append(f"Return type: {baseline.return_type} → {target.return_type}")
            severity = Severity.BREAKING
        
        # Compare parameters
        base_params = [(p.name, p.type) for p in baseline.parameters]
        target_params = [(p.name, p.type) for p in target.parameters]
        
        if len(base_params) != len(target_params):
            changes.append(f"Parameter count: {len(base_params)} → {len(target_params)}")
            severity = Severity.BREAKING
        else:
            for i, (bp, tp) in enumerate(zip(base_params, target_params)):
                if bp[1] != tp[1]:  # Type changed
                    changes.append(f"Param {i+1} type: {bp[1]} → {tp[1]}")
                    severity = Severity.BREAKING
                elif bp[0] != tp[0]:  # Only name changed
                    changes.append(f"Param {i+1} name: {bp[0]} → {tp[0]}")
                    if severity == Severity.SAFE:
                        severity = Severity.INFO
        
        # Compare static/inline qualifiers
        if baseline.is_static != target.is_static:
            changes.append(f"Static: {baseline.is_static} → {target.is_static}")
            severity = max(severity, Severity.REVIEW, key=lambda s: list(Severity).index(s))
        
        if not changes:
            return None
        
        return InterfaceDiff(
            element_name=baseline.name,
            interface_type=InterfaceType.FUNCTION,
            change_type=ChangeType.MODIFIED,
            severity=severity,
            file_path=rel_path,
            line_baseline=baseline.line_number,
            line_target=target.line_number,
            baseline_element=baseline,
            target_element=target,
            diff_summary=f"Signature changed: {', '.join(changes[:2])}",
            diff_details=changes,
            functional_area=self._detect_functional_area(baseline.name, rel_path)
        )
    
    def _compare_structs(self, baseline: InterfaceElement,
                         target: InterfaceElement,
                         rel_path: str) -> Optional[InterfaceDiff]:
        """Compare two struct definitions."""
        
        changes = []
        severity = Severity.SAFE
        
        base_fields = {f.name: f for f in baseline.fields}
        target_fields = {f.name: f for f in target.fields}
        
        # Check for removed fields
        for name in base_fields:
            if name not in target_fields:
                changes.append(f"Field removed: {base_fields[name]}")
                severity = Severity.BREAKING
        
        # Check for added fields
        for name in target_fields:
            if name not in base_fields:
                changes.append(f"Field added: {target_fields[name]}")
                if severity == Severity.SAFE:
                    severity = Severity.REVIEW
        
        # Check for modified fields
        for name in base_fields:
            if name in target_fields:
                bf = base_fields[name]
                tf = target_fields[name]
                if bf.type != tf.type:
                    changes.append(f"Field {name} type: {bf.type} → {tf.type}")
                    severity = Severity.BREAKING
                if bf.array_size != tf.array_size:
                    changes.append(f"Field {name} array size: {bf.array_size} → {tf.array_size}")
                    severity = Severity.BREAKING
        
        if not changes:
            return None
        
        return InterfaceDiff(
            element_name=baseline.name,
            interface_type=InterfaceType.STRUCT,
            change_type=ChangeType.MODIFIED,
            severity=severity,
            file_path=rel_path,
            line_baseline=baseline.line_number,
            line_target=target.line_number,
            baseline_element=baseline,
            target_element=target,
            diff_summary=f"Struct changed: {len(changes)} field(s) affected",
            diff_details=changes,
            functional_area=self._detect_functional_area(baseline.name, rel_path)
        )
    
    def _compare_enums(self, baseline: InterfaceElement,
                       target: InterfaceElement,
                       rel_path: str) -> Optional[InterfaceDiff]:
        """Compare two enum definitions."""
        
        changes = []
        severity = Severity.SAFE
        
        base_values = {v.name: v.value for v in baseline.values}
        target_values = {v.name: v.value for v in target.values}
        
        # Check for removed values
        for name in base_values:
            if name not in target_values:
                changes.append(f"Value removed: {name}")
                severity = Severity.BREAKING
        
        # Check for added values
        for name in target_values:
            if name not in base_values:
                changes.append(f"Value added: {name}")
                # Adding enum values is usually safe
        
        # Check for changed values
        for name in base_values:
            if name in target_values and base_values[name] != target_values[name]:
                changes.append(f"Value {name}: {base_values[name]} → {target_values[name]}")
                severity = Severity.BREAKING
        
        if not changes:
            return None
        
        return InterfaceDiff(
            element_name=baseline.name,
            interface_type=InterfaceType.ENUM,
            change_type=ChangeType.MODIFIED,
            severity=severity,
            file_path=rel_path,
            line_baseline=baseline.line_number,
            line_target=target.line_number,
            baseline_element=baseline,
            target_element=target,
            diff_summary=f"Enum changed: {len(changes)} value(s) affected",
            diff_details=changes,
            functional_area=self._detect_functional_area(baseline.name, rel_path)
        )
    
    def _compare_macros(self, baseline: InterfaceElement,
                        target: InterfaceElement,
                        rel_path: str) -> Optional[InterfaceDiff]:
        """Compare two macro definitions."""
        
        if baseline.macro_value == target.macro_value:
            return None
        
        return InterfaceDiff(
            element_name=baseline.name,
            interface_type=InterfaceType.MACRO,
            change_type=ChangeType.MODIFIED,
            severity=Severity.REVIEW,
            file_path=rel_path,
            line_baseline=baseline.line_number,
            line_target=target.line_number,
            baseline_element=baseline,
            target_element=target,
            diff_summary=f"Macro value changed",
            diff_details=[
                f"Old: {baseline.macro_value[:100]}",
                f"New: {target.macro_value[:100]}"
            ],
            functional_area=self._detect_functional_area(baseline.name, rel_path)
        )
    
    def _compare_typedefs(self, baseline: InterfaceElement,
                          target: InterfaceElement,
                          rel_path: str) -> Optional[InterfaceDiff]:
        """Compare two typedef declarations."""
        
        if baseline.typedef_target == target.typedef_target:
            return None
        
        return InterfaceDiff(
            element_name=baseline.name,
            interface_type=InterfaceType.TYPEDEF,
            change_type=ChangeType.MODIFIED,
            severity=Severity.BREAKING,
            file_path=rel_path,
            line_baseline=baseline.line_number,
            line_target=target.line_number,
            baseline_element=baseline,
            target_element=target,
            diff_summary=f"Typedef target changed",
            diff_details=[
                f"Old: typedef {baseline.typedef_target} {baseline.name}",
                f"New: typedef {target.typedef_target} {target.name}"
            ],
            functional_area=self._detect_functional_area(baseline.name, rel_path)
        )
    
    def _detect_functional_area(self, name: str, file_path: str) -> str:
        """Detect functional area from interface name or file path."""
        
        # Check name prefixes
        for area, patterns in self.FUNCTIONAL_PATTERNS.items():
            for pattern in patterns:
                if pattern in name:
                    return area
        
        # Check file path
        path_lower = file_path.lower()
        for area, patterns in self.FUNCTIONAL_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower().rstrip('_') in path_lower:
                    return area
        
        return "General"

    def _adjust_relative_paths(self, interfaces: Dict[str, FileInterfaces],
                              scope_path: str, root_path: str) -> Dict[str, FileInterfaces]:
        """Adjust relative paths from scope-relative to root-relative."""
        adjusted = {}

        for rel_path, file_interfaces in interfaces.items():
            # Calculate new relative path from root
            abs_path = os.path.join(scope_path, rel_path)
            new_rel_path = os.path.relpath(abs_path, root_path)

            # Update file_path in each interface element
            for interface in file_interfaces.all_elements():
                interface.file_path = os.path.join(root_path, new_rel_path)

            adjusted[new_rel_path] = file_interfaces

        return adjusted

    def _log_summary(self, result: BaselineDiff):
        """Log comparison summary."""
        logger.info("=" * 60)
        logger.info("INTERFACE COMPARISON SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Files: {result.total_files} total")
        logger.info(f"  Added:     {result.files_added}")
        logger.info(f"  Removed:   {result.files_removed}")
        logger.info(f"  Modified:  {result.files_modified}")
        logger.info(f"  Unchanged: {result.files_unchanged}")
        logger.info("")
        logger.info(f"Interface Changes: {result.total_interfaces}")
        logger.info(f"  🔴 Breaking: {result.breaking_changes}")
        logger.info(f"  🟡 Review:   {result.review_needed}")
        logger.info(f"  🟢 Safe:     {result.safe_changes}")
        logger.info("")
        logger.info("By Functional Area:")
        for area, diffs in sorted(result.by_functional_area.items()):
            breaking = sum(1 for d in diffs if d.severity == Severity.BREAKING)
            logger.info(f"  {area}: {len(diffs)} changes ({breaking} breaking)")
        logger.info("=" * 60)


# Convenience function
def compare_interfaces(baseline_path: str, target_path: str,
                       ignore_patterns: List[str] = None) -> BaselineDiff:
    """
    Compare interfaces between two baselines.
    
    Args:
        baseline_path: Path to baseline folder (Stream 1)
        target_path: Path to target folder (Stream 2)
        ignore_patterns: Patterns for files to ignore
        
    Returns:
        BaselineDiff with all differences
    """
    engine = InterfaceDiffEngine(ignore_patterns=ignore_patterns)
    return engine.compare_baselines(baseline_path, target_path)
