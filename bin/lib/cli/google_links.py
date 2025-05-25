import click

from lib.cli import cli
from lib.lookup_google_links import process_from_athena


@cli.command()
@click.option("--athena-database", default="default", help="Athena database (default: default)")
@click.option("--athena-output-location", help="S3 location for Athena query results")
@click.option(
    "--threads",
    "-t",
    type=int,
    default=5,
    help="Number of worker threads (default: 5)",
)
@click.option(
    "--db",
    "-d",
    required=True,
    help="Path to SQLite database",
)
def lookup_google_links(
    athena_database: str,
    athena_output_location: str,
    threads: int,
    db: str,
):
    """Expand Google shortened URLs from CloudFront logs via Athena.

    Runs the query: SELECT DISTINCT(uri) FROM cloudfront_logs WHERE uri LIKE '/g/%'

    Example:
        ce lookup-google-links --db links.db
    """
    if threads < 1:
        raise click.BadParameter("Number of threads must be at least 1")

    click.echo("Processing Google shortened links from CloudFront logs")
    click.echo(f"Database: {athena_database}")
    if athena_output_location:
        click.echo(f"Output location: {athena_output_location}")
    click.echo(f"Using {threads} worker threads")
    click.echo(f"SQLite database: {db}")
    click.echo("-" * 60)

    process_from_athena(
        db_path=db,
        num_threads=threads,
        athena_database=athena_database,
        athena_output_location=athena_output_location,
    )
