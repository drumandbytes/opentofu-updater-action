#!/usr/bin/env python3
"""Update OpenTofu/Terraform provider, Helm chart, module, and container image versions in .tf files."""

from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import yaml
from packaging.version import Version

REPO_ROOT = Path(".").resolve()
VERSIONS_FILE = REPO_ROOT / os.environ.get("VERSIONS_FILE", "versions.tf")

IGNORE = {s.strip() for s in os.environ.get("IGNORE", "").split(",") if s.strip()}
SKIP_PROVIDERS = os.environ.get("SKIP_PROVIDERS", "false").lower() == "true"
SKIP_HELM = os.environ.get("SKIP_HELM", "false").lower() == "true"
SKIP_MODULES = os.environ.get("SKIP_MODULES", "false").lower() == "true"
SKIP_IMAGES = os.environ.get("SKIP_IMAGES", "false").lower() == "true"
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"

DOCKERHUB_USERNAME = os.environ.get("DOCKERHUB_USERNAME", "")
DOCKERHUB_TOKEN = os.environ.get("DOCKERHUB_TOKEN", "")
GHCR_TOKEN = os.environ.get("GHCR_TOKEN", "")

TIMEOUT = aiohttp.ClientTimeout(total=20)

# Tags that look like versions but are not pinnable releases
_UNSTABLE_TAG_RE = re.compile(
    r"(latest|stable|main|master|edge|canary|nightly|dev|snapshot|alpha|beta|rc\d*|next|test)",
    re.IGNORECASE,
)


# ── Version utilities ─────────────────────────────────────────────────────────


def is_stable(v: str) -> bool:
    try:
        return not Version(v.lstrip("v")).is_prerelease
    except Exception:
        return False


def norm(v: str) -> Version:
    return Version(v.lstrip("v"))


def is_version_tag(tag: str) -> bool:
    """True if the tag looks like a pinnable release version."""
    if _UNSTABLE_TAG_RE.search(tag):
        return False
    return bool(re.search(r"\d", tag))


# ── Constraint logic ──────────────────────────────────────────────────────────


def new_constraint(current: str, latest: str) -> tuple[str | None, bool]:
    """
    Returns (new_constraint_string | None, needs_manual_review).

    ~> X.Y   — allow minor bumps within major; flag cross-major.
    ~> X.Y.Z — allow patch bumps; flag cross-minor.
    Exact pin — bump directly to latest if newer.
    """
    latest_v = norm(latest)

    if current.startswith("~>"):
        parts = current[2:].strip().split(".")
        cur_major = int(parts[0])

        if latest_v.major > cur_major:
            return None, True

        if len(parts) == 2:
            cur_minor = int(parts[1])
            if latest_v.minor > cur_minor:
                return f"~> {latest_v.major}.{latest_v.minor}", False
            return None, False

        cur_minor = int(parts[1])
        if latest_v.minor > cur_minor:
            return f"~> {latest_v.major}.{latest_v.minor}.{latest_v.micro}", False
        if latest_v.micro > int(parts[2]):
            return f"~> {latest_v.major}.{latest_v.minor}.{latest_v.micro}", False
        return None, False

    try:
        if norm(latest) > norm(current):
            return latest, False
    except Exception:
        pass
    return None, False


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class Provider:
    name: str
    source: str
    version: str
    new_version: str | None = None
    manual: bool = False


@dataclass
class HelmRelease:
    name: str
    file: Path
    repository: str
    chart: str
    version: str
    latest: str | None = None


@dataclass
class Module:
    name: str
    file: Path
    source: str  # e.g. "namespace/name/provider"
    registry: str  # "opentofu" or "terraform"
    version: str
    latest: str | None = None


@dataclass
class ImageRef:
    file: Path
    original: str  # full original string, e.g. "cloudflare/cloudflared:2026.6.1"
    registry: str  # "dockerhub" | "ghcr" | "quay" | "unknown"
    namespace: str
    name: str
    tag: str
    latest_tag: str | None = None

    @property
    def updated(self) -> str:
        prefix = "/".join(p for p in [self.namespace, self.name] if p)
        registry_prefix = {
            "ghcr": "ghcr.io/",
            "quay": "quay.io/",
        }.get(self.registry, "")
        return f"{registry_prefix}{prefix}:{self.latest_tag}"


