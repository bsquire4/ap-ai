"""OpenAI integration for weekly roundup + context + notepad in one response."""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import OpenAI

from response_model import OpenAIResponse, WeeklyAnalysis

load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")


def _get_client() -> OpenAI:
    """Create OpenAI client lazily so import doesn't fail when env is not loaded yet."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your environment or .env file."
        )
    return OpenAI(api_key=api_key)


def _read_file_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_markdown(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_json(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Treat missing/empty JSON files as "no data yet".
    if not raw.strip():
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in '{path}': {exc}") from exc


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=_json_default)


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _json_default(value: Any) -> Any:
    """JSON serializer for non-serializable runtime values."""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _merge_notepads(existing: Optional[List[Dict]], incoming: List[Dict]) -> List[Dict]:
    """Merge notepad entries, deduplicate by id and content."""
    existing = existing or []
    seen_ids = {n.get("id") for n in existing if n.get("id")}
    seen_contents = {n.get("content") for n in existing if n.get("content")}

    out = list(existing)
    for n in incoming:
        nid = n.get("id") or str(uuid.uuid4())
        if nid in seen_ids:
            continue
        content = n.get("content", "")
        if content and content in seen_contents:
            continue
        note = dict(n)
        note.setdefault("id", nid)
        out.append(note)
        seen_ids.add(nid)
        if content:
            seen_contents.add(content)

    return out


def _model_to_dict(model_obj: Any) -> Dict[str, Any]:
    """Support both Pydantic v1 and v2 model dumping."""
    if hasattr(model_obj, "model_dump"):
        # mode='json' converts datetimes and similar values to JSON-safe types.
        return model_obj.model_dump(mode="json")
    return json.loads(model_obj.json())


def handle_response(
    resp: OpenAIResponse,
    context_path: str,
    notepad_path: str,
) -> Dict[str, str]:
    """Write each response section to the proper destination file(s)."""
    results: Dict[str, str] = {}

    _write_text(context_path, resp.context or "")
    results["context"] = context_path

    existing_notes = _read_json(notepad_path) or []
    incoming_notes = [_model_to_dict(n) for n in resp.notepad]
    merged_notes = _merge_notepads(existing_notes, incoming_notes)
    _write_json(notepad_path, merged_notes)
    results["notepad"] = notepad_path

def handle_roundup(
    roundup: WeeklyAnalysis
):
    """Parse the reposne into a format ready to be written to attackpoint"""
    return(f"""
           <b>Summary</b>
            {roundup.executive_summary}
            <b>Physiological Markers</b>
            {roundup.physiological_markers}
            <b>Recovery Correlation</b>
            {roundup.recovery_correlation}
            <b>Actionable Adjustments</b>
            <ul>
            {''.join(f'<li>{adj}</li>' for adj in roundup.actionable_adjustments)}
            </ul>
            Provided by ap-ai
           """)


def send_training_to_openai(
    training_input: str,
    model: str = DEFAULT_MODEL,
) -> str:
    """Send training data + context + notepad and return structured response + write results."""
    training_text = _read_file_text(training_input) if os.path.exists(training_input) else training_input
    
    context_path = os.path.join(os.getcwd(), "model_notepad/context.md")
    context_text = _read_markdown(context_path)
    notepad_path = os.path.join(os.getcwd(), "model_notepad/notepad.json")
    notepad_json = _read_json(notepad_path) or []

    system = ("""
            You are an elite sports performance coach, physiologist and data analyst, specializing in endurance sports like running and cycling. You have decades of experience working with athletes of all levels, from beginners to world champions, and you are an expert at analyzing training.
            You have access to the athlete's training data, including workouts, metrics, and historical context. Your task is to analyze this information and produce three outputs:
            1. A concise weekly roundup summarizing the athlete's training, progress, and any notable insights. This should be informative, accurate and actionable for the athlete. Focussing on areas that the athlete may have missed during the week and providing insights that they may not have been aware of.
            2. Context markdown that can be iterated on over time. Keep it simple and useful, capturing broad training context that helps future analysis rounds.
            3. Persistent notepad entries that should be stored for long-term tracking of the athlete's training history. These should include any important notes, observations, or patterns that could be useful for future reference and pattern discovery.
            
            Ensure any suggestions or insights are grounded in the training data and context provided. 
            Do not just repeat the training data back in the roundup - provide analysis and insights that are not immediately obvious.
            Over time, using the notepad, focus on identifying patterns and trends in the athlete's training, such as how they respond to different types of workouts, how their performance changes over time, and any correlations between training variables and outcomes.
            Analyze the relationship between training load (volume/intensity) and recovery metrics (HRV/Sleep).
            Identify long term trends in the athlete's performance and training history, such as improvements in key metrics, changes in fitness levels, or emerging patterns that could inform future training decisions.
            
            Base all your analysis on the context provided, and do not make assumptions beyond the data. 
            Keep the roundup concise and un-verbose, focusing on the most important insights and actionable advice for the athlete.
            
            If you have nothing to comment on in a section, return an empty string or empty list for that section. Do not fabricate insights or notes that are not supported by the data.
            Do not assume any data that is not explicitly provided in the training data or context. If certain information is missing, simply omit insights related to that information rather than making assumptions.
            
            You must return exactly one JSON object matching the OpenAIResponse schema. Include all three sections in the same response: weekly_roundup, context, and notepad. Do not return markdown or explanatory text.
        """
    )
    user = {
        "training_data": training_text[:20000],
        "context": context_text,
        "notepad": notepad_json,
        "instructions": (
            "Analyse the training data and produce a concise weekly_roundup, a simple markdown context document for next round, and notepad entries that should persist for pattern tracking."
        ),
    }
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]

    completion = _get_client().chat.completions.parse(
        model=model,
        messages=messages,
        response_format=OpenAIResponse,
    )

    message = completion.choices[0].message
    parsed = message.parsed
    if parsed is None:
        refusal = getattr(message, "refusal", None)
        raise RuntimeError(f"Model did not return a valid structured response. Refusal: {refusal}")

    handle_response(parsed, context_path=context_path, notepad_path=notepad_path)
    
    return handle_roundup(parsed.weekly_roundup)