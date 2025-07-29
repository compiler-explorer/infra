"""CLI commands for compiler routing management."""

import logging
from typing import Optional

import click

from lib.ce_utils import are_you_sure
from lib.cli import cli
from lib.compiler_routing import (
    CompilerRoutingError,
    batch_delete_items,
    create_composite_key,
    get_current_routing_table,
    get_routing_table_stats,
    lookup_compiler_queue,
    lookup_compiler_routing,
    migrate_legacy_entries,
    update_compiler_routing_table,
)
from lib.env import Config, Environment

LOGGER = logging.getLogger(__name__)


@cli.group(name="compiler-routing")
def compiler_routing():
    """Manage compiler to queue routing mappings."""
    pass


@compiler_routing.command(name="update")
@click.option("--env", "environment", help="Environment to update (default: current environment)")
@click.option("--dry-run", is_flag=True, help="Show what would be changed without making changes")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def update_routing(cfg: Config, environment: Optional[str], dry_run: bool, skip_confirmation: bool):
    """Update compiler routing table for specified environment using live API data."""
    try:
        # Use current environment if not specified
        target_env = environment or cfg.env.value
        
        # Validate environment
        try:
            Environment(target_env)
        except ValueError:
            print(f"Invalid environment: {target_env}")
            valid_envs = [env.value for env in Environment]
            print(f"Valid environments: {', '.join(valid_envs)}")
            return
        
        if not dry_run and not skip_confirmation:
            action = "dry-run update" if dry_run else "update"
            if not are_you_sure(f"{action} compiler routing table for {target_env}", cfg):
                return
        
        print(f"Updating compiler routing table for {target_env}...")
        print(f"Fetching compiler data from live API...")
        if dry_run:
            print("DRY RUN - No changes will be made")
        
        result = update_compiler_routing_table(target_env, dry_run=dry_run)
        
        print(f"\nResults for {target_env}:")
        print(f"  Added: {result['added']} compilers")
        print(f"  Updated: {result['updated']} compilers") 
        print(f"  Deleted: {result['deleted']} compilers")
        
        if not dry_run:
            print(f"\n✅ Successfully updated compiler routing table for {target_env}")
        
    except CompilerRoutingError as e:
        print(f"❌ Compiler routing error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        LOGGER.error(f"Error updating compiler routing: {e}", exc_info=True)


@compiler_routing.command(name="status")
@click.pass_obj
def routing_status(cfg: Config):
    """Show current compiler routing table statistics."""
    try:
        print("Compiler Routing Table Status\n" + "=" * 32)
        
        stats = get_routing_table_stats()
        
        print(f"Total compilers: {stats['total_compilers']}")
        print(f"Environments: {stats['environment_count']}")
        print(f"  - {', '.join(stats['environments'])}")
        
        print("\nRouting Types:")
        routing_types = stats.get('routing_types', {})
        for routing_type, count in sorted(routing_types.items()):
            print(f"  {routing_type}: {count} compilers")
        
        print("\nQueue Distribution:")
        for queue_name, count in sorted(stats['queue_distribution'].items()):
            print(f"  {queue_name}: {count} compilers")
        
    except CompilerRoutingError as e:
        print(f"❌ Compiler routing error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        LOGGER.error(f"Error getting routing status: {e}", exc_info=True)


@compiler_routing.command(name="lookup")
@click.argument("compiler_id", required=True)
@click.pass_obj
def lookup_compiler(cfg: Config, compiler_id: str):
    """Look up queue assignment for a specific compiler."""
    try:
        environment = cfg.env.value
        print(f"Looking up routing for compiler: {compiler_id} in environment: {environment}")
        
        routing_info = lookup_compiler_routing(compiler_id, environment)
        
        if routing_info:
            routing_type = routing_info.get("routingType", "queue")
            found_environment = routing_info.get("environment", "unknown")
            
            print(f"✅ Compiler '{compiler_id}' found:")
            print(f"   Environment: {found_environment}")
            print(f"   Routing Type: {routing_type}")
            
            if routing_type == "queue":
                queue_name = routing_info.get("queueName", "")
                print(f"   Queue: {queue_name}")
            elif routing_type == "url":
                target_url = routing_info.get("targetUrl", "")
                print(f"   Target URL: {target_url}")
            
            # Warn if found in different environment than expected
            if found_environment != environment and found_environment != "unknown":
                print(f"   ⚠️  Warning: Found in {found_environment}, but looking in {environment}")
        else:
            print(f"❌ Compiler '{compiler_id}' not found in routing table for environment: {environment}")
            print("   This compiler will use the default queue routing")
        
    except CompilerRoutingError as e:
        print(f"❌ Compiler routing error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        LOGGER.error(f"Error looking up compiler: {e}", exc_info=True)


@compiler_routing.command(name="validate")
@click.option("--env", "environment", help="Environment to validate (default: all environments)")
@click.pass_obj
def validate_routing(cfg: Config, environment: Optional[str]):
    """Validate routing table consistency against live API data."""
    try:
        print("Compiler Routing Validation\n" + "=" * 28)
        
        # Get current table stats
        stats = get_routing_table_stats()
        
        if environment:
            environments_to_check = [environment]
            # Validate environment
            try:
                Environment(environment)
            except ValueError:
                print(f"Invalid environment: {environment}")
                return
        else:
            environments_to_check = stats['environments']
        
        print(f"Validating environments: {', '.join(environments_to_check)}")
        
        validation_issues = []
        
        for env in environments_to_check:
            try:
                print(f"\nValidating {env}...")
                
                # Perform dry-run update to see what would change
                result = update_compiler_routing_table(env, dry_run=True)
                
                total_changes = result['added'] + result['updated'] + result['deleted']
                
                if total_changes == 0:
                    print(f"  ✅ {env}: No changes needed (table is up to date)")
                else:
                    print(f"  ⚠️  {env}: {total_changes} changes needed")
                    print(f"     - {result['added']} to add")
                    print(f"     - {result['updated']} to update") 
                    print(f"     - {result['deleted']} to delete")
                    validation_issues.append(env)
                    
            except CompilerRoutingError as e:
                print(f"  ❌ {env}: Validation failed - {e}")
                validation_issues.append(env)
        
        print(f"\nValidation Summary:")
        if validation_issues:
            print(f"❌ Issues found in {len(validation_issues)} environment(s): {', '.join(validation_issues)}")
            print("Run 'ce compiler-routing update --env <env>' to fix issues")
        else:
            print("✅ All environments are up to date")
        
    except CompilerRoutingError as e:
        print(f"❌ Compiler routing error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        LOGGER.error(f"Error validating routing: {e}", exc_info=True)


@compiler_routing.command(name="clear")
@click.option("--env", "environment", required=True, help="Environment to clear routing entries for")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def clear_routing(cfg: Config, environment: str, skip_confirmation: bool):
    """Clear routing entries for a specific environment."""
    try:
        # Validate environment
        try:
            Environment(environment)
        except ValueError:
            print(f"Invalid environment: {environment}")
            valid_envs = [env.value for env in Environment]
            print(f"Valid environments: {', '.join(valid_envs)}")
            return
        
        # Get current stats to show what will be deleted
        current_table = get_current_routing_table(environment)
        
        # Count entries for this environment (all entries since we filtered by environment)
        env_entries = list(current_table.keys())
        
        if not env_entries:
            print(f"No routing entries found for environment: {environment}")
            return
        
        print(f"Found {len(env_entries)} routing entries for {environment}")
        
        if not skip_confirmation:
            print(f"\n⚠️  WARNING: This will delete all routing entries for {environment}")
            print("Affected compilers will fall back to default queue routing")
            if not are_you_sure(f"clear routing entries for {environment}", cfg):
                return
        
        # Use batch delete to remove entries (need composite keys)
        composite_keys = {data.get("compositeKey", create_composite_key(environment, compiler_id)) 
                         for compiler_id, data in current_table.items()}
        batch_delete_items(composite_keys)
        
        print(f"✅ Successfully cleared {len(env_entries)} routing entries for {environment}")
        
    except CompilerRoutingError as e:
        print(f"❌ Compiler routing error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        LOGGER.error(f"Error clearing routing: {e}", exc_info=True)


@compiler_routing.command(name="migrate")
@click.option("--skip-confirmation", is_flag=True, help="Skip confirmation prompt")
@click.pass_obj
def migrate_legacy_data(cfg: Config, skip_confirmation: bool):
    """Migrate legacy routing entries to environment-prefixed composite keys."""
    try:
        print("Compiler Routing Migration\n" + "=" * 26)
        print("This will migrate legacy routing entries to use environment-prefixed composite keys.")
        print("Legacy entries will be converted from 'compiler-id' to 'environment#compiler-id' format.")
        
        if not skip_confirmation:
            print("\n⚠️  WARNING: This operation will modify the DynamoDB table structure.")
            print("Make sure you have a backup of the table before proceeding.")
            if not are_you_sure("migrate legacy routing entries", cfg):
                return
        
        print("Starting migration of legacy entries...")
        
        result = migrate_legacy_entries()
        
        print(f"\nMigration Results:")
        print(f"  Migrated: {result['migrated']} entries")
        print(f"  Skipped: {result['skipped']} entries (unknown environments)")
        print(f"  Errors: {result['errors']} entries")
        
        if result['errors'] > 0:
            print(f"\n⚠️  {result['errors']} entries failed to migrate - check logs for details")
        elif result['migrated'] == 0:
            print("\n✅ No legacy entries found - table is already using composite keys")
        else:
            print(f"\n✅ Successfully migrated {result['migrated']} legacy entries to composite key format")
        
    except CompilerRoutingError as e:
        print(f"❌ Compiler routing error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        LOGGER.error(f"Error migrating legacy data: {e}", exc_info=True)