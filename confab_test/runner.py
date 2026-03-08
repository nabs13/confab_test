"""
Core test runner — orchestrates test modules, logs to SQLite, drives the UI.
"""
from __future__ import annotations

import asyncio
import importlib
import time
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from confab_test import db as database
from confab_test.ollama_client import OllamaClient
from confab_test.tests import CATEGORY_MAP, TestResult, Verdict

console = Console()

_VERDICT_STYLE = {
    Verdict.PASS: "bold green",
    Verdict.FAIL: "bold red",
    Verdict.UNCERTAIN: "bold yellow",
    Verdict.ERROR: "bold magenta",
}
_VERDICT_ICON = {
    Verdict.PASS: "✓",
    Verdict.FAIL: "✗",
    Verdict.UNCERTAIN: "?",
    Verdict.ERROR: "!",
}


@dataclass
class RunSummary:
    model: str
    categories: list[str]
    results: list[TestResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    @property
    def duration(self) -> float:
        return self.finished_at - self.started_at

    def category_scores(self) -> dict[str, dict]:
        scores: dict[str, dict] = {}
        for cat in self.categories:
            cat_results = [r for r in self.results if r.category == cat]
            if not cat_results:
                continue
            passed = sum(1 for r in cat_results if r.verdict == Verdict.PASS)
            failed = sum(1 for r in cat_results if r.verdict == Verdict.FAIL)
            uncertain = sum(1 for r in cat_results if r.verdict == Verdict.UNCERTAIN)
            errors = sum(1 for r in cat_results if r.verdict == Verdict.ERROR)
            total = len(cat_results)
            scores[cat] = {
                "total": total,
                "passed": passed,
                "failed": failed,
                "uncertain": uncertain,
                "errors": errors,
                "score": (passed / total * 100) if total else 0,
            }
        return scores

    def overall_score(self) -> float:
        cats = self.category_scores()
        if not cats:
            return 0.0
        return sum(v["score"] for v in cats.values()) / len(cats)


async def run_suite(
    config: dict,
    model: str | None = None,
    categories: list[str] | None = None,
    verbose: bool = False,
) -> RunSummary:
    """Run the test suite and return a RunSummary."""
    ollama_cfg = config.get("ollama", {})
    model = model or ollama_cfg.get("default_model", "qwen3.5")
    base_url = ollama_cfg.get("base_url", "http://127.0.0.1:11434")
    timeout = ollama_cfg.get("timeout", 120)

    all_categories = config.get("tests", {}).get("categories", list(CATEGORY_MAP.keys()))
    categories = categories or all_categories
    # Filter to valid categories only
    categories = [c for c in categories if c in CATEGORY_MAP]

    db_path = config.get("logging", {}).get("db_path", "~/confab_test/confab_results.db")

    # --- Verify Ollama is up ---
    client = OllamaClient(base_url, model, timeout)
    console.print(f"\n[bold]Connecting to Ollama[/bold] at [cyan]{base_url}[/cyan] …")
    if not await client.ping():
        console.print(
            f"[bold red]ERROR:[/bold red] Cannot reach Ollama at {base_url}\n"
            "Make sure Ollama is running: [dim]ollama serve[/dim]"
        )
        raise ConnectionError(f"Cannot reach Ollama at {base_url}")

    available = await client.list_models()
    console.print(f"  Available models: [dim]{', '.join(available) or 'none'}[/dim]")

    short_names = [m.split(":")[0] for m in available]
    model_base = model.split(":")[0]
    if model not in available and model_base not in short_names:
        console.print(
            f"[bold yellow]WARNING:[/bold yellow] Model [cyan]{model}[/cyan] "
            f"not found in Ollama. Tests may fail."
        )
    else:
        console.print(f"  Using model: [bold cyan]{model}[/bold cyan]")

    # --- DB setup ---
    database.init_db(db_path)
    run_id = database.create_run(db_path, model, config)
    console.print(f"  Logging to: [dim]{db_path}[/dim] (run_id={run_id})\n")

    summary = RunSummary(model=model, categories=categories)

    # --- Progress display ---
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    total_cases_estimate = len(categories) * 5  # rough estimate
    overall_task = progress.add_task(
        "[bold white]Overall progress", total=len(categories)
    )

    with progress:
        for cat in categories:
            progress.update(overall_task, description=f"[bold white]Running: {cat}")

            # Load module
            module_path = CATEGORY_MAP[cat]
            try:
                mod = importlib.import_module(module_path)
            except ImportError as e:
                console.print(f"[red]Cannot load {module_path}: {e}[/red]")
                progress.advance(overall_task)
                continue

            # Find the test class (first class that ends with "Tests")
            test_cls = None
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and name.endswith("Tests") and name != "BaseTestModule":
                    test_cls = obj
                    break

            if test_cls is None:
                console.print(f"[red]No test class found in {module_path}[/red]")
                progress.advance(overall_task)
                continue

            test_module = test_cls(client, config)
            cat_task = progress.add_task(f"  [cyan]{cat}", total=None)

            try:
                cat_results = await test_module.run_all()
            except Exception as exc:
                console.print(f"[red]Error running {cat}: {exc}[/red]")
                cat_results = []

            progress.remove_task(cat_task)

            for result in cat_results:
                database.save_result(db_path, run_id, result)
                summary.results.append(result)

                icon = _VERDICT_ICON[result.verdict]
                style = _VERDICT_STYLE[result.verdict]
                line = (
                    f"  [{style}]{icon} {result.verdict:10s}[/{style}] "
                    f"[dim]{cat}[/dim] / {result.test_name}"
                )
                if verbose:
                    line += f"\n    [dim]Reason: {result.reason}[/dim]"
                progress.console.print(line)

                if verbose and result.responses:
                    snippet = result.responses[-1][:200].replace("\n", " ")
                    progress.console.print(
                        f"    [dim italic]Response: {snippet}…[/dim italic]"
                    )

            progress.advance(overall_task)

    summary.finished_at = time.time()
    database.finish_run(db_path, run_id)

    _print_summary(summary)
    return summary


def _print_summary(summary: RunSummary) -> None:
    scores = summary.category_scores()
    overall = summary.overall_score()

    table = Table(title=f"Results for [cyan]{summary.model}[/cyan]", show_lines=True)
    table.add_column("Category", style="bold")
    table.add_column("Tests", justify="right")
    table.add_column("Pass", style="green", justify="right")
    table.add_column("Fail", style="red", justify="right")
    table.add_column("?", style="yellow", justify="right")
    table.add_column("Err", style="magenta", justify="right")
    table.add_column("Score", justify="right")

    for cat, s in scores.items():
        score_pct = f"{s['score']:.0f}%"
        style = "green" if s["score"] >= 70 else ("yellow" if s["score"] >= 40 else "red")
        table.add_row(
            cat,
            str(s["total"]),
            str(s["passed"]),
            str(s["failed"]),
            str(s["uncertain"]),
            str(s["errors"]),
            f"[{style}]{score_pct}[/{style}]",
        )

    overall_style = "green" if overall >= 70 else ("yellow" if overall >= 40 else "red")
    table.add_row(
        "[bold]OVERALL[/bold]",
        str(len(summary.results)),
        "",
        "",
        "",
        "",
        f"[bold {overall_style}]{overall:.0f}%[/bold {overall_style}]",
    )

    console.print()
    console.print(table)
    console.print(
        f"\n[dim]Duration: {summary.duration:.1f}s[/dim]\n"
    )
