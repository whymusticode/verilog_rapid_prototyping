# Extraction prompts

The `py2v extract` command runs three separate API calls. Each call gets the
PDF as a `document` content block and a tightly scoped instruction.

## A. Verbatim Python extraction

> You are extracting source code from a technical document. Locate every Python
> code block in the attached PDF (formatted code, listings, appendices, inline
> snippets). Concatenate them in document order into a single Python module.
>
> Rules:
>   - Preserve identifiers, indentation, comments, and ordering exactly as in
>     the document. Do not "fix" obvious bugs.
>   - If multiple unrelated programs appear, separate them with a comment line
>     `# --- next snippet (page <N>) ---`.
>   - If a snippet looks truncated or unreadable, insert a comment
>     `# TODO: extraction-uncertain (page <N>): <one-line reason>` and emit the
>     best-effort transcription.
>   - Do not add any imports, helper functions, or wrappers that are not in the
>     document.
>   - Output ONLY the Python source — no markdown fences, no commentary.

## B. Bug review (read-only)

> You are reviewing the attached PDF's Python reference for likely numerical or
> algorithmic issues. Do NOT modify the code. Output a Markdown bullet list,
> one issue per bullet, in the form:
>
>     - **<short title>** (`<file>:<line range>`): <what's wrong>; <suggested fix or check>
>
> If the document is internally consistent and no issues are found, output a
> single line: `No issues found.`

## C. py2c.yaml fill (existing)

The original `get_params` prompt — see `py2v/skeletons/py2c.yaml` for the
schema the model fills in.
