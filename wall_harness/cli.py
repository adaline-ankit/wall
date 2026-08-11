from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from .pipeline import WallPipeline
from .spec import load_spec

app = typer.Typer(no_args_is_help=True, help="Subscribe to intent, not feeds.")


@app.command()
def init(
    destination: Annotated[Path, typer.Argument(help="Where to create your WallSpec")] = Path(
        "wall.yaml"
    ),
    example: Annotated[
        str, typer.Option(help="Bundled example: frontier-ai or distributed-systems")
    ] = "frontier-ai",
) -> None:
    """Create a WallSpec from a bundled example."""
    source = Path(__file__).parent / "examples" / f"{example}.yaml"
    if not source.exists():
        raise typer.BadParameter(f"Unknown example {example!r}")
    if destination.exists():
        raise typer.BadParameter(f"{destination} already exists")
    shutil.copyfile(source, destination)
    typer.echo(f"Created {destination}. Edit it, then run: wall run {destination}")


@app.command()
def validate(spec_path: Annotated[Path, typer.Argument(help="Path to a WallSpec YAML")]) -> None:
    """Validate a WallSpec without fetching anything."""
    try:
        spec = load_spec(spec_path)
    except (OSError, ValueError, ValidationError) as exc:
        typer.echo(f"Invalid WallSpec: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"Valid WallSpec: {spec.name} ({len(spec.sources)} sources, {len(spec.topics)} topics)"
    )


@app.command()
def run(
    spec_path: Annotated[Path, typer.Argument(help="Path to a WallSpec YAML")],
    no_llm: Annotated[
        bool, typer.Option("--no-llm", help="Skip analysis even when configured")
    ] = False,
    dry_run: Annotated[bool, typer.Option(help="Discover and rank without writing output")] = False,
) -> None:
    """Discover, cluster, rank, analyze, and render one Wall edition."""
    spec = load_spec(spec_path)
    pipeline = WallPipeline(spec)
    with typer.progressbar(length=1, label="Building your wall") as progress:
        edition = pipeline.run(use_llm=not no_llm)
        progress.update(1)
    if dry_run:
        typer.echo(f"Selected {len(edition.items)} of {edition.discovered_count} discovered items")
        return
    paths = pipeline.write(edition)
    pipeline.deliver(edition)
    typer.echo(f"Built {len(edition.items)}-item wall: {', '.join(str(path) for path in paths)}")
    for receipt in edition.delivery_receipts:
        typer.echo(
            f"Delivery {receipt.target}: {receipt.status}{f' ({receipt.detail})' if receipt.detail else ''}"
        )


@app.command()
def serve(
    spec_path: Annotated[Path, typer.Argument(help="Path to a WallSpec YAML or directory")],
    host: Annotated[
        str, typer.Option(help="Interface to bind; local-only by default")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Local dashboard port", min=1, max=65535)] = 8765,
) -> None:
    """Open the interactive local Wall dashboard."""
    import uvicorn

    from .web import create_app

    if spec_path.is_file():
        load_spec(spec_path)
    typer.echo(f"Wall is ready at http://{host}:{port}")
    uvicorn.run(create_app(spec_path), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    app()
