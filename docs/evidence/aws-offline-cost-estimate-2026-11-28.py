"""Reproduce the documented indicative monthly AWS fixed-cost baseline."""

from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path


HOURS_PER_MONTH = Decimal("730")
EC2_HOURLY_USD = Decimal("0.0896")
GP3_GIB_MONTH_USD = Decimal("0.0912")
PUBLIC_IPV4_HOURLY_USD = Decimal("0.005")
ROUTE53_HOSTED_ZONE_MONTH_USD = Decimal("0.50")
ROOT_VOLUME_GIB = 24
DATA_VOLUME_GIB = 40


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


components = [
    {
        "name": "EC2 t3.large Linux On-Demand",
        "formula": "0.0896 USD/hour * 730 hours",
        "monthly_usd_unrounded": EC2_HOURLY_USD * HOURS_PER_MONTH,
        "source": "https://trucost.cloud/instances/ec2/ap-south-1/t3.large",
        "source_note": "Public AWS list-price index; catalog date 2026-11-22, not an AWS Calculator quote.",
    },
    {
        "name": "Encrypted gp3 root and data volumes",
        "formula": "(24 GiB + 40 GiB) * 0.0912 USD/GiB-month",
        "monthly_usd_unrounded": GP3_GIB_MONTH_USD
        * Decimal(ROOT_VOLUME_GIB + DATA_VOLUME_GIB),
        "source": "https://clowdey.ai/aws-bill/ec2/ebs-volumeusage-gp3/",
        "source_note": "Mumbai public Price List rate, checked 2026-11-03; baseline gp3 performance included.",
    },
    {
        "name": "One attached public IPv4 address",
        "formula": "0.005 USD/hour * 730 hours",
        "monthly_usd_unrounded": PUBLIC_IPV4_HOURLY_USD * HOURS_PER_MONTH,
        "source": "https://aws.amazon.com/vpc/pricing/",
        "source_note": "AWS published in-use public IPv4 hourly rate, accessed 2026-11-28; the attached Elastic IP is the one address counted.",
    },
    {
        "name": "One Route 53 public hosted zone",
        "formula": "0.50 USD/hosted-zone-month",
        "monthly_usd_unrounded": ROUTE53_HOSTED_ZONE_MONTH_USD,
        "source": "https://aws.amazon.com/route53/pricing/",
        "source_note": "AWS first-25-hosted-zone published rate, accessed 2026-11-28.",
    },
]

unrounded_total = sum(
    (component["monthly_usd_unrounded"] for component in components), Decimal("0")
)
for component in components:
    amount = component.pop("monthly_usd_unrounded")
    component["monthly_usd"] = money(amount)

estimate = {
    "generated_date": "2026-11-28",
    "currency": "USD",
    "region": "ap-south-1",
    "estimate_type": "indicative_public_list_price_fixed_baseline",
    "monthly_hours_assumption": str(HOURS_PER_MONTH),
    "included_resources": {
        "ec2": "one Linux shared-tenancy t3.large running for 730 hours",
        "ebs": {
            "root_gp3_gib": ROOT_VOLUME_GIB,
            "persistent_gp3_gib": DATA_VOLUME_GIB,
            "default_iops_and_throughput_only": True,
        },
        "public_ipv4_addresses": 1,
        "route53_public_hosted_zones": 1,
    },
    "components": components,
    "fixed_baseline_monthly_usd": money(unrounded_total),
    "pricing_calculator_used": True,
    "pricing_calculator_cross_check": {
        "service": "AWS Pricing Calculator",
        "url": "https://calculator.aws/",
        "checked_date": "2026-11-28",
        "region": "Asia Pacific (Mumbai) / ap-south-1",
        "assumptions": [
            "one shared Linux t3.large On-Demand instance, 100% utilization, 730 hours/month",
            "64 GiB gp3 EBS per instance, baseline IOPS and throughput, no snapshots",
            "one in-use public IPv4 address and zero idle addresses",
            "one public Route 53 hosted zone, no DNS query volume entered",
        ],
        "displayed_monthly_usd": "75.40",
        "displayed_12_month_usd": "904.80",
        "components_monthly_usd": {
            "ec2": "65.41",
            "gp3_ebs": "5.84",
            "public_ipv4": "3.65",
            "route53_hosted_zone": "0.50",
        },
        "rounding_note": "The calculator rounds displayed components before summing ($75.40); this script sums unrounded list-price inputs before currency rounding ($75.39). The one-cent difference is display rounding.",
        "persistence": "Estimate was reviewed in the public calculator; it was not exported, shared, or attached to an AWS account. No AWS resources were provisioned.",
    },
    "exclusions": [
        "S3 object storage, requests, retrieval and transfer",
        "EBS snapshots and backup retention",
        "CloudWatch log ingestion, retention, metrics, alarms and notifications",
        "internet and cross-region data transfer",
        "domain registration, taxes, support and account-specific credits or discounts",
        "CPU capacity/performance beyond the t3.large Standard-mode baseline",
    ],
    "limitations": [
        "Regional rates were cross-checked against the AWS Pricing Calculator on 2026-11-28; re-check live prices, workload and region before budget approval because rates and usage assumptions can change.",
        "The estimate is an always-on fixed-resource floor, not an all-in bill or production capacity estimate.",
        "Terraform configures t3.large CPU credit mode as Standard to avoid unlimited surplus-credit charges; sustained load beyond its documented baseline can constrain performance.",
        "Actual AWS provisioning and an account-specific AWS plan were not authorized or performed.",
    ],
    "sources": [
        "https://trucost.cloud/instances/ec2/ap-south-1/t3.large",
        "https://clowdey.ai/aws-bill/ec2/ebs-volumeusage-gp3/",
        "https://aws.amazon.com/vpc/pricing/",
        "https://aws.amazon.com/route53/pricing/",
        "https://calculator.aws/",
        "https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html",
    ],
}

output = Path(__file__).with_suffix(".json")
output.write_text(json.dumps(estimate, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {output}; fixed baseline ${estimate['fixed_baseline_monthly_usd']}/month")
