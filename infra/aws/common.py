"""Shared AWS settings for the workshop scripts. Everything we create is tagged project=factory-workshop."""
from __future__ import annotations

import os

import boto3

PROFILE = os.environ.get("AWS_PROFILE", "cse-playground")
REGION = "us-east-1"
PARENT_ZONE = "playground-cse.rasa-dev.io."
FORBIDDEN_ZONE = "agent-factory.playground-cse.rasa-dev.io."  # belongs to another project — never touch
DOMAIN = "factory-workshop.playground-cse.rasa-dev.io"
TAG = {"Key": "project", "Value": "factory-workshop"}
VM_TYPE = os.environ.get("VM_TYPE", "t3.xlarge")  # 4 vCPU: builds, checks and training share it
PORTAL_TYPE = os.environ.get("PORTAL_TYPE", "t3.large")
VM_PORTS = (8080, 5005, 5006, 8600, 8800)


def session(profile: str = PROFILE) -> boto3.Session:
    return boto3.Session(profile_name=profile, region_name=REGION)


def tags(name: str) -> list[dict]:
    return [TAG, {"Key": "Name", "Value": name}]


def parent_zone_id(r53) -> str:
    zones = r53.list_hosted_zones_by_name(DNSName=PARENT_ZONE)["HostedZones"]
    zone = next(z for z in zones if z["Name"] == PARENT_ZONE)
    assert zone["Name"] != FORBIDDEN_ZONE
    return zone["Id"].split("/")[-1]


def in_domain(name: str) -> bool:
    """True only for DOMAIN itself or a name under it (label boundary), never the forbidden zone."""
    n = name.replace("\\052", "*").rstrip(".").lower()
    return (n == DOMAIN or n.endswith("." + DOMAIN)) and not (n + ".").endswith(FORBIDDEN_ZONE)


def assert_safe_record(name: str) -> None:
    if not in_domain(name):
        raise SystemExit(f"Refusing to touch DNS record {name!r}: outside {DOMAIN}")
