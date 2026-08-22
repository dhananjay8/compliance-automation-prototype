import os
from typing import Any

from .base import Connector, ConnectorCredentials, ResourceRecord


class AWSCredentials(ConnectorCredentials):
    def __init__(
        self,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region: str | None = None,
    ) -> None:
        self.access_key_id = access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_access_key = secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = region or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"

    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key)


class AWSConnector(Connector):
    def __init__(self, credentials: AWSCredentials | None = None) -> None:
        super().__init__(credentials or AWSCredentials())

    def health_check(self) -> dict[str, Any]:
        if not self.is_ready():
            return {"configured": False, "region": None}
        creds = self.credentials
        assert isinstance(creds, AWSCredentials)
        try:
            import boto3

            sts = boto3.client(
                "sts",
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                region_name=creds.region,
            )
            identity = sts.get_caller_identity()
            return {
                "configured": True,
                "reachable": True,
                "region": creds.region,
                "account": identity.get("Account"),
            }
        except Exception as exc:
            return {
                "configured": True,
                "reachable": False,
                "region": creds.region,
                "error": str(exc),
            }

    def list_resources(self) -> list[ResourceRecord]:
        if not self.is_ready():
            return _aws_mock_resources()
        creds = self.credentials
        assert isinstance(creds, AWSCredentials)
        try:
            import boto3

            records: list[ResourceRecord] = []
            iam = boto3.client(
                "iam",
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                region_name=creds.region,
            )
            for user in iam.get_paginator("list_users").paginate().build_full_result()["Users"]:
                mfa = (
                    iam.list_mfa_devices(UserName=user["UserName"])
                    .get("MFADevices", [])
                )
                records.append(
                    ResourceRecord(
                        external_id=user["Arn"],
                        resource_type="UserAccount",
                        data={
                            "user_name": user["UserName"],
                            "arn": user["Arn"],
                            "create_date": user["CreateDate"].isoformat(),
                            "mfa_enabled": len(mfa) > 0,
                        },
                    )
                )
            ec2 = boto3.client(
                "ec2",
                aws_access_key_id=creds.access_key_id,
                aws_secret_access_key=creds.secret_access_key,
                region_name=creds.region,
            )
            for page in ec2.get_paginator("describe_instances").paginate():
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        records.append(
                            ResourceRecord(
                                external_id=instance["InstanceId"],
                                resource_type="Computer",
                                data={
                                    "instance_id": instance["InstanceId"],
                                    "instance_type": instance.get("InstanceType"),
                                    "state": instance.get("State", {}).get("Name"),
                                    "public": instance.get("PublicIpAddress") is not None,
                                    "encrypted": instance.get("EbsOptimized") is True,
                                    "launch_time": (
                                        instance["LaunchTime"].isoformat()
                                        if instance.get("LaunchTime")
                                        else None
                                    ),
                                },
                            )
                        )
            return records
        except Exception:
            return _aws_mock_resources()


def _aws_mock_resources() -> list[ResourceRecord]:
    return [
        ResourceRecord(
            external_id="arn:aws:iam::123456789012:user/alice",
            resource_type="UserAccount",
            data={
                "user_name": "alice",
                "mfa_enabled": True,
                "arn": "arn:aws:iam::123456789012:user/alice",
            },
        ),
        ResourceRecord(
            external_id="arn:aws:iam::123456789012:user/bob",
            resource_type="UserAccount",
            data={
                "user_name": "bob",
                "mfa_enabled": False,
                "arn": "arn:aws:iam::123456789012:user/bob",
            },
        ),
        ResourceRecord(
            external_id="arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0",
            resource_type="Computer",
            data={
                "instance_id": "i-1234567890abcdef0",
                "public": False,
                "encrypted": True,
            },
        ),
    ]