# ── HCL parsers ───────────────────────────────────────────────────────────────


def parse_providers(content: str) -> list[Provider]:
    header = re.search(r"required_providers\s*\{", content)
    if not header:
        return []
    block = _extract_block(content, header.end())
    pattern = re.compile(
        r"(\w+)\s*=\s*\{[^{}]*?"
        r'source\s*=\s*"([^"]+)"[^{}]*?'
        r'version\s*=\s*"([^"]+)"[^{}]*?\}',
        re.DOTALL,
    )
    return [
        Provider(name=m.group(1), source=m.group(2), version=m.group(3))
        for m in pattern.finditer(block)
        if m.group(1) not in IGNORE and m.group(2) not in IGNORE
    ]


def _extract_block(content: str, start: int) -> str:
    """Extract a brace-delimited block starting at `start` (after the opening `{`)."""
    depth, pos = 1, start
    while pos < len(content) and depth:
        depth += (content[pos] == "{") - (content[pos] == "}")
        pos += 1
    return content[start : pos - 1]


def parse_helm_releases(tf_files: list[Path]) -> list[HelmRelease]:
    releases: list[HelmRelease] = []
    header = re.compile(r'resource\s+"helm_release"\s+"(\w+)"\s*\{')
    attrs = re.compile(r'^\s*(repository|chart|version)\s*=\s*"([^"]+)"', re.MULTILINE)

    for path in tf_files:
        content = path.read_text()
        for m in header.finditer(content):
            block = _extract_block(content, m.end())
            found = {a.group(1): a.group(2) for a in attrs.finditer(block)}
            if all(k in found for k in ("repository", "chart", "version")):
                if found["chart"] not in IGNORE:
                    releases.append(HelmRelease(name=m.group(1), file=path, **found))  # type: ignore[arg-type]
    return releases


def parse_modules(tf_files: list[Path]) -> list[Module]:
    modules: list[Module] = []
    header = re.compile(r'module\s+"(\w+)"\s*\{')
    src_re = re.compile(r'^\s*source\s*=\s*"([^"]+)"', re.MULTILINE)
    ver_re = re.compile(r'^\s*version\s*=\s*"([^"]+)"', re.MULTILINE)

    for path in tf_files:
        content = path.read_text()
        for m in header.finditer(content):
            block = _extract_block(content, m.end())
            src_m = src_re.search(block)
            ver_m = ver_re.search(block)
            if not src_m or not ver_m:
                continue
            source = src_m.group(1)
            version = ver_m.group(1)
            # Skip local paths, git sources, http(s) sources
            if source.startswith(("./", "../", "git::", "https://", "http://")):
                continue
            # Normalise: strip explicit registry prefix
            registry = "opentofu"
            clean = source
            if source.startswith("registry.opentofu.org/"):
                clean = source[len("registry.opentofu.org/") :]
            elif source.startswith("registry.terraform.io/"):
                clean = source[len("registry.terraform.io/") :]
                registry = "terraform"
            # Must be namespace/name/provider
            if clean.count("/") != 2:
                continue
            if clean not in IGNORE and m.group(1) not in IGNORE:
                modules.append(
                    Module(
                        name=m.group(1),
                        file=path,
                        source=clean,
                        registry=registry,
                        version=version,
                    )
                )
    return modules


def _parse_image_ref(image_str: str, path: Path) -> ImageRef | None:
    """Parse 'registry/ns/name:tag' or 'ns/name:tag' or 'name:tag' into an ImageRef."""
    if ":" not in image_str:
        return None
    ref, tag = image_str.rsplit(":", 1)
    if not is_version_tag(tag):
        return None

    parts = ref.split("/")
    if parts[0] in ("ghcr.io",):
        return ImageRef(
            file=path,
            original=image_str,
            registry="ghcr",
            namespace="/".join(parts[1:-1]),
            name=parts[-1],
            tag=tag,
        )
    if parts[0] == "quay.io":
        return ImageRef(
            file=path,
            original=image_str,
            registry="quay",
            namespace="/".join(parts[1:-1]),
            name=parts[-1],
            tag=tag,
        )
    if "." in parts[0] or ":" in parts[0]:
        # Unknown registry (gcr.io, ECR, etc.)
        return None
    # Docker Hub — keep namespace empty for single-part images so updated preserves original format
    namespace = parts[0] if len(parts) > 1 else ""
    name = parts[-1]
    return ImageRef(
        file=path, original=image_str, registry="dockerhub", namespace=namespace, name=name, tag=tag
    )


