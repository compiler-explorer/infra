from __future__ import annotations

import os

import boto3

from lib.cli import cli


@cli.group()
def library_stats():
    """Library stats things"""


@library_stats.command(name="update")
def library_stats_update():
    """Queries Athena for Library statistics and updates the public CSV."""
    client = boto3.client("athena")

    # Conan traffic moved behind CloudFront (and a dedicated internal ALB) in #1868, so it no longer
    # appears in alb_logs. CloudFront logs split the URL into host_header + a path-only uri, hence the
    # split_part indices differ from the old full-URL query.
    fields = "count(*) as times_used, min(date) as first_used, max(date) as last_used, split_part(uri, '/', 4) as library, split_part(uri, '/', 5) as library_version"
    server_host = "conan.compiler-explorer.com"
    where = f"WHERE host_header='{server_host}' and uri like '/v1/conans/%/download_urls'"
    group_by = "GROUP BY split_part(uri, '/', 4), split_part(uri, '/', 5)"
    order_by = "ORDER BY count(*) DESC"

    response = client.start_query_execution(
        QueryString=f"SELECT {fields} FROM cloudfront_logs {where} {group_by} {order_by};",
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
        library_usage_csv_url = "s3://compiler-explorer/public/library_usage.csv"

        os.system(f'aws s3 cp --acl public-read "{query_csv_url}" "{library_usage_csv_url}"')
        os.system(f'aws s3 rm "{query_meta_url}"')
        os.system(f'aws s3 rm "{query_csv_url}"')

        print("Ok")
    else:
        print(status)
