"""CLI commands for API key management."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
import configparser

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from src.auth.api_key_service import (
    APIKeyService,
    APIKeyNotFoundError,
    APIKeyValidationError,
)
from src.database.connection import DatabaseConnection
from src.database.operations import APIKeyDatabaseOperations


console = Console()


def get_auth_config() -> Optional[dict]:
    """Get authentication configuration."""
    # Check environment variable first
    user_id = os.environ.get("HOKUSAI_USER_ID")
    api_endpoint = os.environ.get("HOKUSAI_API_ENDPOINT", "http://localhost:8000")
    
    if user_id:
        return {
            "user_id": user_id,
            "api_endpoint": api_endpoint
        }
    
    # Check config file
    config_file = Path.home() / ".hokusai" / "config"
    if config_file.exists():
        config = configparser.ConfigParser()
        config.read(config_file)
        
        if "default" in config:
            return {
                "user_id": config["default"].get("user_id"),
                "api_endpoint": config["default"].get("api_endpoint", "http://localhost:8000")
            }
    
    return None


def get_api_key_service() -> APIKeyService:
    """Get API key service instance."""
    db_conn = DatabaseConnection()
    db_ops = APIKeyDatabaseOperations(db_conn)
    return APIKeyService(db_ops)


@click.group()
def auth_group():
    """Manage API keys for Hokusai ML Platform."""
    pass


@auth_group.command("create-key")
@click.option("--name", required=True, help="Name for the API key")
@click.option("--environment", default="production", 
              type=click.Choice(["production", "test", "development"]),
              help="Environment for the API key")
@click.option("--rate-limit", default=1000, type=int,
              help="Rate limit per hour")
@click.option("--expires-in-days", type=int,
              help="Number of days until key expires")
@click.option("--allowed-ip", multiple=True,
              help="IP addresses allowed to use this key (can be specified multiple times)")
def create_key(
    name: str,
    environment: str,
    rate_limit: int,
    expires_in_days: Optional[int],
    allowed_ip: tuple
):
    """Create a new API key."""
    try:
        # Get auth config
        config = get_auth_config()
        if not config or not config.get("user_id"):
            console.print("[red]Error:[/red] Authentication not configured.")
            console.print("Set HOKUSAI_USER_ID environment variable or run 'hokusai auth login'")
            raise click.Abort()
        
        # Get service
        service = get_api_key_service()
        
        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now() + timedelta(days=expires_in_days)
        
        # Convert allowed IPs
        allowed_ips = list(allowed_ip) if allowed_ip else None
        
        # Create API key
        with console.status("Creating API key..."):
            api_key = service.generate_api_key(
                user_id=config["user_id"],
                key_name=name,
                environment=environment,
                expires_at=expires_at,
                rate_limit_per_hour=rate_limit,
                allowed_ips=allowed_ips
            )
        
        # Display success message
        console.print("\n[green]✓[/green] API key created successfully!\n")
        
        # Create formatted panel with key details
        content = f"""[bold cyan]API Key:[/bold cyan] [yellow]{api_key.key}[/yellow]

[bold]Save this key securely. It will not be shown again.[/bold]

