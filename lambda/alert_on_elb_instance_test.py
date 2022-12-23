from alert_on_elb_instance import parse_sns_message, Reason

UNHEALTHY_EVENT = dict(
    Origin="AutoScalingGroup",
    Destination="EC2",
    Progress=50,
    AccountId="052730242331",
    Description="Terminating EC2 instance: i-016dea8095930f564",
    RequestId="f5061501-6dab-c119-7e0f-d4c4794b5075",
    EndTime="2022-12-23T19:05:15.651Z",
    AutoScalingGroupARN="blahblashblah:autoScalingGroupName/staging",
    ActivityId="f5061501-6dab-c119-7e0f-d4c4794b5075",
    StartTime="2022-12-23T19:00:11.120Z",
    Service="AWS Auto Scaling",
    Time="2022-12-23T19:05:15.651Z",
    EC2InstanceId="i-016dea8095930f564",
    StatusCode="InProgress",
    StatusMessage="",
    Details={"Subnet ID": "subnet-0b7ecd0395d5f2cc9", "Availability Zone": "us-east-1f"},
    AutoScalingGroupName="staging",
    Cause="At 2022-12-23T19:00:11Z an instance was taken out of service in response to an ELB system health check failure.",
    Event="autoscaling:EC2_INSTANCE_TERMINATE",
)

SCALING_EVENT = dict(
    Origin="AutoScalingGroup",
    Destination="EC2",
    Progress=50,
    AccountId="052730242331",
    Description="Terminating EC2 instance: i-0d1835f80668172d7",
    RequestId="433c452a-a0e7-4dde-b1b5-21780c03821d",
    EndTime="2022-12-23T19:17:20.123Z",
    AutoScalingGroupARN="arn:aws:blah:autoScalingGroupName/prod",
    ActivityId="433c452a-a0e7-4dde-b1b5-21780c03821d",
    StartTime="2022-12-23T19:12:10.234Z",
    Service="AWS Auto Scaling",
    Time="2022-12-23T19:17:20.123Z",
    EC2InstanceId="i-0d1835f80668172d7",
    StatusCode="InProgress",
    StatusMessage="",
    Details={
        "Subnet ID": "subnet-1df1e135",
        "Availability Zone": "us-east-1d",
        "InvokingAlarms": [
            dict(
                AlarmArn="arn:blah-408b-b787-b01c939e9da1",
                Trigger=dict(
                    MetricName="CPUUtilization",
                    EvaluateLowSampleCountPercentile="",
                    ComparisonOperator="LessThanThreshold",
                    TreatMissingData="",
                    Statistic="AVERAGE",
                    StatisticType="Statistic",
                    Period=60,
                    EvaluationPeriods=15,
                    Unit=None,
                    Namespace="AWS/EC2",
                    Threshold=42.5,
                ),
                AlarmName="TargetTracking-prod-AlarmLow-a83afbd9-b74b-408b-b787-b01c939e9da1",
                AlarmDescription="DO NOT EDIT OR DELETE. For TargetTrackingScaling policy arn:aws:autoscaling:us-east-1:052730242331:scalingPolicy:e0c81289-89ca-432f-9b06-2a6e0ae78741:autoScalingGroupName/prod:policyName/cpu-tracker.",
                AWSAccountId="052730242331",
                OldStateValue="ALARM",
                Region="US East (N. Virginia)",
                NewStateValue="ALARM",
                AlarmConfigurationUpdatedTimestamp=1671820750666,
                StateChangeTime=1671821766263,
            )
        ],
    },
    AutoScalingGroupName="prod",
    Cause="At 2022-12-23T19:12:06Z a monitor alarm TargetTracking-prod-AlarmLow-a83afbd9-b74b-408b-b787-b01c939e9da1 in state ALARM triggered policy cpu-tracker changing the desired capacity from 7 to 6.  At 2022-12-23T19:12:09Z an instance was taken out of service in response to a difference between desired and actual capacity, shrinking the capacity from 7 to 6.  At 2022-12-23T19:12:10Z instance i-0d1835f80668172d7 was selected for termination.",
    Event="autoscaling:EC2_INSTANCE_TERMINATE",
)


def test_can_parse_unhealthy_event():
    result = parse_sns_message(UNHEALTHY_EVENT)
    assert result.reason == Reason.FailedHealthCheck
    assert result.environment == "staging"
    assert result.instance == "i-016dea8095930f564"


def test_can_parse_scaling_event():
    result = parse_sns_message(SCALING_EVENT)
    assert result.reason == Reason.ScaledDown
    assert result.environment == "prod"
    assert result.instance == "i-0d1835f80668172d7"
