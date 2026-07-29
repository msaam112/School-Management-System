"""Shared AI helper — thin wrapper around the AI provider used by every
AI feature (result card remarks, notices, parent Q&A, admin assistant).

Currently backed by Google Gemini's free tier. Every other module calls
only generate_text() below, so the underlying provider can be swapped
later (e.g. back to Anthropic) without touching any feature code.
"""
import os
import google.generativeai as genai

_configured = False

MODEL = "gemini-flash-latest"

def _ensure_configured():
    global _configured
    if not _configured:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Set it as an environment variable "
                "before using any AI feature."
            )
        genai.configure(api_key=api_key)
        _configured = True


def generate_text(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """Single-turn text generation: system instructions + one user message,
    returns plain text. Used by result-card remarks, notice drafting, etc."""
    _ensure_configured()
    model = genai.GenerativeModel(MODEL, system_instruction=system_prompt)
    response = model.generate_content(
        user_prompt,
        generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens),
    )
    return (response.text or "").strip()

def generate_result_remark(student_name: str, exam_name: str, subject_rows: list, overall_percentage: float, overall_result: str) -> str:
    """Generates a short, personalized teacher-style remark for a result card."""
    subjects_summary = "\n".join(
        f"- {r['subject']}: {r['obtained']}/{r['total']} ({r['percentage']:.1f}%, {r['grade']}, {r['pass_fail']})"
        for r in subject_rows
    )
    system_prompt = (
        "You are an experienced, encouraging school teacher writing a brief remark "
        "for a student's result card. Write 2-3 sentences, warm but honest, "
        "highlighting a specific strength and one area to improve. "
        "Do not use markdown formatting. Do not repeat the raw numbers verbatim; "
        "speak about performance qualitatively."
    )
    user_prompt = (
        f"Student: {student_name}\n"
        f"Examination: {exam_name}\n"
        f"Overall: {overall_percentage:.1f}% ({overall_result})\n"
        f"Subject breakdown:\n{subjects_summary}\n\n"
        f"Write the remark now."
    )
    return generate_text(system_prompt, user_prompt, max_tokens=800)