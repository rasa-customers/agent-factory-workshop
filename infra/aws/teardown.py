"""Tear down after the workshop.

    uv run python -m infra.aws.teardown              # revoke attendee keys, terminate cloud machines
    uv run python -m infra.aws.teardown --everything # also the portal host, Elastic IP, DNS, image, launch template

Only touches resources tagged project=factory-workshop and DNS under factory-workshop.playground-cse.rasa-dev.io.
"""
from __future__ import annotations

import os
import sys

import httpx

from infra.aws.common import DOMAIN, assert_safe_record, parent_zone_id, session

s = session()
ec2 = s.client("ec2")
TAGGED = [{"Name": "tag:project", "Values": ["factory-workshop"]}]


def instances(name_prefix: str) -> list[dict]:
    r = ec2.describe_instances(Filters=TAGGED + [{"Name": "instance-state-name", "Values": ["pending", "running", "stopped"]}])
    out = []
    for res in r["Reservations"]:
        for i in res["Instances"]:
            name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "")
            if name.startswith(name_prefix):
                out.append(i)
    return out


def revoke_keys() -> None:
    url, master = os.environ.get("LITELLM_URL", f"https://llm.{DOMAIN}"), os.environ.get("LITELLM_MASTER_KEY")
    if not master:
        print("LITELLM_MASTER_KEY not set — skipping key revocation (or stop the litellm container).")
        return
    h = {"Authorization": f"Bearer {master}"}
    keys = httpx.get(f"{url}/key/list", headers=h, params={"size": 1000}, timeout=30).json().get("keys", [])
    if keys:
        httpx.post(f"{url}/key/delete", headers=h, json={"keys": keys}, timeout=60).raise_for_status()
    print(f"revoked {len(keys)} keys")


def main() -> None:
    everything = "--everything" in sys.argv
    revoke_keys()
    vms = instances("factory-workshop-vm-") + instances("factory-workshop-bake")
    if vms:
        ec2.terminate_instances(InstanceIds=[i["InstanceId"] for i in vms])
    print(f"terminated {len(vms)} cloud machines")
    if not everything:
        return
    for i in instances("factory-workshop-portal"):
        ec2.terminate_instances(InstanceIds=[i["InstanceId"]])
        ec2.get_waiter("instance_terminated").wait(InstanceIds=[i["InstanceId"]])
        print(f"terminated portal host {i['InstanceId']}")
    for a in ec2.describe_addresses(Filters=TAGGED)["Addresses"]:
        ec2.release_address(AllocationId=a["AllocationId"])
        r53 = s.client("route53")
        name = f"*.{DOMAIN}"
        assert_safe_record(name)
        try:
            r53.change_resource_record_sets(HostedZoneId=parent_zone_id(r53), ChangeBatch={"Changes": [{
                "Action": "DELETE", "ResourceRecordSet": {"Name": name, "Type": "A", "TTL": 60,
                                                          "ResourceRecords": [{"Value": a["PublicIp"]}]}}]})
        except Exception as e:  # noqa: BLE001
            print(f"DNS record not removed: {e}")
    try:
        ec2.delete_launch_template(LaunchTemplateName="factory-workshop-vm")
    except Exception:  # noqa: BLE001
        pass
    for img in ec2.describe_images(Owners=["self"], Filters=TAGGED)["Images"]:
        ec2.deregister_image(ImageId=img["ImageId"])
        for bd in img.get("BlockDeviceMappings", []):
            if "Ebs" in bd:
                ec2.delete_snapshot(SnapshotId=bd["Ebs"]["SnapshotId"])
    print("removed portal host, address, DNS record, launch template and images "
          "(security groups, IAM role and key pair are left; they cost nothing)")


if __name__ == "__main__":
    main()
