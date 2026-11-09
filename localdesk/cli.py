"""Command-line interface."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .agent import Agent
from .automation import Desktop
from .config import Settings
from .console import configure_console
from .errors import LocalDeskError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="localdesk",
        description="Request approval-based mouse and keyboard plans from a local multimodal model.",
    )
    parser.add_argument("goal", nargs="?", help="Task to run; omit it to start interactive mode")
    parser.add_argument("--version", action="version", version=f"localdesk {__version__}")
    parser.add_argument("--yes", action="store_true", help="Skip approval; the plan still passes validation")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan without sending input")
    parser.add_argument("--show-config", action="store_true", help="Show the effective configuration summary")
    return parser


def main() -> int:
    configure_console()
    args = build_parser().parse_args()
    try:
        settings = Settings.from_env()
        if args.show_config:
            print(f"API: {settings.base_url}\nModel: {settings.model}\nStep limit: {settings.max_steps}")
            return 0
        if args.dry_run and args.yes:
            raise LocalDeskError("--dry-run and --yes cannot be used together.")
        desktop = Desktop()
        agent = Agent(settings, desktop)
        if args.goal:
            _run_goal(args.goal, agent, args)
            return 0
        print("LocalDesk interactive mode. Type /quit to exit.")
        print("Each task is shown as a plan and requires separate approval.")
        while True:
            try:
                goal = input("\nTask> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting.")
                break
            if goal.lower() in {"/quit", "/exit", "quit", "exit"}:
                break
            if not goal:
                continue
            try:
                _run_goal(goal, agent, args)
            except LocalDeskError as exc:
                print(f"Error: {exc}", file=sys.stderr)
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except LocalDeskError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


def _run_goal(goal: str, agent: Agent, args) -> None:
    if args.dry_run:
        plan = agent.propose(goal)
        print(f"\nPlan: {plan.summary}")
        for index, action in enumerate(plan.steps, 1):
            from .automation import describe_action
            print(f"  {index}. {describe_action(action)}")
        print("Dry run: no input was sent.")
    else:
        agent.run(goal, lambda: True if args.yes else _confirm())


def _confirm() -> bool:
    try:
        return input("Execute this plan? [y/N] ").strip().lower() in {"y", "yes"}
    except (EOFError, KeyboardInterrupt):
        print("\nApproval cancelled.")
        return False


if __name__ == "__main__":
    raise SystemExit(main())
