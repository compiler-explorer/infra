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
    serverurl = 'conan.compiler-explorer.com'
    requesturl = 'https://conan.compiler-explorer.com:1443/v1/conans/%/download_urls'
    where = f'WHERE domain_name=\'{serverurl}\' and request_url like \'{requesturl}\''
    groupby = 'GROUP BY split_part(request_url, \'/\', 6), split_part(request_url, \'/\', 7)'
    orderby = 'ORDER BY count(*) DESC'

    response = client.start_query_execution(
        QueryString=f'SELECT {fields} FROM alb_logs {where} {groupby} {orderby};',
        QueryExecutionContext={
            'Database': 'default'
        },
        ResultConfiguration={
            'OutputLocation': 's3://compiler-explorer/public/',
        },
        WorkGroup='primary'
    )

    queryExecutionId = response['QueryExecutionId']

    status = 'QUEUED'
    while status in ['QUEUED', 'RUNNING']:
        response = client.get_query_execution(
            QueryExecutionId=queryExecutionId)
        status = response['QueryExecution']['Status']['State']

    if status == 'SUCCEEDED':
        querycsvurl = f's3://compiler-explorer/public/{queryExecutionId}.csv'
        querymetaurl = f's3://compiler-explorer/public/{queryExecutionId}.csv.metadata'
        pubcsvurl = 's3://compiler-explorer/public/library_usage.csv'

        os.system(
            f'aws s3 cp --acl public-read "{querycsvurl}" "{pubcsvurl}"')
        os.system(f'aws s3 rm "{querymetaurl}"')
        os.system(f'aws s3 rm "{querycsvurl}"')

        print('Ok')
    else:
        print(status)
