import boto3
import os

from lib.cli import cli


@cli.group()
def compiler_stats():
    """Compiler stats things"""


@compiler_stats.command(name="update")
def compiler_stats_update():
    """Queries Athena for Compiler statistics and updates the public CSV."""
    client = boto3.client("athena")

    fields = "count(*) as times_used, min(time) as first_used, max(time) as last_used, split_part(request_url, '/', 6) as compiler"
    request_url = "https://%:443/api/compiler/%/compile"
    where = f"WHERE request_url like '{request_url}'"
    group_by = "GROUP BY split_part(request_url, '/', 6)"
    order_by = "ORDER BY count(*) DESC"

    response = client.start_query_execution(
        QueryString=f"SELECT {fields} FROM alb_logs {where} {group_by} {order_by};",
        QueryExecutionContext={"Database": "default"},
        ResultConfiguration={
            "OutputLocation": "s3://compiler-explorer/public/",
        },
        WorkGroup="primary",
    )

    query_execution_id = response["QueryExecutionId"]

    status = "QUEUED"
    while status in ["QUEUED", "RUNNING"]:
        response = client.get_query_execution(QueryExecutionId=query_execution_id)
        status = response["QueryExecution"]["Status"]["State"]

    if status == "SUCCEEDED":
        query_csv_url = f"s3://compiler-explorer/public/{query_execution_id}.csv"
        query_meta_url = f"s3://compiler-explorer/public/{query_execution_id}.csv.metadata"
        usage_csv_url = "s3://compiler-explorer/public/compiler_usage.csv"

        os.system(f'aws s3 cp --acl public-read "{query_csv_url}" "{usage_csv_url}"')
        os.system(f'aws s3 rm "{query_meta_url}"')
        os.system(f'aws s3 rm "{query_csv_url}"')

        print("Ok")
    else:
        print(status)
