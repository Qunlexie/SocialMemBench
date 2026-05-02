"""SocialMemBench CLI — run the full pipeline from the terminal via `smb`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

# Project root — always run claude subprocess from here so relative paths work
PROJECT_ROOT = Path(__file__).parents[2]
COMMANDS_DIR = PROJECT_ROOT / ".claude" / "commands"
MANIFEST_PATH = PROJECT_ROOT / "data" / "manifest.json"

VALID_TIERS = ["small", "medium", "large"]
VALID_GROUP_TYPES = [
    "close_friends", "family", "recreational",
    "interest_community", "acquaintance_network",
]


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def run_skill(skill_name: str, args: str = "") -> int:
    """Load a skill markdown, substitute $ARGUMENTS, run via `claude -p`.

    Always runs with cwd=PROJECT_ROOT so data/ paths resolve correctly.
    Returns the subprocess exit code (does NOT call sys.exit).
    """
    skill_file = COMMANDS_DIR / f"{skill_name}.md"
    if not skill_file.exists():
        click.echo(f"Error: skill file not found: {skill_file}", err=True)
        return 1

    prompt = skill_file.read_text(encoding="utf-8").replace("$ARGUMENTS", args)

    try:
        result = subprocess.run(["claude", "-p", prompt], cwd=PROJECT_ROOT)
        return result.returncode
    except FileNotFoundError:
        click.echo(
            "Error: `claude` CLI not found in PATH. "
            "Install Claude Code and ensure `claude` is accessible.",
            err=True,
        )
        return 1


def _load_manifest():
    """Load manifest, returning None if it doesn't exist yet."""
    from socialmembench.utils.manifest import DatasetManifest
    if not MANIFEST_PATH.exists():
        return None
    return DatasetManifest.load(MANIFEST_PATH)


def _network_ids_in_manifest() -> set[str]:
    m = _load_manifest()
    return set(m.networks.keys()) if m else set()


def _tier_args(tier: str, group_type: str, group_size: int | None) -> str:
    """Build $ARGUMENTS string for smb-generate-network from tier config."""
    from socialmembench.config import TIER_CONFIG
    cfg = TIER_CONFIG[tier]
    size = group_size or cfg["group_size_default"]
    return (
        f"{group_type} {size} "
        f"--sessions {cfg['sessions']} "
        f"--turns-per-session {cfg['turns_per_session']} "
        f"--departures {cfg['departures']}"
    ).strip()


def _step(label: str) -> None:
    click.echo(f"\n{click.style('→', fg='cyan', bold=True)} {label}")


def _ok(label: str) -> None:
    click.echo(f"  {click.style('✓', fg='green', bold=True)} {label}")


def _fail(label: str) -> None:
    click.echo(f"  {click.style('✗', fg='red', bold=True)} {label}", err=True)


def _run_stage(label: str, skill: str, args: str) -> bool:
    """Run one stage, print result. Returns True on success."""
    _step(label)
    rc = run_skill(skill, args)
    if rc == 0:
        _ok(f"{label} complete")
        return True
    else:
        _fail(f"{label} failed (exit {rc})")
        return False


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """SocialMemBench pipeline CLI.

    All LLM stages delegate to `claude -p` (Claude Code headless).
    Status, metrics, and scale planning are pure Python.

    \b
    Single network:
      smb pipeline --tier medium --group-type recreational

    \b
    Scale to a target:
      smb scale --target-qa 200
      smb scale --milestone tier-validation

    \b
    Step by step:
      smb generate-network --tier medium --group-type recreational
      smb generate-conversations grp_<id>
      smb generate-qa grp_<id>
      smb verify grp_<id>
      smb qc grp_<id>
    """
    pass


# ---------------------------------------------------------------------------
# Individual stage commands
# ---------------------------------------------------------------------------

@cli.command("generate-network")
@click.option("--tier", default="small", type=click.Choice(VALID_TIERS), show_default=True,
              help="Size tier — drives group size, sessions, and departures from TIER_CONFIG.")
