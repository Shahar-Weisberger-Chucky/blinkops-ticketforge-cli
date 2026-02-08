# TicketForge CLI – BlinkOps Take Home Assignment

This project is a command-line application for managing TicketForge work items (tickets).

The TicketForge system does not provide public API documentation.
All API endpoints, request parameters, and payload formats were discovered manually
by inspecting network requests made by the provided web application.

The focus of this solution is correctness, robustness, and a clear user-friendly CLI experience.

## Features

- Setup command to configure access credentials
- List tickets with cursor-based pagination
- Create new tickets from the CLI
- Update existing tickets safely without breaking required fields
- Basic rate-limit handling for HTTP 429 responses
- Clear and readable CLI output

## Requirements

- Python 3.10 or newer
- Tested with Python 3.12

## Installation

Create a virtual environment:

```bash
python -m venv .venv
```

Activate the virtual environment:
Windows:

```bash
.venv\Scripts\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Setup

```bash
python src/main.py setup
```

This command stores credentials locally in a config.json file which is ignored by git.

### List tickets

```bash
python src/main.py list --limit 5
python src/main.py list --all --limit 2
```

### Show a ticket (detail)

```bash
python src/main.py show TF-160
```

### Create a ticket

```bash
python src/main.py create \
  --title "My ticket" \
  --description "Created via CLI" \
  --depends-on TF-160,TF-158
```

### Update a ticket

Update title:

```bash
python src/main.py update TF-160 --title "Updated title"
```

Update stage:

```bash
python src/main.py update TF-160 --stage review
```

Update custom fields:

```bash
python src/main.py update TF-160 --custom-fields j9=hello
```

## Notes and Assumptions

- Authentication uses HTTP Basic Authentication
- Update operations use a fetch-merge-put approach to avoid clearing required fields
- Pagination is implemented using the `nextCursor` value returned by the API
- Valid ticket stages are: open, in_progress, review, closed

## Evidence

Screenshots demonstrating successful execution of setup, list, create, and update
commands are provided in the `evidence` directory.

## AI Disclosure

I used ChatGPT to help plan the overall approach, validate edge cases, and refine error handling and CLI structure.

All reverse engineering was done by me: I inspected the TicketForge web app network requests, inferred the API endpoints and payloads, and manually tested the integration end to end (create, list with pagination, and update) from the CLI.
