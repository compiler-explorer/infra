import click

from lib.cli import cli
from lib.lookup_google_links import process_csv


@cli.command()
@click.argument("csv_file", type=click.Path(exists=True))
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
def lookup_google_links(csv_file: str, threads: int, db: str):
    """Expand Google shortened URLs from a CSV file."""
    if threads < 1:
        raise click.BadParameter("Number of threads must be at least 1")

    click.echo(f"Processing Google shortened links from: {csv_file}")
    click.echo(f"Using {threads} worker threads")
    click.echo(f"Database: {db}")
    click.echo("-" * 60)

    process_csv(csv_file, db, threads)