@click.option("--group-type", default=None,
              help="Group type. Omit to auto-select (most underrepresented in manifest).")
@click.option("--group-size", default=None, type=int,
              help="Override group size (default: tier's group_size_default).")
def generate_network(tier: str, group_type: str | None, group_size: int | None) -> None:
    """Generate a new ego network (Stage 1).

    All generation parameters (sessions, departures, size) derive from --tier.
    """
    from socialmembench.config import TIER_GROUP_TYPES
    if group_type is None:
        # Auto-select from manifest
        m = _load_manifest()
        counts = m.group_type_counts if m else {}
        valid = TIER_GROUP_TYPES[tier]
        group_type = min(valid, key=lambda t: counts.get(t, 0))
        click.echo(f"Auto-selected group type: {group_type}")

    args = _tier_args(tier, group_type, group_size)
    sys.exit(run_skill("smb-generate-network", args))


@cli.command("generate-conversations")
@click.argument("network_id")
@click.option("--skip-if-done", is_flag=True, help="Skip if conversations already exist.")
def generate_conversations(network_id: str, skip_if_done: bool) -> None:
    """Generate conversation corpus for a network (Stage 2).

    Session count is read from the network JSON (set during generate-network).
    """
    if skip_if_done:
        if (PROJECT_ROOT / "data" / "conversations" / f"{network_id}.json").exists():
            click.echo(f"Skipping {network_id}: conversations already exist")
            return
    sys.exit(run_skill("smb-generate-conversations", network_id))


@cli.command("generate-qa")
@click.argument("network_id")
@click.argument("query_types", nargs=-1, metavar="[Q1 Q2 ...]")
@click.option("--skip-if-done", is_flag=True, help="Skip if QA already exists.")
def generate_qa(network_id: str, query_types: tuple[str, ...], skip_if_done: bool) -> None:
    """Generate QA pairs for a network (Stage 3).

    Optionally restrict to specific query types:

    \b
      smb generate-qa grp_abc123 Q1 Q4 Q8
    """
    if skip_if_done:
        qa_file = PROJECT_ROOT / "data" / "qa" / f"{network_id}.jsonl"
        if qa_file.exists() and qa_file.stat().st_size > 0:
            click.echo(f"Skipping {network_id}: QA already exists")
            return
    args = " ".join([network_id] + list(query_types))
    sys.exit(run_skill("smb-generate-qa", args))


@cli.command("verify")
@click.argument("network_id")
@click.option("--stage", default=None, type=click.Choice(["1", "2", "3"]),
              help="Check only one stage (default: all).")
def verify(network_id: str, stage: str | None) -> None:
    """Run structural verification checks."""
    args = network_id + (f" --stage {stage}" if stage else "")
    sys.exit(run_skill("smb-verify", args))


@cli.command("qc")
@click.argument("network_id")
def qc(network_id: str) -> None:
    """Run blind-critic QC on QA pairs for a network."""
    sys.exit(run_skill("smb-qc", network_id))


# ---------------------------------------------------------------------------
# Pure Python commands (no LLM)
# ---------------------------------------------------------------------------

