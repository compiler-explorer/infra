import boto3
import os

from lib.cli import cli


@cli.group()
def library_stats():
    """Library stats things"""


@library_stats.command(name='update')
def library_stats_update():
    """Queries Athena for Library statistics and updates the public CSV."""
    client = boto3.client('athena')

    fields = 'count(*) as times_used, min(time) as first_used, max(time) as last_used, split_part(request_url, \'/\', 6) as library, split_part(request_url, \'/\', 7) as library_version'
    server_url = 'conan.compiler-explorer.com'
    request_url = 'https://conan.compiler-explorer.com:1443/v1/conans/%/download_urls'
    where = f'WHERE domain_name=\'{server_url}\' and request_url like \'{request_url}\''
    group_by = 'GROUP BY split_part(request_url, \'/\', 6), split_part(request_url, \'/\', 7)'
    order_by = 'ORDER BY count(*) DESC'

    response = client.start_query_execution(
        QueryString=f'SELECT {fields} FROM alb_logs {where} {group_by} {order_by};',
        QueryExecutionContext={
            'Database': 'default'
        },
        ResultConfiguration={
            'OutputLocation': 's3://compiler-explorer/public/',
        },
        WorkGroup='primary'
    )

    query_execution_id = response['QueryExecutionId']

    status = 'QUEUED'
    while status in ['QUEUED', 'RUNNING']:
        response = client.get_query_execution(
            QueryExecutionId=query_execution_id)
        status = response['QueryExecution']['Status']['State']

    if status == 'SUCCEEDED':
        query_csv_url = f's3://compiler-explorer/public/{query_execution_id}.csv'
        query_meta_url = f's3://compiler-explorer/public/{query_execution_id}.csv.metadata'
        library_usage_csv_url = 's3://compiler-explorer/public/library_usage.csv'

        os.system(
            f'aws s3 cp --acl public-read "{query_csv_url}" "{library_usage_csv_url}"')
        os.system(f'aws s3 rm "{query_meta_url}"')
        os.system(f'aws s3 rm "{query_csv_url}"')

        print('Ok')
    else:
        print(status)
