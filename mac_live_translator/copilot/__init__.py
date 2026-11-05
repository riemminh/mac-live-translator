"""Meeting Copilot cloud assistant and retrieval synthesis."""

from .assistant import MeetingAssistant
from .client import ClaudeClient, ClaudeClientError, ClaudeUsage
from .models import CopilotResult, PreparedCopilotRequest
from .parser import extract_citations, parse_copilot_response
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .streaming import StreamingSectionParser
