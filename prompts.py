"""Tutor prompts and starter questions."""

from __future__ import annotations

LEVELS = ["Beginner", "Intermediate", "Advanced"]

STARTERS = {
    "Beginner": [
        "What's the difference between a list and a tuple?",
        "Explain for-loops with a simple example",
        "Why do I need to indent my code?",
    ],
    "Intermediate": [
        "How do list comprehensions actually work?",
        "Debug my BeautifulSoup scraper's rate limiting",
        "When should I use a class vs. a plain function?",
    ],
    "Advanced": [
        "Walk me through Python's GIL and threading",
        "How do generators and yield actually work under the hood?",
        "Best practices for structuring a data pipeline package",
    ],
}

CONTINUE_PROMPT = (
    "Continue exactly where you left off. Do not repeat any text you already wrote."
)


def build_system_prompt(level: str) -> str:
    base = (
        "You are a patient, precise Python tutor running inside an interactive REPL-style "
        "teaching console. Teach by explaining the 'why', not just the 'how'. Always include "
        "a short, runnable code example when a concept benefits from one, formatted in a "
        "fenced code block with the python language tag. Ask a small follow-up question or "
        "suggest a next step at the end of your answer to keep the lesson moving. Keep answers "
        "focused \u2014 prefer one clear example over several. When the learner shares code with "
        "an error, diagnose it directly before explaining the underlying concept."
    )
    notes = {
        "Beginner": (
            "The learner is new to Python. Avoid jargon unless you define it immediately. Use "
            "everyday analogies. Keep code examples under 8 lines."
        ),
        "Intermediate": (
            "The learner is comfortable with core syntax (loops, functions, basic data "
            "structures) and has built small real projects, including a BeautifulSoup-based web "
            "scraper. Skip basic definitions. Favor practical, slightly-real-world examples "
            "(automation, working with APIs/data) over toy examples. It's fine to introduce "
            "idiomatic patterns (comprehensions, context managers, decorators) when relevant."
        ),
        "Advanced": (
            "The learner wants depth: internals, performance trade-offs, and idiomatic/"
            "production-grade patterns. Don't oversimplify. Reference relevant standard-library "
            "or ecosystem tools by name."
        ),
    }
    return f"{base}\n\n{notes.get(level, notes['Intermediate'])}"