@cli.command("status")
@click.argument("network_id", required=False, default=None)
def status(network_id: str | None) -> None:
    """Show dataset status (reads manifest directly — no LLM needed)."""
    from socialmembench.config import TIER_CONFIG
    m = _load_manifest()
    if m is None:
        click.echo("No manifest found. Run `smb generate-network` to start.")
        return

    if network_id:
        if network_id not in m.networks:
            click.echo(f"Network {network_id} not found in manifest.", err=True)
            return
        net = m.networks[network_id]
        click.echo(f"\nNetwork: {network_id}")
        click.echo(f"  Tier:       {net.tier}  |  Group type: {net.group_type}  |  Size: {net.group_size}")
        click.echo(f"  Status:     {net.status}")
        click.echo(f"  Sessions:   {net.n_sessions} / {TIER_CONFIG[net.tier]['sessions']}")
        click.echo(f"  QA pairs:   {net.n_qa} / ~{TIER_CONFIG[net.tier]['qa_yield_estimate']} expected")
        click.echo(f"  Departures: {TIER_CONFIG[net.tier]['departures']} configured")
        click.echo(f"  Challenges: {len(net.consumed_challenge_ids)}")
        click.echo("\n  Files:")
        for label, path in [
            ("raw network",    PROJECT_ROOT / "data" / "raw" / f"{network_id}.json"),
            ("conversations",  PROJECT_ROOT / "data" / "conversations" / f"{network_id}.json"),
            ("QA pairs",       PROJECT_ROOT / "data" / "qa" / f"{network_id}.jsonl"),
            ("QC report",      PROJECT_ROOT / "data" / "qa" / f"{network_id}_qc.json"),
            ("oracle results", PROJECT_ROOT / "data" / "results" / "oracle" / f"{network_id}_summary.json"),
        ]:
            exists = click.style("✓", fg="green") if path.exists() else click.style("✗", fg="red")
            click.echo(f"    {exists}  {label}: {path.relative_to(PROJECT_ROOT)}")
        return

    # Summary view
    status_counts: dict[str, int] = {}
    for net in m.networks.values():
        status_counts[net.status] = status_counts.get(net.status, 0) + 1

    click.echo(f"\n{'='*44}")
    click.echo("SocialMemBench Dataset Status")
    click.echo(f"{'='*44}")
    click.echo(f"Networks:  {len(m.networks)}   QA pairs: {m.qa_pairs_total}   Next seed: {m.next_seed}")
    click.echo("")
    for s, n in sorted(status_counts.items()):
        click.echo(f"  {s:<20} {n}")

    click.echo("\nTier distribution:")
    for tier in VALID_TIERS:
        cnt = m.size_tier_counts.get(tier, 0)
        bar = "█" * cnt
        click.echo(f"  {tier:<10} {cnt:>3}  {bar}")

    click.echo("\nQuery type distribution:")
    for qt, count in sorted(m.query_type_counts.items()):
        bar = "█" * count
        click.echo(f"  {qt}  {count:>3}  {bar}")

    click.echo("\nGroup type distribution:")
    for gt, count in sorted(m.group_type_counts.items()):
        click.echo(f"  {gt:<25} {count}")

    click.echo("\nNetworks:")
    for nid, net in m.networks.items():
        status_color = "green" if net.status == "verified" else "yellow"
        s = click.style(f"{net.status:<12}", fg=status_color)
        click.echo(
            f"  {nid}  {net.tier:<8} {net.group_type:<25} "
            f"size={net.group_size}  {s}  qa={net.n_qa}"
        )


@cli.command("metrics")
@click.option("--data-dir", default=None, help="Path to data dir (default: project data/).")
def metrics(data_dir: str | None) -> None:
    """Print dataset quality metrics (pure Python, no LLM required)."""
    from socialmembench.utils.metrics import print_metrics
    print_metrics(data_dir or str(PROJECT_ROOT / "data"))


@cli.command("plan")
@click.option("--target-qa", default=None, type=int, help="Target total QA pairs.")
@click.option("--milestone", default=None, help="Named milestone (e.g. tier-validation).")
@click.option("--tiers", default=None, help="Comma-separated tiers to use (e.g. medium,large).")
def plan(target_qa: int | None, milestone: str | None, tiers: str | None) -> None:
    """Show what would be generated without running anything.

    \b
    Examples:
      smb plan --target-qa 200
      smb plan --milestone tier-validation
      smb plan --target-qa 800 --tiers medium,large
    """
    from socialmembench.pipeline.planner import plan_milestone, plan_to_target, summarize_plan
    m = _load_manifest()
    if m is None:
        click.echo("No manifest found. Run `smb generate-network` first.")
        return

    tier_filter = [t.strip() for t in tiers.split(",")] if tiers else None

    if milestone:
        tasks = plan_milestone(milestone, m)
    elif target_qa:
        tasks = plan_to_target(target_qa, m, preferred_tiers=tier_filter)
    else:
        click.echo("Provide --target-qa or --milestone. Run `smb plan --help`.")
        return

    click.echo(summarize_plan(tasks, m.qa_pairs_total))


