"""Validate experiment requests before creating files or spending tokens."""
from pathlib import Path


def validate_request(n_papers, reps, out_dir, model_names, only_models=None):
    if n_papers < 1 or reps < 1:
        raise ValueError("Paper and replicate counts must be positive.")
    if only_models is not None:
        if not only_models or len(set(only_models)) != len(only_models):
            raise ValueError("Select at least one model without duplicates.")
        unknown = set(only_models) - set(model_names)
        if unknown:
            raise ValueError(f"Unknown models: {', '.join(sorted(unknown))}")
    if Path(out_dir).exists():
        raise FileExistsError("Choose a new output directory; existing runs are never overwritten.")


def validate_papers(papers):
    required = {"id", "lw_id", "title", "url", "author", "content"}
    if not isinstance(papers, list) or not papers:
        raise ValueError("A stimulus file must contain a nonempty list of papers.")
    for paper in papers:
        if not isinstance(paper, dict) or not required.issubset(paper):
            raise ValueError("Each paper needs id, lw_id, title, url, author, and content.")
        if not all(isinstance(paper[key], str) and paper[key].strip() for key in ("title", "url")):
            raise ValueError("Paper titles and URLs must be nonempty strings.")
        if any(paper[key] is not None and not isinstance(paper[key], str) for key in ("author", "content")):
            raise ValueError("Paper author and content must be strings or null.")
    return papers
