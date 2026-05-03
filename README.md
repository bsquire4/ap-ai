# ap-ai

`ap-ai` pulls the last 7 days of training data from AttackPoint, sends that data to OpenAI for analysis, and posts a formatted weekly roundup back to AttackPoint as a training note. It also maintains a small local memory layer in `model_notepad/` so each run can build on prior context.

## What It Does

The main workflow in `main.py` is:

1. Log into AttackPoint and export the last 7 days of completed training.
2. Parse the export into a cleaned pandas DataFrame.
3. Send that training data, plus the current `model_notepad/context.md` and `model_notepad/notepad.json`, to OpenAI.
4. Receive a structured response containing:
   - a weekly training analysis
   - refreshed rolling context
   - persistent note entries
5. Save the updated context/notepad locally.
6. Post the weekly roundup back to AttackPoint as a note.

## Requirements

- Python 3.10+
- Google Chrome installed locally
- An AttackPoint account
- An OpenAI API key

## Installation

Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project root with the following values:

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-5.4
ATTACKPOINT_USERNAME=your_attackpoint_username
ATTACKPOINT_PASSWORD=your_attackpoint_password
```

Notes:

- `OPENAI_MODEL` is optional. If omitted, the code defaults to `gpt-5.4`.

## Usage

Run the full weekly workflow with:

```powershell
python main.py
```

On a successful run, the project will:

- fetch the past week of completed training from AttackPoint
- update `model_notepad/context.md`
- merge new long-term notes into `model_notepad/notepad.json`
- submit the generated roundup to AttackPoint as a note

## Project Structure

```text
ap-ai/
|-- main.py
|-- attackpoint_client.py
|-- openai_client.py
|-- response_model.py
|-- utils.py
|-- requirements.txt
`-- model_notepad/
    |-- context.md
    `-- notepad.json
```

## File Overview

- `main.py`: orchestration entry point for the full workflow.
- `attackpoint_client.py`: Selenium-based AttackPoint login, report export, parsing, and note submission.
- `openai_client.py`: OpenAI request/response handling, local context persistence, and roundup formatting.
- `response_model.py`: Pydantic models for the structured OpenAI response.
- `model_notepad/context.md`: rolling markdown context carried from one run to the next.
- `model_notepad/notepad.json`: persistent note store used for longer-term pattern tracking.

## How Persistence Works

The project keeps a lightweight memory layer under `model_notepad/`:

- `context.md` is overwritten each run with the latest context returned by the model.
- `notepad.json` is merged with new notes, deduplicating by note id and content where possible.

This lets the OpenAI analysis stay aware of broader training history instead of treating each week as isolated.

## Notes and Limitations

- The AttackPoint integration depends on the current site structure. If the login or report pages change, the Selenium selectors may need to be updated.
- The browser automation expects Chrome to be available.
- The OpenAI request only sends the first 20,000 characters of serialized training data.
- There are no automated tests in the repository yet.

## Example Run Flow

```text
AttackPoint -> training export -> pandas cleanup -> OpenAI structured analysis
          -> update context/notepad -> format HTML note -> post back to AttackPoint
```