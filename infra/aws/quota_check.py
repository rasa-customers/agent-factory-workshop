"""Does the account's EC2 vCPU quota cover the VM ceiling?  python -m infra.aws.quota_check"""
from __future__ import annotations

import os
import sys

from infra.aws.common import PORTAL_TYPE, VM_TYPE, session


def main() -> int:
    s = session()
    quota = s.client("service-quotas").get_service_quota(ServiceCode="ec2", QuotaCode="L-1216C47A")["Quota"]["Value"]
    ec2 = s.client("ec2")
    vcpu = lambda t: ec2.describe_instance_types(InstanceTypes=[t])["InstanceTypes"][0]["VCpuInfo"]["DefaultVCpus"]  # noqa: E731
    running = sum(vcpu(i["InstanceType"]) for r in ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running", "pending"]}])["Reservations"] for i in r["Instances"])
    ceiling = int(os.environ.get("CEILING", "60"))
    need = ceiling * vcpu(VM_TYPE) + vcpu(PORTAL_TYPE)
    print(f"On-Demand Standard vCPU quota: {quota:.0f}; in use: {running}; workshop needs up to {need} "
          f"({ceiling} × {VM_TYPE} + portal).")
    ok = running + need <= quota
    print("✓ enough headroom" if ok else "✗ not enough — request a quota increase or lower CEILING")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
