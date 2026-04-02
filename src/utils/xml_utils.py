"""XML utility functions for Migration Analysis Tool"""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from .file_utils import read_file_as_text


def normalize_xml(file_path):
    """Parse and normalize XML for comparison"""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        # Pretty print XML for better comparison
        xml_str = ET.tostring(root, encoding='unicode')
        dom = minidom.parseString(xml_str)
        return dom.toprettyxml(indent="  ").splitlines(keepends=True)
    except Exception as e:
        # If XML parsing fails, treat as regular text file
        return read_file_as_text(file_path)
