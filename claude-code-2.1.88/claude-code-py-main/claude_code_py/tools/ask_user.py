"""AskUserQuestion tool."""

from __future__ import annotations

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult


class AskUserTool(BaseTool):
    name = "AskUserQuestion"
    description = "Ask the user a question with optional choices."
    input_schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "description": "Questions to ask",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                            },
                        },
                    },
                    "required": ["question"],
                },
            },
        },
        "required": ["questions"],
    }

    def is_read_only(self, args: dict) -> bool:
        return True

    def render_tool_use(self, args: dict) -> str:
        questions = args.get("questions", [])
        if questions:
            return questions[0].get("question", "")[:100]
        return "Asking user..."

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        questions = args.get("questions", [])
        answers = {}

        for q in questions:
            question_text = q.get("question", "")
            options = q.get("options", [])

            print(f"\n  ❓ {question_text}")
            if options:
                for i, opt in enumerate(options, 1):
                    label = opt.get("label", "")
                    desc = opt.get("description", "")
                    print(f"    {i}. {label}" + (f" — {desc}" if desc else ""))
                print(f"    {len(options) + 1}. Other (type your answer)")

            try:
                answer = input("  Your answer: ").strip()
                # If numeric and matches an option
                if options and answer.isdigit():
                    idx = int(answer) - 1
                    if 0 <= idx < len(options):
                        answer = options[idx].get("label", answer)
                answers[question_text] = answer
            except (EOFError, KeyboardInterrupt):
                answers[question_text] = "(no answer)"

        return ToolResult(output="\n".join(f"Q: {k}\nA: {v}" for k, v in answers.items()))