def parse_images(tf_files: list[Path]) -> list[ImageRef]:
    images: list[ImageRef] = []
    # Match: image = "..."  (HCL attribute, single or double quotes with = sign)
    pattern = re.compile(r'image\s*=\s*"([^"]+)"')
    seen: set[str] = set()

    for path in tf_files:
        content = path.read_text()
        for m in pattern.finditer(content):
            img = m.group(1)
            if img in seen or img in IGNORE:
                continue
            seen.add(img)
            ref = _parse_image_ref(img, path)
            if ref:
                images.append(ref)
    return images


# ── Registry fetchers ─────────────────────────────────────────────────────────


async def fetch_latest_provider(session: aiohttp.ClientSession, source: str) -> str | None:
    url = f"https://registry.opentofu.org/v1/providers/{source}/versions"
    try:
        async with session.get(url, timeout=TIMEOUT) as r:
            data = await r.json(content_type=None)
        versions = [v["version"] for v in data.get("versions", []) if is_stable(v["version"])]
        return str(max(versions, key=norm)) if versions else None
    except Exception as e:
        print(f"  warn: provider {source}: {e}", file=sys.stderr)
        return None


async def fetch_latest_chart(session: aiohttp.ClientSession, repo: str, chart: str) -> str | None:
    url = f"{repo.rstrip('/')}/index.yaml"
    try:
        async with session.get(url, timeout=TIMEOUT) as r:
            text = await r.text()
        entries = yaml.safe_load(text).get("entries", {}).get(chart, [])
        stable = [str(e["version"]) for e in entries if is_stable(str(e["version"]))]
        return str(max(stable, key=norm)) if stable else None
    except Exception as e:
        print(f"  warn: chart {chart} @ {repo}: {e}", file=sys.stderr)
        return None


async def fetch_latest_module(
    session: aiohttp.ClientSession, source: str, registry: str
) -> str | None:
    base = (
        "https://registry.opentofu.org"
        if registry == "opentofu"
        else "https://registry.terraform.io"
    )
    url = f"{base}/v1/modules/{source}/versions"
    try:
        async with session.get(url, timeout=TIMEOUT) as r:
            data = await r.json(content_type=None)
        versions = [
            v["version"]
            for mod in data.get("modules", [])
            for v in mod.get("versions", [])
            if is_stable(v["version"])
        ]
        return str(max(versions, key=norm)) if versions else None
    except Exception as e:
        print(f"  warn: module {source}: {e}", file=sys.stderr)
        return None


