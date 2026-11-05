"""Meeting Copilot cloud assistant and retrieval synthesis."""

from .assistant import CopilotResult, MeetingAssistant
from .client import ClaudeClient, ClaudeClientError, ClaudeUsage
from .parser import extract_citations, parse_copilot_response
from .prompts import SYSTEM_PROMPT, build_user_prompt

