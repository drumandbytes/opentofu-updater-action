"""Tests for HCL file update functions."""

import pytest
from pathlib import Path

from update_versions import (
    apply_chart_update,
    apply_image_update,
    apply_module_update,
    apply_provider_update,
)

VERSIONS_TF = '''\
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
  }
}
'''

HELM_TF = '''\
resource "helm_release" "cilium" {
  repository = "https://helm.cilium.io"
  chart      = "cilium"
  version    = "1.17.4"
}
resource "helm_release" "traefik" {
  repository = "https://helm.traefik.io/traefik"
  chart      = "traefik"
  version    = "35.0.0"
}
'''

HELM_TF_WITH_SET = '''\
resource "helm_release" "cilium" {
  repository = "https://helm.cilium.io"
  chart      = "cilium"
  set {
    name  = "global.tag"
    value = "custom"
  }
  version    = "1.17.4"
}
'''

MODULE_TF = '''\
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.1.2"
}
'''

MODULE_TF_EXPLICIT = '''\
module "vpc" {
  source  = "registry.opentofu.org/terraform-aws-modules/vpc/aws"
  version = "5.1.2"
}
'''

IMAGE_TF = '''\
resource "kubernetes_deployment_v1" "app" {
  spec {
    template {
      spec {
        container {
          image = "cloudflare/cloudflared:2026.6.1"
        }
      }
    }
  }
}
'''


class TestApplyProviderUpdate:
    def test_exact_pin_bump(self):
        updated = apply_provider_update(VERSIONS_TF, "bpg/proxmox", "0.112.0")
        assert '"0.112.0"' in updated
        assert '"0.111.0"' not in updated

    def test_pessimistic_constraint_bump(self):
        updated = apply_provider_update(VERSIONS_TF, "hashicorp/helm", "~> 3.3")
        assert '"~> 3.3"' in updated
        assert '"~> 3.2.0"' not in updated

    def test_leaves_other_providers_unchanged(self):
        updated = apply_provider_update(VERSIONS_TF, "bpg/proxmox", "0.112.0")
        assert '"~> 3.2.0"' in updated

    def test_source_not_present(self):
        updated = apply_provider_update(VERSIONS_TF, "nonexistent/provider", "1.0.0")
        assert updated == VERSIONS_TF


class TestApplyChartUpdate:
    def test_updates_correct_chart(self):
        updated = apply_chart_update(HELM_TF, "cilium", "1.17.4", "1.17.9")
        assert '"1.17.9"' in updated
        assert '"35.0.0"' in updated  # traefik untouched

    def test_leaves_other_charts_unchanged(self):
        updated = apply_chart_update(HELM_TF, "cilium", "1.17.4", "1.18.0")
        assert '"35.0.0"' in updated

    def test_no_match(self):
        updated = apply_chart_update(HELM_TF, "cilium", "9.9.9", "10.0.0")
        assert updated == HELM_TF

    def test_chart_not_present(self):
        updated = apply_chart_update(HELM_TF, "nonexistent", "1.0.0", "2.0.0")
        assert updated == HELM_TF

    def test_updates_through_nested_set_block(self):
        updated = apply_chart_update(HELM_TF_WITH_SET, "cilium", "1.17.4", "1.17.9")
        assert '"1.17.9"' in updated
        assert '"1.17.4"' not in updated


class TestApplyModuleUpdate:
    def test_bare_source(self):
        updated = apply_module_update(MODULE_TF, "terraform-aws-modules/vpc/aws", "5.1.2", "5.2.0")
        assert '"5.2.0"' in updated
        assert '"5.1.2"' not in updated

    def test_explicit_registry_prefix(self):
        updated = apply_module_update(MODULE_TF_EXPLICIT, "terraform-aws-modules/vpc/aws", "5.1.2", "5.2.0")
        assert '"5.2.0"' in updated

    def test_no_match(self):
        updated = apply_module_update(MODULE_TF, "terraform-aws-modules/vpc/aws", "9.9.9", "10.0.0")
        assert updated == MODULE_TF

    def test_source_not_present(self):
        updated = apply_module_update(MODULE_TF, "nonexistent/mod/aws", "5.1.2", "5.2.0")
        assert updated == MODULE_TF


class TestApplyImageUpdate:
    def test_replaces_image(self):
        updated = apply_image_update(IMAGE_TF, "cloudflare/cloudflared:2026.6.1", "cloudflare/cloudflared:2026.7.0")
        assert '"cloudflare/cloudflared:2026.7.0"' in updated
        assert '"cloudflare/cloudflared:2026.6.1"' not in updated

    def test_no_match(self):
        updated = apply_image_update(IMAGE_TF, "nginx:1.25.0", "nginx:1.26.0")
        assert updated == IMAGE_TF

    def test_multiple_occurrences(self):
        content = 'image = "nginx:1.25.0"\nimage = "nginx:1.25.0"\n'
        updated = apply_image_update(content, "nginx:1.25.0", "nginx:1.26.0")
        assert updated.count('"nginx:1.26.0"') == 2
