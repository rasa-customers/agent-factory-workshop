"""Where cloud machines come from: EC2 for real, a fake for tests."""
from __future__ import annotations

import asyncio
import base64
import os
from typing import Protocol

import httpx

TAG = {"Key": "project", "Value": "factory-workshop"}


class VmProvider(Protocol):
    async def launch(self, vm_id: str, hostname: str, config_secret: str) -> str: ...
    async def is_ready(self, vm: dict) -> str | None:
        """The machine's private IP once it is up and serving, else None."""
    async def terminate(self, vm: dict) -> None: ...


class FakeProvider:
    def __init__(self) -> None:
        self.launched: list[str] = []
        self._ready: set[str] = set()

    async def launch(self, vm_id: str, hostname: str, config_secret: str) -> str:
        self.launched.append(hostname)
        return f"i-{len(self.launched):04d}"

    def ready(self, hostname: str) -> None:
        self._ready.add(hostname)

    def ready_all(self) -> None:
        self._ready.update(self.launched)

    async def is_ready(self, vm: dict) -> str | None:
        return f"10.0.0.{self.launched.index(vm['hostname']) + 10}" if vm["hostname"] in self._ready else None

    async def terminate(self, vm: dict) -> None:
        self._ready.discard(vm["hostname"])


USER_DATA = """#!/bin/bash
cat > /etc/factory-workshop.env <<EOT
VM_ID={vm_id}
VM_HOSTNAME={hostname}
CONFIG_SECRET={secret}
PORTAL_URL={portal}
DOMAIN={domain}
EOT
systemctl restart factory-config-agent
"""


class Ec2Provider:
    """Launches from the `factory-workshop-vm` launch template. Machines are reached via their private IP
    through the portal host's reverse proxy, so they need no public DNS or certificates of their own."""

    def __init__(self, portal_url: str, domain: str, template: str = "factory-workshop-vm",
                 region: str = "us-east-1", profile: str | None = None) -> None:
        import boto3

        session = boto3.Session(profile_name=profile, region_name=region) if profile else boto3.Session(region_name=region)
        self.ec2 = session.client("ec2")
        self.portal_url, self.domain, self.template = portal_url, domain, template

    async def launch(self, vm_id: str, hostname: str, config_secret: str) -> str:
        user_data = USER_DATA.format(vm_id=vm_id, hostname=hostname, secret=config_secret,
                                     portal=self.portal_url, domain=self.domain)

        def run() -> str:
            r = self.ec2.run_instances(
                LaunchTemplate={"LaunchTemplateName": self.template, "Version": "$Latest"},
                MinCount=1, MaxCount=1, UserData=base64.b64encode(user_data.encode()).decode(),
                TagSpecifications=[{"ResourceType": "instance",
                                    "Tags": [TAG, {"Key": "Name", "Value": f"factory-workshop-{vm_id}"}]}])
            return r["Instances"][0]["InstanceId"]

        return await asyncio.to_thread(run)

    async def is_ready(self, vm: dict) -> str | None:
        def ip() -> str | None:
            r = self.ec2.describe_instances(InstanceIds=[vm["instance_id"]])
            return r["Reservations"][0]["Instances"][0].get("PrivateIpAddress")

        addr = await asyncio.to_thread(ip)
        if not addr:
            return None
        try:
            async with httpx.AsyncClient(timeout=3) as c:
                ok = (await c.get(f"http://{addr}:8080/healthz")).status_code == 200
        except httpx.HTTPError:
            ok = False
        return addr if ok else None

    async def terminate(self, vm: dict) -> None:
        await asyncio.to_thread(self.ec2.terminate_instances, InstanceIds=[vm["instance_id"]])


def provider_from_env() -> VmProvider | None:
    if os.environ.get("CLOUD_VMS", "on") == "off":
        return None
    return Ec2Provider(portal_url=os.environ["PORTAL_URL"], domain=os.environ["DOMAIN"],
                       profile=os.environ.get("AWS_PROFILE") or None)
