"""OpenAI GPT integration for AI suggestions"""

import os
from src.config import settings


def ai_suggest_changes(file1_content, file2_content, file_name):
    """
    Use OpenAI GPT to suggest purpose of changes between two files.
    Returns AI-generated suggestion or None if not available.
    
    Args:
        file1_content: Content from platform/baseline file
        file2_content: Content from project file
        file_name: Name of the file being analyzed
    
    Returns:
        str: AI suggestion or None
    """
    # NOTE: This is a placeholder - Actual implementation should use OpenAI API
    # Refer to the original test.py for the complete AI integration logic
    print(f"ai_suggest_changes for {file_name} - TODO: Implement OpenAI API integration")
    
    if not settings.OPENAI_API_KEY:
        print("OpenAI API key not configured")
        return None
    
    # TODO: Implement actual OpenAI API call here
    # 1. Prepare prompt with file differences
    # 2. Make API call to OpenAI GPT-4o-mini
    # 3. Parse and return the AI suggestion
    
    return None