async def _dockerhub_token(session: aiohttp.ClientSession, namespace: str, name: str) -> str:
    repo = f"{namespace}/{name}"
    url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
    headers: dict = {}
    if DOCKERHUB_USERNAME and DOCKERHUB_TOKEN:
        creds = base64.b64encode(f"{DOCKERHUB_USERNAME}:{DOCKERHUB_TOKEN}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"
    async with session.get(url, headers=headers, timeout=TIMEOUT) as r:
        return (await r.json(content_type=None)).get("token", "")


async def _ghcr_token(session: aiohttp.ClientSession, namespace: str, name: str) -> str:
    if not GHCR_TOKEN:
        return ""
    scope = f"repository:{namespace}/{name}:pull"
    url = f"https://ghcr.io/token?scope={scope}"
    creds = base64.b64encode(f"token:{GHCR_TOKEN}".encode()).decode()
    async with session.get(url, headers={"Authorization": f"Basic {creds}"}, timeout=TIMEOUT) as r:
        return (await r.json(content_type=None)).get("token", "")


async def _list_tags_oci(
    session: aiohttp.ClientSession, registry_host: str, repo: str, token: str
) -> list[str]:
    url = f"https://{registry_host}/v2/{repo}/tags/list"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    tags: list[str] = []
    while url:
        async with session.get(url, headers=headers, timeout=TIMEOUT) as r:
            if r.status != 200:
                break
            data = await r.json(content_type=None)
            tags.extend(data.get("tags") or [])
            link = r.headers.get("Link", "")
            next_url = re.search(r'<([^>]+)>;\s*rel="next"', link)
            url = next_url.group(1) if next_url else None  # type: ignore[assignment]
    return tags


async def fetch_latest_image(session: aiohttp.ClientSession, ref: ImageRef) -> str | None:
    try:
        if ref.registry == "dockerhub":
            ns = ref.namespace or "library"
            repo = f"{ns}/{ref.name}"
            token = await _dockerhub_token(session, ns, ref.name)
            tags = await _list_tags_oci(session, "registry-1.docker.io", repo, token)
        elif ref.registry == "ghcr":
            repo = f"{ref.namespace}/{ref.name}" if ref.namespace else ref.name
            token = await _ghcr_token(session, ref.namespace or "", ref.name)
            tags = await _list_tags_oci(session, "ghcr.io", repo, token)
        else:
            return None

        stable = [t for t in tags if is_version_tag(t) and is_stable(t)]
        if not stable:
            return None

        # Prefer tags that match the same format as current (v-prefix vs bare)
        has_v = ref.tag.startswith("v")
        same_format = [t for t in stable if t.startswith("v") == has_v]
        candidates = same_format or stable

        try:
            best = str(max(candidates, key=norm))
        except Exception:
            # Fall back to lexicographic if version parse fails for any candidate
            best = sorted(candidates)[-1]

        return best if norm(best) > norm(ref.tag) else None
    except Exception as e:
        print(f"  warn: image {ref.original}: {e}", file=sys.stderr)
        return None


# ── File updaters ─────────────────────────────────────────────────────────────


def apply_provider_update(content: str, source: str, new_ver: str) -> str:
    pattern = re.compile(
        r'(source\s*=\s*"' + re.escape(source) + r'"[^}]*?version\s*=\s*)"[^"]+"',
        re.DOTALL,
    )
    return pattern.sub(r'\g<1>"' + new_ver + '"', content)


def apply_chart_update(content: str, chart: str, old_ver: str, new_ver: str) -> str:
    header = re.compile(r'resource\s+"helm_release"\s+"\w+"\s*\{')
    chart_re = re.compile(r'chart\s*=\s*"' + re.escape(chart) + r'"')
    ver_re = re.compile(r'(version\s*=\s*)"' + re.escape(old_ver) + r'"')
    for m in header.finditer(content):
        start = m.end()
        block = _extract_block(content, start)
        if not chart_re.search(block):
            continue
        new_block = ver_re.sub(r'\g<1>"' + new_ver + '"', block)
        if new_block != block:
            return content[:start] + new_block + content[start + len(block) :]
    return content


def apply_module_update(content: str, source: str, old_ver: str, new_ver: str) -> str:
    # Match source = "..." then version = "old" within the same module block
    escaped_sources = [
        re.escape(source),
        re.escape(f"registry.opentofu.org/{source}"),
        re.escape(f"registry.terraform.io/{source}"),
    ]
    for esc in escaped_sources:
        pattern = re.compile(
            r'(source\s*=\s*"' + esc + r'"[^}]*?version\s*=\s*)"' + re.escape(old_ver) + r'"',
            re.DOTALL,
        )
        updated = pattern.sub(r'\g<1>"' + new_ver + '"', content)
        if updated != content:
            return updated
    return content


def apply_image_update(content: str, old_ref: str, new_ref: str) -> str:
    return content.replace(f'"{old_ref}"', f'"{new_ref}"')


# ── Main ──────────────────────────────────────────────────────────────────────


async def main() -> None:
    tf_files = list(REPO_ROOT.rglob("*.tf"))
    non_versions_files = [f for f in tf_files if f.resolve() != VERSIONS_FILE.resolve()]

    providers: list[Provider] = []
    releases: list[HelmRelease] = []
    modules: list[Module] = []
    images: list[ImageRef] = []

    if not SKIP_PROVIDERS and VERSIONS_FILE.exists():
        providers = parse_providers(VERSIONS_FILE.read_text())
    if not SKIP_HELM:
        releases = parse_helm_releases(non_versions_files)
    if not SKIP_MODULES:
        modules = parse_modules(non_versions_files)
    if not SKIP_IMAGES:
        images = parse_images(tf_files)

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            asyncio.gather(*(fetch_latest_provider(session, p.source) for p in providers)),
            asyncio.gather(*(fetch_latest_chart(session, r.repository, r.chart) for r in releases)),
            asyncio.gather(*(fetch_latest_module(session, m.source, m.registry) for m in modules)),
            asyncio.gather(*(fetch_latest_image(session, img) for img in images)),
        )

    provider_latest, chart_latest, module_latest, image_latest = results  # type: ignore[misc]

    manual_items: list[str] = []

    for p, latest in zip(providers, provider_latest):
        if not latest:
            continue
        new_ver, needs_manual = new_constraint(p.version, latest)
        if needs_manual:
            manual_items.append(
                f"- `{p.name}` (`{p.source}`): `{p.version}` → `{latest}` (major bump)"
            )
        elif new_ver:
            p.new_version = new_ver

    for r, latest in zip(releases, chart_latest):
        if not latest:
            continue
        try:
            if norm(latest) > norm(r.version):
                r.latest = latest
        except Exception:
            pass

    for m, latest in zip(modules, module_latest):
        if not latest:
            continue
        try:
            new_ver, needs_manual = new_constraint(m.version, latest)
            if needs_manual:
                manual_items.append(
                    f"- module `{m.name}` (`{m.source}`): `{m.version}` → `{latest}` (major bump)"
                )
            elif new_ver:
                m.latest = new_ver
        except Exception:
            pass

    for img, latest in zip(images, image_latest):
        if latest:
            img.latest_tag = latest

    provider_updates = [p for p in providers if p.new_version]
    chart_updates = [r for r in releases if r.latest]
    module_updates = [m for m in modules if m.latest]
    image_updates = [img for img in images if img.latest_tag]

    if not DRY_RUN:
        if provider_updates and VERSIONS_FILE.exists():
            content = VERSIONS_FILE.read_text()
            for u in provider_updates:
                content = apply_provider_update(content, u.source, u.new_version)  # type: ignore[arg-type]
            VERSIONS_FILE.write_text(content)

        for u in chart_updates:
            content = u.file.read_text()
            updated = apply_chart_update(content, u.chart, u.version, u.latest)  # type: ignore[arg-type]
            if updated != content:
                u.file.write_text(updated)

        for u in module_updates:
            content = u.file.read_text()
            updated = apply_module_update(content, u.source, u.version, u.latest)  # type: ignore[arg-type]
            if updated != content:
                u.file.write_text(updated)

        by_file: dict[Path, list[ImageRef]] = defaultdict(list)
        for img in image_updates:
            by_file[img.file].append(img)
        for path, refs in by_file.items():
            content = path.read_text()
            for img in refs:
                content = apply_image_update(content, img.original, img.updated)
            path.write_text(content)

    # ── Report ────────────────────────────────────────────────────────────────
    lines: list[str] = []

    if provider_updates:
        lines.append("Provider updates:")
        for u in provider_updates:
            lines.append(f"- {u.name} ({u.source}): {u.version} → {u.new_version}")
        lines.append("")
        lines.append("Note: run 'tofu init -upgrade' after merging to regenerate the lock file.")
        lines.append("")

    if chart_updates:
        lines.append("Helm chart updates:")
        for u in chart_updates:
            lines.append(f"- {u.chart} ({u.name}): {u.version} → {u.latest}")
        lines.append("")

    if module_updates:
        lines.append("Module updates:")
        for u in module_updates:
            lines.append(f"- {u.name} ({u.source}): {u.version} → {u.latest}")
        lines.append("")

    if image_updates:
        lines.append("Container image updates:")
        for u in image_updates:
            lines.append(f"- {u.original} → {u.updated}")
        lines.append("")

    if manual_items:
        lines.append("Major bumps — manual review required:")
        lines.extend(manual_items)
        lines.append("")

    if not lines:
        lines.append("All providers, charts, modules, and images are up to date.")

    report = "\n".join(lines).strip()
    print(report)

    if DRY_RUN:
        print("\n(dry-run: no files were modified)", file=sys.stderr)

    has_changes = bool(provider_updates or chart_updates or module_updates or image_updates)

    # Write report to file; action.yml captures it to avoid GITHUB_OUTPUT multiline issues
    Path(".update-report.txt").write_text(report)

    if gh_out := os.environ.get("GITHUB_OUTPUT"):
        with open(gh_out, "a") as f:
            f.write(f"changes={'true' if has_changes else 'false'}\n")


if __name__ == "__main__":
    asyncio.run(main())