# ---------------------------------------------------------------------------
# Orchestration commands
# ---------------------------------------------------------------------------

def _run_pipeline_for(
    network_id: str,
    skip_verify: bool = False,
) -> bool:
    """Run generate-conversations → [verify] → generate-qa → [verify] → qc.

    Returns True on success. Assumes stage 1 (network) is already done.
    """
    # Stage 2
    if not _run_stage("Stage 2: generate-conversations", "smb-generate-conversations", network_id):
        return False

    if not skip_verify:
        if not _run_stage("Verify: stage 2", "smb-verify", f"{network_id} --stage 2"):
            _fail("Stage 2 verification failed. Fix conversations before generating QA.")
            return False

    # Stage 3
    if not _run_stage("Stage 3: generate-qa", "smb-generate-qa", network_id):
        return False

    if not skip_verify:
        if not _run_stage("Verify: stage 3", "smb-verify", f"{network_id} --stage 3"):
            _fail("Stage 3 verification failed. Fix QA pairs before running QC.")
            return False

    # QC
    if not _run_stage("QC: blind critic", "smb-qc", network_id):
        return False

    return True


@cli.command("pipeline")
@click.option("--tier", default="small", type=click.Choice(VALID_TIERS), show_default=True,
              help="Tier to generate — drives size, sessions, and departures from TIER_CONFIG.")
@click.option("--group-type", default=None,
              help="Group type. Omit to auto-select from manifest.")
@click.option("--group-size", default=None, type=int,
              help="Override group size (default: tier's group_size_default).")
@click.option("--skip-verify", is_flag=True, help="Skip verify gates between stages.")
def pipeline(tier: str, group_type: str | None, group_size: int | None, skip_verify: bool) -> None:
    """Run the full pipeline for one new network.

    \b
    Stages (with review loops built in):
      generate-network → generate-conversations → verify(2) →
      generate-qa → verify(3) → qc

    All generation parameters come from --tier via TIER_CONFIG.
    """
    from socialmembench.config import TIER_GROUP_TYPES
    click.echo(click.style(f"\n=== SMB Pipeline [{tier} tier] ===", bold=True))

    if group_type is None:
        m = _load_manifest()
        counts = m.group_type_counts if m else {}
        valid = TIER_GROUP_TYPES[tier]
        group_type = min(valid, key=lambda t: counts.get(t, 0))
        click.echo(f"Auto-selected group type: {group_type}")

    # Stage 1
    before_ids = _network_ids_in_manifest()
    args = _tier_args(tier, group_type, group_size)
    if not _run_stage("Stage 1: generate-network", "smb-generate-network", args):
        sys.exit(1)

    after_ids = _network_ids_in_manifest()
    new_ids = after_ids - before_ids
    if not new_ids:
        _fail("Could not determine new network_id from manifest — aborting.")
        sys.exit(1)
    network_id = sorted(new_ids)[0]
    click.echo(f"  Network: {click.style(network_id, bold=True)}")

    if not _run_pipeline_for(network_id, skip_verify=skip_verify):
        sys.exit(1)

    click.echo(click.style(f"\n✓ Pipeline complete: {network_id}", fg="green", bold=True))
    click.echo(f"  Run `smb status {network_id}` for details.")


@cli.command("scale")
@click.option("--target-qa", default=None, type=int,
              help="Target total QA pairs across all networks.")
@click.option("--milestone", default=None,
              help="Named milestone: tier-validation, first-scale, full-dataset, longitudinal.")
@click.option("--tiers", default=None,
              help="Comma-separated tiers to restrict generation (e.g. medium,large).")
@click.option("--skip-verify", is_flag=True, help="Skip verify gates (faster, less safe).")
@click.option("--dry-run", is_flag=True, help="Show plan without running anything.")
@click.option("--stop-on-failure/--no-stop-on-failure", default=True, show_default=True,
              help="Abort batch if any network fails.")
