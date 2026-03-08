"""
CLI entry point for confab_test.

Usage examples:
  python -m confab_test --model qwen3.5 --category all
  python -m confab_test --model deepseek-r1:8b --category tool_fabrication
  python -m confab_test --model mistral --category links,citations
  python -m confab_test --compare qwen3.5 deepseek-r1:8b mistral
  python -m confab_test --list-models
  python -m confab_test --list-categories
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console

from confab_test.config import load_config
from confab_test.tests import CATEGORY_MAP

console = Console()

_CATEGORY_ALIASES = {
    "tool": "tool_fabrication",
    "links": "link_verification",
    "link": "link_verification",
    "temporal": "temporal_consistency",
    "time": "temporal_consistency",
    "citations": "citation_fabrication",
    "citation": "citation_fabrication",
    "self": "self_knowledge",
    "capabilities": "self_knowledge",
    "correction": "correction_persistence",
    "contrition": "correction_persistence",
    "numbers": "number_fabrication",
    "number": "number_fabrication",
}


def _resolve_categories(cat_str: str) -> list[str]:
    if cat_str.lower() in ("all", ""):
        return list(CATEGORY_MAP.keys())
    parts = [p.strip().lower() for p in cat_str.split(",")]
    resolved = []
    for p in parts:
        full = _CATEGORY_ALIASES.get(p, p)
        if full not in CATEGORY_MAP:
            console.print(
                f"[yellow]Unknown category '{p}' — skipping. "
                f"Valid: {', '.join(CATEGORY_MAP)}[/yellow]"
            )
        else:
            resolved.append(full)
    return resolved


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--model", "-m", default=None, help="Ollama model name (e.g. qwen3.5)")
@click.option(
    "--category", "-c", default="all",
    help="Category or comma-separated list. Use 'all' for full suite.",
)
@click.option("--config", default=None, help="Path to config.yaml")
@click.option("--verbose", "-v", is_flag=True, help="Show full responses during run")
@click.option("--no-report", is_flag=True, help="Skip writing the Markdown report")
@click.option("--json", "write_json", is_flag=True, help="Also write a JSON report")
def main(ctx, model, category, config, verbose, no_report, write_json):
    """Automated confabulation test suite for local LLMs via Ollama."""
    if ctx.invoked_subcommand is not None:
        return

    cfg = load_config(config)
    if model:
        cfg["ollama"]["default_model"] = model

    categories = _resolve_categories(category)
    if not categories:
        console.print("[red]No valid categories selected. Exiting.[/red]")
        sys.exit(1)

    asyncio.run(_run(cfg, model, categories, verbose, no_report, write_json))


async def _run(cfg, model, categories, verbose, no_report, write_json):
    from confab_test.runner import run_suite
    from confab_test.report import generate_report, generate_json_report

    try:
        summary = await run_suite(cfg, model=model, categories=categories, verbose=verbose)
    except ConnectionError as e:
        console.print(f"[bold red]{e}[/bold red]")
        sys.exit(1)

    output_dir = cfg.get("reporting", {}).get("output_dir", "~/confab_test/reports")

    if not no_report:
        report_path = generate_report(summary, output_dir)
        console.print(f"[bold green]Report saved:[/bold green] {report_path}")

    if write_json:
        json_path = generate_json_report(summary, output_dir)
        console.print(f"[bold green]JSON saved:[/bold green] {json_path}")


@main.command("list-models")
@click.option("--config", default=None)
def list_models(config):
    """List models available in Ollama."""
    cfg = load_config(config)
    asyncio.run(_list_models(cfg))


async def _list_models(cfg):
    from confab_test.ollama_client import OllamaClient
    base_url = cfg["ollama"]["base_url"]
    client = OllamaClient(base_url, "")
    if not await client.ping():
        console.print(f"[red]Cannot reach Ollama at {base_url}[/red]")
        return
    models = await client.list_models()
    console.print("[bold]Available models:[/bold]")
    for m in models:
        console.print(f"  {m}")


@main.command("list-categories")
def list_categories():
    """List available test categories."""
    console.print("[bold]Available categories:[/bold]")
    for cat in CATEGORY_MAP:
        console.print(f"  [cyan]{cat}[/cyan]")
    console.print("\n[bold]Aliases:[/bold]")
    for alias, full in _CATEGORY_ALIASES.items():
        console.print(f"  {alias:20s} → {full}")


@main.command("compare")
@click.argument("models", nargs=-1, required=True)
@click.option("--category", "-c", default="all")
@click.option("--config", default=None)
@click.option("--verbose", "-v", is_flag=True)
def compare(models, category, config, verbose):
    """Run the test suite against multiple models and compare results."""
    cfg = load_config(config)
    categories = _resolve_categories(category)
    asyncio.run(_compare(cfg, list(models), categories, verbose))


async def _compare(cfg, models, categories, verbose):
    from confab_test.runner import run_suite, console as rconsole
    from confab_test.report import generate_report
    from rich.table import Table

    output_dir = cfg.get("reporting", {}).get("output_dir", "~/confab_test/reports")
    summaries = []

    for model in models:
        console.print(f"\n{'='*60}")
        console.print(f"[bold]Testing model:[/bold] [cyan]{model}[/cyan]")
        console.print(f"{'='*60}")
        try:
            summary = await run_suite(cfg, model=model, categories=categories, verbose=verbose)
            summaries.append(summary)
            generate_report(summary, output_dir)
        except Exception as e:
            console.print(f"[red]Error testing {model}: {e}[/red]")

    if len(summaries) < 2:
        return

    # Comparison table
    table = Table(title="Model Comparison", show_lines=True)
    table.add_column("Category", style="bold")
    for s in summaries:
        table.add_column(s.model, justify="right")

    all_cats = categories
    for cat in all_cats:
        row = [cat]
        for s in summaries:
            sc = s.category_scores().get(cat, {})
            score = sc.get("score", 0)
            color = "green" if score >= 70 else ("yellow" if score >= 40 else "red")
            row.append(f"[{color}]{score:.0f}%[/{color}]")
        table.add_row(*row)

    overall_row = ["[bold]OVERALL[/bold]"]
    for s in summaries:
        o = s.overall_score()
        color = "green" if o >= 70 else ("yellow" if o >= 40 else "red")
        overall_row.append(f"[bold {color}]{o:.0f}%[/bold {color}]")
    table.add_row(*overall_row)

    console.print()
    console.print(table)


@main.command("history")
@click.option("--config", default=None)
@click.option("--limit", default=10)
def history(config, limit):
    """Show recent test runs from the database."""
    from confab_test import db as database
    from rich.table import Table

    cfg = load_config(config)
    db_path = cfg["logging"]["db_path"]
    runs = database.load_all_runs(db_path)[:limit]

    if not runs:
        console.print("[dim]No runs found.[/dim]")
        return

    table = Table(title="Recent Runs")
    table.add_column("ID")
    table.add_column("Model")
    table.add_column("Started")
    table.add_column("Finished")

    for r in runs:
        table.add_row(
            str(r["id"]),
            r["model"],
            r["started_at"],
            r["finished_at"] or "[dim]running[/dim]",
        )
    console.print(table)


if __name__ == "__main__":
    main()
