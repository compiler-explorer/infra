from cloudwatch_to_discord import parse_sns_message

EXAMPLE_TRAFFIC_EVENT = dict(
    AlarmName="Traffic",
    AlarmDescription="A high amount of traffic: did we just get slashdotted?",
    AWSAccountId="052730242331",
    NewStateValue="ALARM",
    NewStateReason="Threshold Crossed: 3 out of the last 3 datapoints "
    "[1141.0 (09/10/20 21:24:00), 1226.0 (09/10/20 21:19:00), 1390.0 (09/10/20 21:14:00)] "
    "were greater than or equal to the threshold (30.0) "
    "(minimum 3 datapoints for OK -> ALARM transition).",
    StateChangeTime="2020-10-09T21:32:10.617+0000",
    Region="US East (N. Virginia)",
    AlarmArn="arn:aws:cloudwatch:us-east-1:052730242331:alarm:Traffic",
    OldStateValue="OK",
    Trigger={
        "MetricName": "RequestCount",
        "Namespace": "AWS/ApplicationELB",
        "StatisticType": "Statistic",
        "Statistic": "SUM",
        "Unit": None,
        "Dimensions": [{"value": "app/GccExplorerApp/4a4513393260c7c5", "name": "LoadBalancer"}],
        "Period": 300,
        "EvaluationPeriods": 3,
        "ComparisonOperator": "GreaterThanOrEqualToThreshold",
        "Threshold": 30,
        "TreatMissingData": "- TreatMissingData:                    missing",
        "EvaluateLowSampleCountPercentile": "",
    },
)


EXAMPLE_ANOMALY_EVENT = dict(
    AlarmName="TrafficAnomaly",
    AlarmDescription="A traffic anomaly was detected (too much or too little)",
    AWSAccountId="052730242331",
    NewStateValue="ALARM",
    NewStateReason="Thresholds Crossed: 7 out of the last 10 datapoints were "
    "less than the lower thresholds or greater than the upper thresholds. "
    "Recent datapoints [2246.0 (11/10/20 09:45:00), 2442.0 (11/10/20 09:40:00), "
    "2294.0 (11/10/20 09:35:00), 2393.0 (11/10/20 09:30:00), "
    "2660.0 (11/10/20 09:25:00)] crossed the lower thresholds "
    "[153.14514009861045, 13.94763546927436, -67.59661653399712, "
    "59.31589686034863, -102.53180874192037] or upper thresholds "
    "[2152.153702273202, 2011.8820527416765, 1932.1216878019675, "
    "2059.7204222396495, 1898.7580338483122] (minimum 7 datapoints for "
    "OK -> ALARM transition).",
    StateChangeTime="2020-10-11T09:53:25.070+0000",
    Region="US East (N. Virginia)",
    AlarmArn="arn:aws:cloudwatch:us-east-1:052730242331:alarm:TrafficAnomaly",
    OldStateValue="OK",
    Trigger=dict(
        Period=300,
        EvaluationPeriods=10,
        ComparisonOperator="LessThanLowerOrGreaterThanUpperThreshold",
        ThresholdMetricId="e1",
        TreatMissingData="- TreatMissingData:                    missing",
        EvaluateLowSampleCountPercentile="",
        Metrics=[
            dict(
                Id="m1",
                MetricStat=dict(
                    Metric=dict(
                        Dimensions=[dict(value="app/GccExplorerApp/4a4513393260c7c5", name="LoadBalancer")],
                        MetricName="RequestCount",
                        Namespace="AWS/ApplicationELB",
                    ),
                    Period=300,
                    Stat="Sum",
                ),
                ReturnData=True,
            ),
            dict(Expression="ANOMALY_DETECTION_BAND(m1,5)", Id="e1", Label="RequestCount (Expected)", ReturnData=True),
        ],
    ),
)


def test_can_parse_traffic_event():
    result = parse_sns_message(EXAMPLE_TRAFFIC_EVENT)
    assert result["embeds"][0]["title"] == "CloudWatch Alert - Traffic!"


def test_can_parse_anomaly_event():
    result = parse_sns_message(EXAMPLE_ANOMALY_EVENT)
    assert result["embeds"][0]["title"] == "CloudWatch Alert - TrafficAnomaly!"
    import json

    print(json.dumps(result))
