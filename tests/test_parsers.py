"""Tests for HCL parsing functions."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / ".github" / "scripts"))

from update_versions import (
    parse_providers,
    parse_helm_releases,
    parse_modules,
    parse_images,
    new_constraint,
    is_version_tag,
    _parse_image_ref,
)


VERSIONS_TF = '''
terraform {
  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.111.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.2.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }
}
'''

HELM_TF = '''
resource "helm_release" "cilium" {
  name       = "cilium"
  repository = "https://helm.cilium.io"
  chart      = "cilium"
  version    = "1.17.4"
  namespace  = "kube-system"
  max_history = 2
}

resource "helm_release" "traefik" {
  name       = "traefik"
  repository = "https://helm.traefik.io/traefik"
  chart      = "traefik"
  version    = "35.0.0"
  namespace  = "traefik"
  max_history = 2
}
'''

MODULE_TF = '''
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.1.2"
  cidr    = "10.0.0.0/16"
}

module "local_path" {
  source = "./modules/local-path"
}
'''

IMAGE_TF = '''
resource "kubernetes_deployment_v1" "cloudflared" {
  spec {
    template {
      spec {
        container {
          name  = "cloudflared"
          image = "cloudflare/cloudflared:2026.6.1"
        }
      }
    }
  }
}

resource "kubernetes_deployment_v1" "app" {
  spec {
    template {
      spec {
        container {
          image = "ghcr.io/myorg/myapp:v1.2.3"
        }
      }
    }
  }
}
'''


class TestParseProviders:
    def test_exact_pin(self):
        providers = parse_providers(VERSIONS_TF)
        assert len(providers) == 3
        proxmox = next(p for p in providers if p.name == "proxmox")
        assert proxmox.source == "bpg/proxmox"
        assert proxmox.version == "0.111.0"

    def test_pessimistic_constraint(self):
        providers = parse_providers(VERSIONS_TF)
        helm = next(p for p in providers if p.name == "helm")
        assert helm.version == "~> 3.2.0"

    def test_short_pessimistic_constraint(self):
        providers = parse_providers(VERSIONS_TF)
        cf = next(p for p in providers if p.name == "cloudflare")
        assert cf.version == "~> 5.0"


class TestParseHelmReleases:
    def test_parses_all_releases(self, tmp_path):
        f = tmp_path / "helm.tf"
        f.write_text(HELM_TF)
        releases = parse_helm_releases([f])
        assert len(releases) == 2
        names = {r.chart for r in releases}
        assert names == {"cilium", "traefik"}

    def test_release_fields(self, tmp_path):
        f = tmp_path / "helm.tf"
        f.write_text(HELM_TF)
        releases = parse_helm_releases([f])
        cilium = next(r for r in releases if r.chart == "cilium")
        assert cilium.repository == "https://helm.cilium.io"
        assert cilium.version == "1.17.4"

    def test_skips_releases_missing_fields(self, tmp_path):
        f = tmp_path / "helm.tf"
        f.write_text('resource "helm_release" "broken" { chart = "foo" }')
        releases = parse_helm_releases([f])
        assert releases == []


class TestParseModules:
    def test_registry_module(self, tmp_path):
        f = tmp_path / "modules.tf"
        f.write_text(MODULE_TF)
        modules = parse_modules([f])
        assert len(modules) == 1
        assert modules[0].source == "terraform-aws-modules/vpc/aws"
        assert modules[0].version == "5.1.2"

    def test_skips_local_path(self, tmp_path):
        f = tmp_path / "modules.tf"
        f.write_text(MODULE_TF)
        modules = parse_modules([f])
        names = [m.name for m in modules]
        assert "local_path" not in names

    def test_strips_explicit_registry_prefix(self, tmp_path):
        f = tmp_path / "modules.tf"
        f.write_text('''
module "eks" {
  source  = "registry.opentofu.org/terraform-aws-modules/eks/aws"
  version = "20.0.0"
}
''')
        modules = parse_modules([f])
        assert modules[0].source == "terraform-aws-modules/eks/aws"
        assert modules[0].registry == "opentofu"


class TestParseImages:
    def test_dockerhub_image(self, tmp_path):
        f = tmp_path / "deploy.tf"
        f.write_text(IMAGE_TF)
        images = parse_images([f])
        docker = next(i for i in images if "cloudflared" in i.name)
        assert docker.registry == "dockerhub"
        assert docker.namespace == "cloudflare"
        assert docker.tag == "2026.6.1"

    def test_ghcr_image(self, tmp_path):
        f = tmp_path / "deploy.tf"
        f.write_text(IMAGE_TF)
        images = parse_images([f])
        ghcr = next(i for i in images if i.registry == "ghcr")
        assert ghcr.namespace == "myorg"
        assert ghcr.name == "myapp"
        assert ghcr.tag == "v1.2.3"

    def test_skips_latest_tag(self, tmp_path):
        f = tmp_path / "deploy.tf"
        f.write_text('container { image = "nginx:latest" }')
        images = parse_images([f])
        assert images == []


class TestNewConstraint:
    def test_exact_bump(self):
        ver, manual = new_constraint("0.111.0", "0.112.0")
        assert ver == "0.112.0"
        assert not manual

    def test_exact_no_change(self):
        ver, manual = new_constraint("0.112.0", "0.112.0")
        assert ver is None
        assert not manual

    def test_pessimistic_minor(self):
        ver, manual = new_constraint("~> 3.2", "3.5.1")
        assert ver == "~> 3.5"
        assert not manual

    def test_pessimistic_no_change(self):
        ver, manual = new_constraint("~> 3.2", "3.2.9")
        assert ver is None
        assert not manual

    def test_pessimistic_major_flags_manual(self):
        ver, manual = new_constraint("~> 3.2", "4.0.0")
        assert ver is None
        assert manual

    def test_pessimistic_patch(self):
        ver, manual = new_constraint("~> 1.17.4", "1.17.9")
        assert ver == "~> 1.17.9"
        assert not manual

    def test_pessimistic_patch_minor_bump(self):
        ver, manual = new_constraint("~> 1.17.4", "1.18.0")
        assert ver == "~> 1.18.0"
        assert not manual


class TestIsVersionTag:
    def test_semver(self):
        assert is_version_tag("1.25.3")
        assert is_version_tag("v1.25.3")

    def test_date_based(self):
        assert is_version_tag("2026.6.1")

    def test_rejects_latest(self):
        assert not is_version_tag("latest")

    def test_rejects_main(self):
        assert not is_version_tag("main")

    def test_rejects_rc(self):
        assert not is_version_tag("rc1")
        assert not is_version_tag("1.0.0-rc1")

    def test_rejects_bare_string(self):
        assert not is_version_tag("stable")
