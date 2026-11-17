#!/usr/bin/env python3
"""
build_regs.py - Generate register HTML documentation for pinned Caliptra 2.1 sources

Reads the "2.1" refs of caliptra-rtl and caliptra-ss from
src/data/caliptra-docs.json, shallow-clones each ref with submodules, runs the
repository's register generator, and stages the HTML under:

    <output>/regs/caliptra-rtl/2.1/internal-regs/
    <output>/regs/caliptra-rtl/2.1/external-regs/
    <output>/regs/caliptra-ss/2.1/regs/

Usage:
    python build_regs.py [--output DIR] [--work DIR] [--verbose]

Requirements:
    - git, bash, python3
    - peakrdl packages from tools/requirements-build_regs.txt
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

VERSION = "2.1"

REPO_ROOT = Path(__file__).resolve().parent.parent
CALIPTRA_DOCS_JSON_PATH = REPO_ROOT / "src" / "data" / "caliptra-docs.json"

# Per-repo generator invocation, mirroring each repository's doc-gen workflow
# at the 2.1 tags. "outputs" maps checkout-relative HTML dirs to site dirs.
REG_REPOS: dict[str, dict] = {
    "caliptra-rtl": {
        "command": ["bash", "tools/scripts/reg_doc_gen.sh"],
        "env": {"ADAMSBRIDGE_ROOT": "./submodules/adams-bridge"},
        "outputs": {
            "src/integration/docs/caliptra_reg_html": "internal-regs",
            "src/soc_ifc/docs/caliptra_top_reg_html": "external-regs",
        },
    },
    "caliptra-ss": {
        "command": ["bash", "tools/scripts/gen_soc_regs.sh"],
        "env": {"CALIPTRA_SS_ROOT": "{checkout}"},
        "outputs": {
            "src/integration/docs/soc_address_map_html": "regs",
        },
    },
}

logger = logging.getLogger("build_regs")


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def load_repo_refs() -> dict[str, tuple[str, str]]:
    """Return {repo_key: (clone_url, ref)} for VERSION from caliptra-docs.json."""
    data = json.loads(CALIPTRA_DOCS_JSON_PATH.read_text())
    repos = data.get("repositories", {})
    refs = {}
    for key in REG_REPOS:
        info = repos[key]
        ref = info.get("versions", {}).get(VERSION)
        if not ref:
            raise SystemExit(f"{key} has no ref for version {VERSION}")
        refs[key] = (f"https://github.com/{info['github']}.git", ref)
    return refs


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    logger.debug(f"$ {' '.join(cmd)} (cwd={cwd})")
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def clone(url: str, ref: str, dest: Path) -> None:
    run(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            ref,
            "--recurse-submodules",
            "--shallow-submodules",
            url,
            str(dest),
        ]
    )


def generate(key: str, checkout: Path) -> None:
    spec = REG_REPOS[key]
    env = dict(os.environ)
    for name, value in spec["env"].items():
        env[name] = value.format(checkout=checkout)
    run(spec["command"], cwd=checkout, env=env)


def stage(key: str, checkout: Path, output: Path) -> None:
    spec = REG_REPOS[key]
    for src_rel, dest_name in spec["outputs"].items():
        src = checkout / src_rel
        if not src.is_dir():
            raise RuntimeError(f"{key}: generator did not produce {src_rel}")
        if not (src / "index.html").is_file():
            raise RuntimeError(f"{key}: missing index.html in {src_rel}")
        dest = output / "regs" / key / VERSION / dest_name
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        logger.info(f"  Staged {dest.relative_to(output)}")


def build_repo(key: str, url: str, ref: str, work: Path, output: Path) -> None:
    checkout = work / key
    if checkout.exists():
        shutil.rmtree(checkout)

    start = time.monotonic()
    logger.info(f"{key} {VERSION}: cloning {url} @ {ref}")
    clone(url, ref, checkout)
    logger.info(f"  cloned in {time.monotonic() - start:.1f}s")

    start = time.monotonic()
    logger.info("  generating registers")
    generate(key, checkout)
    logger.info(f"  generated in {time.monotonic() - start:.1f}s")

    stage(key, checkout, output)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Caliptra 2.1 register HTML documentation",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("regs-build"),
        help="Output directory; receives regs/ (default: regs-build/)",
    )
    parser.add_argument(
        "--work",
        type=Path,
        default=None,
        help="Work directory for clones (default: temporary directory)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    setup_logging(args.verbose)

    refs = load_repo_refs()
    output = args.output.resolve()
    if (output / "regs").exists():
        shutil.rmtree(output / "regs")
    output.mkdir(parents=True, exist_ok=True)

    def build_all(work: Path) -> None:
        work.mkdir(parents=True, exist_ok=True)
        for key, (url, ref) in refs.items():
            build_repo(key, url, ref, work, output)

    if args.work:
        build_all(args.work.resolve())
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            build_all(Path(tmpdir))

    logger.info("Register documentation build complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