def scale(
    target_qa: int | None,
    milestone: str | None,
    tiers: str | None,
    skip_verify: bool,
    dry_run: bool,
    stop_on_failure: bool,
) -> None:
    """Generate networks until reaching a QA target or milestone.

    The system computes the mix of tiers and group types automatically,
    balancing against what's already in the manifest.

    \b
    Examples:
      smb scale --target-qa 200
      smb scale --milestone tier-validation
      smb scale --target-qa 800 --tiers medium,large
      smb scale --target-qa 200 --dry-run    # preview only
    """
    from socialmembench.pipeline.planner import (
        plan_milestone, plan_to_target, summarize_plan,
    )

    if not target_qa and not milestone:
        click.echo("Error: provide --target-qa or --milestone.", err=True)
        sys.exit(1)

    m = _load_manifest()
    if m is None:
        from socialmembench.utils.manifest import DatasetManifest
        m = DatasetManifest()

    tier_filter = [t.strip() for t in tiers.split(",")] if tiers else None

    if milestone:
        tasks = plan_milestone(milestone, m)
    else:
        tasks = plan_to_target(target_qa, m, preferred_tiers=tier_filter)

    click.echo("\n" + summarize_plan(tasks, m.qa_pairs_total))

    if dry_run or not tasks:
        return

    click.echo("")
    results: list[dict] = []

    for i, task in enumerate(tasks, 1):
        click.echo(click.style(f"\n{'='*52}", bold=True))
        click.echo(click.style(f"  Task {i}/{len(tasks)}: {task.tier} / {task.group_type}", bold=True))
        click.echo(click.style(f"{'='*52}", bold=True))

        before_ids = _network_ids_in_manifest()

        rc = run_skill("smb-generate-network", task.skill_args())
        if rc != 0:
            _fail(f"generate-network failed for task {i}")
            results.append({"task": i, "network_id": None, "success": False, "failed_at": "stage1"})
            if stop_on_failure:
                break
            continue

        after_ids = _network_ids_in_manifest()
        new_ids = after_ids - before_ids
        if not new_ids:
            _fail(f"Could not determine network_id for task {i}")
            results.append({"task": i, "network_id": None, "success": False, "failed_at": "stage1"})
            if stop_on_failure:
                break
            continue

        network_id = sorted(new_ids)[0]
        click.echo(f"  {click.style('→', fg='cyan')} Network: {network_id}")

        if _run_pipeline_for(network_id, skip_verify=skip_verify):
            _ok(f"Task {i} ({network_id}): complete")
            results.append({"task": i, "network_id": network_id, "success": True})
        else:
            results.append({"task": i, "network_id": network_id, "success": False, "failed_at": "pipeline"})
            if stop_on_failure:
                break

    # Summary
    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    click.echo(click.style(f"\n{'='*52}", bold=True))
    click.echo(click.style(f"Scale complete: {len(successes)}/{len(results)} networks generated", bold=True))
    if successes:
        click.echo(click.style("  Generated:", fg="green"))
        for r in successes:
            click.echo(f"    {r['network_id']}")
    if failures:
        click.echo(click.style("  Failed:", fg="red"))
        for r in failures:
            click.echo(f"    {r.get('network_id') or '(unknown)'}  at: {r.get('failed_at', '?')}")

    sys.exit(0 if not failures else 1)


@cli.command("evaluate")
@click.argument("network_id", required=False, default=None)
@click.option("--condition", default="oracle", type=click.Choice(["oracle"]), show_default=True,
              help="Evaluation condition.")
@click.option("--all", "all_networks", is_flag=True,
              help="Run on all networks with status 'verified' or 'complete'.")
