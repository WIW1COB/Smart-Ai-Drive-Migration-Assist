"""AI Integration Package - Azure OpenAI Smart Merge + OpenAI GPT (optional)"""

from .azure_openai_farm import ai_merge_with_azure_openai
from .ai_suggest import ai_analyze_file

__all__ = ['ai_merge_with_azure_openai', 'ai_analyze_file']