[bold]API Key Details:[/bold]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Key ID:      {api_key.key_id}
Name:        {api_key.name}
Environment: {environment}
Created:     {api_key.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"""
        
        if api_key.expires_at:
            content += f"\nExpires:     {api_key.expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        
        if rate_limit != 1000:
            content += f"\nRate Limit:  {rate_limit}/hour"
        
        if allowed_ips:
            content += f"\nAllowed IPs: {', '.join(allowed_ips)}"
        
        panel = Panel(content, title="New API Key", border_style="green", box=box.ROUNDED)
        console.print(panel)
        
    except Exception as e:
        console.print(f"[red]Error creating API key:[/red] {str(e)}")
        raise click.Abort()


@auth_group.command("list-keys")
@click.option("--active-only", is_flag=True, help="Show only active keys")
def list_keys(active_only: bool):
    """List your API keys."""
    try:
        # Get auth config
        config = get_auth_config()
        if not config or not config.get("user_id"):
            console.print("[red]Error:[/red] Authentication not configured.")
            raise click.Abort()
        
        # Get service
        service = get_api_key_service()
        
        # List keys
        with console.status("Fetching API keys..."):
            keys = service.list_api_keys(config["user_id"], active_only=active_only)
        
        if not keys:
            console.print("\n[yellow]No API keys found.[/yellow]")
            return
        
        # Create table
        table = Table(title=f"\nAPI Keys ({len(keys)} total)", box=box.ROUNDED)
        table.add_column("Key ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Prefix", style="yellow")
        table.add_column("Created", style="blue")
        table.add_column("Last Used", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Expires", style="red")
        
        for key in keys:
            # Format dates
            created = key.created_at.strftime('%Y-%m-%d')
            last_used = key.last_used_at.strftime('%Y-%m-%d %H:%M') if key.last_used_at else "Never"
            expires = key.expires_at.strftime('%Y-%m-%d') if key.expires_at else "-"
            
            # Determine status
            if not key.is_active:
                status = "[red]Inactive[/red]"
            elif key.expires_at and key.expires_at < datetime.now():
                status = "[red]Expired[/red]"
            else:
                status = "[green]Active[/green]"
            
            table.add_row(
                key.key_id[:8] + "...",
                key.name,
                key.key_prefix,
                created,
                last_used,
                status,
                expires
            )
        
        console.print(table)
        console.print(f"\n[dim]Total: {len(keys)} keys[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error listing API keys:[/red] {str(e)}")
        raise click.Abort()


@auth_group.command("revoke-key")
@click.argument("key_id")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def revoke_key(key_id: str, force: bool):
    """Revoke an API key."""
    try:
        # Get auth config
        config = get_auth_config()
        if not config or not config.get("user_id"):
            console.print("[red]Error:[/red] Authentication not configured.")
            raise click.Abort()
        
        # Confirm unless forced
        if not force:
            if not click.confirm(f"Are you sure you want to revoke API key {key_id}?"):
                console.print("Revocation cancelled.")
                return
        
        # Get service
        service = get_api_key_service()
        
        # Revoke key
        with console.status("Revoking API key..."):
            service.revoke_api_key(config["user_id"], key_id)
        
        console.print(f"\n[green]✓[/green] API key revoked successfully.")
        
    except APIKeyNotFoundError:
        console.print(f"[red]Error:[/red] API key not found: {key_id}")
        raise click.Abort()
    except APIKeyValidationError:
        console.print(f"[red]Error:[/red] You don't have permission to revoke this key.")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Error revoking API key:[/red] {str(e)}")
        raise click.Abort()


@auth_group.command("rotate-key")
@click.argument("key_id")
def rotate_key(key_id: str):
    """Rotate an API key (revoke old, create new with same settings)."""
    try:
        # Get auth config
        config = get_auth_config()
        if not config or not config.get("user_id"):
            console.print("[red]Error:[/red] Authentication not configured.")
            raise click.Abort()
        
        # Confirm
        if not click.confirm(f"This will revoke the old key and create a new one. Continue?"):
            console.print("Rotation cancelled.")
            return
        
        # Get service
        service = get_api_key_service()
        
        # Rotate key
        with console.status("Rotating API key..."):
            new_key = service.rotate_api_key(config["user_id"], key_id)
        
        # Display new key
        console.print("\n[green]✓[/green] API key rotated successfully!\n")
        
        content = f"""[bold cyan]New API Key:[/bold cyan] [yellow]{new_key.key}[/yellow]

[bold]Save this new key securely. The old key has been revoked.[/bold]

Key ID: {new_key.key_id}
Name:   {new_key.name}"""
        
        panel = Panel(content, title="Rotated API Key", border_style="green", box=box.ROUNDED)
        console.print(panel)
        
    except APIKeyNotFoundError:
        console.print(f"[red]Error:[/red] API key not found: {key_id}")
        raise click.Abort()
    except APIKeyValidationError:
        console.print(f"[red]Error:[/red] You don't have permission to rotate this key.")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Error rotating API key:[/red] {str(e)}")
        raise click.Abort()


# Add commands to the auth group
if __name__ == "__main__":
    auth_group()