def evaluate(network_id: str | None, condition: str, all_networks: bool) -> None:
    """Run evaluation against QA pairs (Stage 4).

    \b
    Oracle condition (Condition A) — full conversation as context:
      smb evaluate grp_<id>
      smb evaluate --all
    """
    skill = f"smb-evaluate-{condition}"

    if all_networks:
        m = _load_manifest()
        if m is None:
            click.echo("No manifest found.", err=True)
            sys.exit(1)
        eligible = [
            nid for nid, net in m.networks.items()
            if net.status in ("verified", "complete", "stage3_done")
        ]
        if not eligible:
            click.echo("No eligible networks found (need status verified/complete/stage3_done).")
            return
        click.echo(f"Evaluating {len(eligible)} network(s) under condition: {condition}\n")
        failed = []
        for nid in eligible:
            click.echo(click.style(f"--- {nid} ---", bold=True))
            rc = run_skill(skill, nid)
            if rc != 0:
                _fail(f"{nid}: evaluation failed")
                failed.append(nid)
        if failed:
            click.echo(click.style(f"\nFailed: {', '.join(failed)}", fg="red"))
            sys.exit(1)
    elif network_id:
        sys.exit(run_skill(skill, network_id))
    else:
        click.echo("Provide a network_id or --all.", err=True)
        sys.exit(1)


@cli.command("batch")
@click.option("--count", default=1, type=int, show_default=True)
@click.option("--tier", default="small", type=click.Choice(VALID_TIERS), show_default=True)
@click.option("--group-type", default=None)
@click.option("--group-size", default=None, type=int)
@click.option("--skip-verify", is_flag=True)
@click.option("--stop-on-failure/--no-stop-on-failure", default=True, show_default=True)
def batch(
    count: int,
    tier: str,
    group_type: str | None,
    group_size: int | None,
    skip_verify: bool,
    stop_on_failure: bool,
) -> None:
    """Run the full pipeline N times with the same tier settings.

    For mixed-tier generation, use `smb scale` instead.

    \b
    Example:
      smb batch --count 3 --tier medium --group-type recreational
    """
    from socialmembench.config import TIER_GROUP_TYPES

    results: list[dict] = []

    for i in range(count):
        click.echo(click.style(f"\n{'='*52}", bold=True))
        click.echo(click.style(f"  Network {i + 1}/{count} [{tier} tier]", bold=True))
        click.echo(click.style(f"{'='*52}", bold=True))

        _group_type = group_type
        if _group_type is None:
            m = _load_manifest()
            counts = m.group_type_counts if m else {}
            valid = TIER_GROUP_TYPES[tier]
            _group_type = min(valid, key=lambda t: counts.get(t, 0))
            click.echo(f"  Auto-selected group type: {_group_type}")

        before_ids = _network_ids_in_manifest()
        args = _tier_args(tier, _group_type, group_size)
        rc = run_skill("smb-generate-network", args)
        if rc != 0:
            _fail(f"Network {i + 1}: generate-network failed")
            results.append({"index": i + 1, "network_id": None, "success": False, "failed_at": "stage1"})
            if stop_on_failure:
                break
            continue

        after_ids = _network_ids_in_manifest()
        new_ids = after_ids - before_ids
        if not new_ids:
            _fail(f"Network {i + 1}: could not determine network_id")
            results.append({"index": i + 1, "network_id": None, "success": False, "failed_at": "stage1"})
            if stop_on_failure:
                break
            continue

        network_id = sorted(new_ids)[0]
        click.echo(f"  {click.style('→', fg='cyan')} Network: {network_id}")

        if _run_pipeline_for(network_id, skip_verify=skip_verify):
            _ok(f"Network {i + 1} ({network_id}): complete")
            results.append({"index": i + 1, "network_id": network_id, "success": True})
        else:
            results.append({"index": i + 1, "network_id": network_id, "success": False, "failed_at": "pipeline"})
            if stop_on_failure:
                break

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    click.echo(click.style(f"\nBatch complete: {len(successes)}/{len(results)} networks", bold=True))
    if failures:
        for r in failures:
            click.echo(f"  failed: {r.get('network_id') or '(unknown)'}  at: {r.get('failed_at', '?')}", err=True)

    sys.exit(0 if not failures else 1)
