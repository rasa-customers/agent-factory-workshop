"""Tear down after the workshop.

    uv run python -m infra.aws.teardown              # revoke attendee keys, terminate cloud machines
    uv run python -m infra.aws.teardown --everything # also portal host, load balancer, DNS, cert, image, VPC

Only touches resources tagged project=factory-workshop and DNS under factory-workshop.playground-cse.rasa-dev.io.
"""
from __future__ import annotations

import os
import sys

from infra.portal.keys import revoke_all_keys

from infra.aws.common import DOMAIN, assert_safe_record, in_domain, parent_zone_id, session

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
    n = revoke_all_keys(url, master)
    print(f"revoked {n} keys")


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
    if vms:
        ec2.get_waiter("instance_terminated").wait(InstanceIds=[i["InstanceId"] for i in vms])
    remove_dns()
    remove_load_balancer()
    for a in ec2.describe_addresses(Filters=TAGGED)["Addresses"]:
        ec2.release_address(AllocationId=a["AllocationId"])
    quietly(ec2.delete_launch_template, LaunchTemplateName="factory-workshop-vm")
    for img in ec2.describe_images(Owners=["self"], Filters=TAGGED)["Images"]:
        ec2.deregister_image(ImageId=img["ImageId"])
        for bd in img.get("BlockDeviceMappings", []):
            if "Ebs" in bd:
                quietly(ec2.delete_snapshot, SnapshotId=bd["Ebs"]["SnapshotId"])
    acm = s.client("acm")
    for c in acm.list_certificates()["CertificateSummaryList"]:
        if c["DomainName"] == f"*.{DOMAIN}":
            quietly(acm.delete_certificate, CertificateArn=c["CertificateArn"])
    remove_network()
    quietly(ec2.delete_key_pair, KeyName="factory-workshop")
    print("removed portal host, load balancer, DNS records, certificate, images, launch template and the workshop VPC "
          "(the IAM role factory-workshop-portal is left: deleting it needs the admin profile)")


def quietly(fn, **kw) -> None:
    try:
        fn(**kw)
    except Exception as e:  # noqa: BLE001
        print(f"  skipped {fn.__name__}: {str(e)[:120]}")


def remove_dns() -> None:
    """Delete every record at or under DOMAIN (wildcard alias, certificate validation) — nothing else."""
    r53 = s.client("route53")
    zone = parent_zone_id(r53)
    changes = []
    for page in r53.get_paginator("list_resource_record_sets").paginate(HostedZoneId=zone):
        for rr in page["ResourceRecordSets"]:
            if in_domain(rr["Name"]):
                assert_safe_record(rr["Name"])
                changes.append({"Action": "DELETE", "ResourceRecordSet": rr})
    if changes:
        r53.change_resource_record_sets(HostedZoneId=zone, ChangeBatch={"Changes": changes})
    print(f"removed {len(changes)} DNS records under {DOMAIN}")


def remove_load_balancer() -> None:
    elb = s.client("elbv2")
    try:
        lb = elb.describe_load_balancers(Names=["factory-workshop"])["LoadBalancers"][0]
        elb.delete_load_balancer(LoadBalancerArn=lb["LoadBalancerArn"])
        elb.get_waiter("load_balancers_deleted").wait(LoadBalancerArns=[lb["LoadBalancerArn"]])
    except Exception as e:  # noqa: BLE001
        print(f"  no load balancer: {str(e)[:80]}")
    try:
        tg = elb.describe_target_groups(Names=["factory-workshop-portal"])["TargetGroups"][0]
        quietly(elb.delete_target_group, TargetGroupArn=tg["TargetGroupArn"])
    except Exception:  # noqa: BLE001
        pass


def remove_network() -> None:
    vpcs = ec2.describe_vpcs(Filters=TAGGED)["Vpcs"]
    for v in vpcs:
        vid = v["VpcId"]
        import time
        time.sleep(30)  # load balancer network interfaces take a moment to go
        for g in ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vid]}])["SecurityGroups"]:
            if g["GroupName"] != "default" and g.get("IpPermissions"):
                quietly(ec2.revoke_security_group_ingress, GroupId=g["GroupId"], IpPermissions=g["IpPermissions"])
        for g in ec2.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vid]}])["SecurityGroups"]:
            if g["GroupName"] != "default":
                quietly(ec2.delete_security_group, GroupId=g["GroupId"])
        for sn in ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vid]}])["Subnets"]:
            quietly(ec2.delete_subnet, SubnetId=sn["SubnetId"])
        for rt in ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vid]}] + TAGGED)["RouteTables"]:
            quietly(ec2.delete_route_table, RouteTableId=rt["RouteTableId"])
        for igw in ec2.describe_internet_gateways(Filters=[{"Name": "attachment.vpc-id", "Values": [vid]}])["InternetGateways"]:
            quietly(ec2.detach_internet_gateway, InternetGatewayId=igw["InternetGatewayId"], VpcId=vid)
            quietly(ec2.delete_internet_gateway, InternetGatewayId=igw["InternetGatewayId"])
        quietly(ec2.delete_vpc, VpcId=vid)
        print(f"removed VPC {vid}")

if __name__ == "__main__":
    main()
