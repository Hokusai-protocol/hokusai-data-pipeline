"""CLI commands for API key management using external auth service."""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import configparser

import click
import requests
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


def get_auth_config() -> Dict[str, str]:
    """Get authentication configuration."""
    # Get auth service URL
    auth_service_url = os.environ.get("HOKUSAI_AUTH_SERVICE_URL", "https://auth.hokus.ai")
    
    # Get admin token for key management
    admin_token = os.environ.get("HOKUSAI_ADMIN_TOKEN")
    
    # Get user's own API key
    api_key = os.environ.get("HOKUSAI_API_KEY")
    
    # Check config file for additional settings
    config_file = Path.home() / ".hokusai" / "config"
    if config_file.exists():
        config = configparser.ConfigParser()
        config.read(config_file)
        
        if "default" in config:
            if not admin_token:
                admin_token = config["default"].get("admin_token")
            if not api_key:
                api_key = config["default"].get("api_key")
            if not auth_service_url:
                auth_service_url = config["default"].get("auth_service_url", auth_service_url)
    
    return {
        "auth_service_url": auth_service_url,
        "admin_token": admin_token,
        "api_key": api_key
    }


def make_auth_request(
    method: str,
    endpoint: str,
    token: str,
    json_data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None
) -> requests.Response:
    """Make authenticated request to auth service."""
    config = get_auth_config()
    url = f"{config['auth_service_url']}{endpoint}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=json_data,
            params=params,
            timeout=10
        )
        return response
    except requests.exceptions.ConnectionError:
        console.print(f"[red]Error:[/red] Could not connect to auth service at {config['auth_service_url']}")
        raise click.Abort()
    except requests.exceptions.Timeout:
        console.print("[red]Error:[/red] Auth service request timed out")
        raise click.Abort()


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
@click.option("--scope", multiple=True, default=["model:read", "model:write", "mlflow:access"],
              help="Scopes for the API key (can be specified multiple times)")
def create_key(
    name: str,
    environment: str,
    rate_limit: int,
    expires_in_days: Optional[int],
    allowed_ip: tuple,
    scope: tuple
):
    """Create a new API key."""
    config = get_auth_config()
    
    if not config.get("admin_token"):
        console.print("[red]Error:[/red] Admin token required to create API keys.")
        console.print("Set HOKUSAI_ADMIN_TOKEN environment variable or add to ~/.hokusai/config")
        raise click.Abort()
    
    # Prepare request data
    data = {
        "name": name,
        "service_id": "ml-platform",
        "environment": environment,
        "rate_limit_per_hour": rate_limit,
        "scopes": list(scope)
    }
    
    if expires_in_days:
        expires_at = datetime.now().isoformat() + f"+{expires_in_days}d"
        data["expires_at"] = expires_at
    
    if allowed_ip:
        data["allowed_ips"] = list(allowed_ip)
    
    # Create key via auth service
    try:
        response = make_auth_request(
            method="POST",
            endpoint="/api/v1/keys",
            token=config["admin_token"],
            json_data=data
        )
        
        if response.status_code == 201:
            result = response.json()
            
            # Display the created key
            console.print("\n[green]✓[/green] API key created successfully!\n")
            
            panel = Panel(
                f"[bold cyan]{result['api_key']}[/bold cyan]",
                title="Your API Key",
                subtitle="[red]Save this key - it won't be shown again![/red]",
                box=box.DOUBLE
            )
            console.print(panel)
            
            # Show key details
            console.print("\n[bold]Key Details:[/bold]")
            console.print(f"  ID: {result['key_id']}")
            console.print(f"  Name: {name}")
            console.print(f"  Environment: {environment}")
            console.print(f"  Rate Limit: {rate_limit}/hour")
            if expires_in_days:
                console.print(f"  Expires: In {expires_in_days} days")
            if allowed_ip:
                console.print(f"  Allowed IPs: {', '.join(allowed_ip)}")
            console.print(f"  Scopes: {', '.join(scope)}")
            
            # Show how to use it
            console.print("\n[bold]To use this key:[/bold]")
            console.print(f"  export HOKUSAI_API_KEY={result['api_key']}")
            console.print("  # Or add to your Python code:")
            console.print("  from hokusai import setup")
            console.print(f"  setup(api_key='{result['api_key']}')")
            
        else:
            console.print(f"[red]Error:[/red] Failed to create API key: {response.text}")
            raise click.Abort()
            
    except Exception as e:
        if not isinstance(e, click.Abort):
            console.print(f"[red]Error:[/red] {str(e)}")
            raise click.Abort()
        raise


@auth_group.command("list-keys")
@click.option("--format", "output_format", 
              type=click.Choice(["table", "json"]), 
              default="table",
              help="Output format")
def list_keys(output_format: str):
    """List your API keys."""
    config = get_auth_config()
    
    # Use admin token if available, otherwise use regular API key
    token = config.get("admin_token") or config.get("api_key")
    if not token:
        console.print("[red]Error:[/red] Authentication required.")
        console.print("Set HOKUSAI_ADMIN_TOKEN or HOKUSAI_API_KEY environment variable")
        raise click.Abort()
    
    try:
        response = make_auth_request(
            method="GET",
            endpoint="/api/v1/keys",
            token=token
        )
        
        if response.status_code == 200:
            keys = response.json()
            
            if output_format == "json":
                console.print_json(data=keys)
            else:
                if not keys:
                    console.print("[yellow]No API keys found.[/yellow]")
                    return
                
                # Create table
                table = Table(
                    title="Your API Keys",
                    box=box.ROUNDED,
                    show_lines=True
                )
                
                table.add_column("ID", style="cyan")
                table.add_column("Name", style="green")
                table.add_column("Environment", style="yellow")
                table.add_column("Created", style="blue")
                table.add_column("Last Used", style="magenta")
                table.add_column("Status", style="red")
                
                for key in keys:
                    created = datetime.fromisoformat(key["created_at"]).strftime("%Y-%m-%d %H:%M")
                    last_used = "Never"
                    if key.get("last_used_at"):
                        last_used = datetime.fromisoformat(key["last_used_at"]).strftime("%Y-%m-%d %H:%M")
                    
                    status = "[green]Active[/green]"
                    if not key.get("is_active", True):
                        status = "[red]Revoked[/red]"
                    elif key.get("expires_at"):
                        expires = datetime.fromisoformat(key["expires_at"])
                        if expires < datetime.now():
                            status = "[red]Expired[/red]"
                    
                    table.add_row(
                        key["id"][:8] + "...",
                        key["name"],
                        key.get("environment", "production"),
                        created,
                        last_used,
                        status
                    )
                
                console.print(table)
        else:
            console.print(f"[red]Error:[/red] Failed to list API keys: {response.text}")
            raise click.Abort()
            
    except Exception as e:
        if not isinstance(e, click.Abort):
            console.print(f"[red]Error:[/red] {str(e)}")
            raise click.Abort()
        raise


@auth_group.command("revoke-key")
@click.argument("key_id")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def revoke_key(key_id: str, yes: bool):
    """Revoke an API key."""
    config = get_auth_config()
    
    if not config.get("admin_token"):
        console.print("[red]Error:[/red] Admin token required to revoke API keys.")
        console.print("Set HOKUSAI_ADMIN_TOKEN environment variable")
        raise click.Abort()
    
    # Confirm revocation
    if not yes:
        confirm = click.confirm(f"Are you sure you want to revoke key {key_id}?")
        if not confirm:
            console.print("[yellow]Revocation cancelled.[/yellow]")
            return
    
    try:
        response = make_auth_request(
            method="DELETE",
            endpoint=f"/api/v1/keys/{key_id}",
            token=config["admin_token"]
        )
        
        if response.status_code in [200, 204]:
            console.print(f"[green]✓[/green] API key {key_id} has been revoked.")
        elif response.status_code == 404:
            console.print(f"[red]Error:[/red] API key {key_id} not found.")
            raise click.Abort()
        else:
            console.print(f"[red]Error:[/red] Failed to revoke API key: {response.text}")
            raise click.Abort()
            
    except Exception as e:
        if not isinstance(e, click.Abort):
            console.print(f"[red]Error:[/red] {str(e)}")
            raise click.Abort()
        raise


@auth_group.command("rotate-key")
@click.argument("key_id")
def rotate_key(key_id: str):
    """Rotate an API key (generate a new key and revoke the old one)."""
    config = get_auth_config()
    
    if not config.get("admin_token"):
        console.print("[red]Error:[/red] Admin token required to rotate API keys.")
        console.print("Set HOKUSAI_ADMIN_TOKEN environment variable")
        raise click.Abort()
    
    try:
        response = make_auth_request(
            method="POST",
            endpoint=f"/api/v1/keys/{key_id}/rotate",
            token=config["admin_token"]
        )
        
        if response.status_code == 200:
            result = response.json()
            
            console.print(f"\n[green]✓[/green] API key {key_id} has been rotated!\n")
            
            panel = Panel(
                f"[bold cyan]{result['api_key']}[/bold cyan]",
                title="Your New API Key",
                subtitle="[red]Save this key - it won't be shown again![/red]",
                box=box.DOUBLE
            )
            console.print(panel)
            
            console.print("\n[yellow]Note:[/yellow] The old key will remain valid for 24 hours to allow migration.")
            console.print("\n[bold]Update your applications with:[/bold]")
            console.print(f"  export HOKUSAI_API_KEY={result['api_key']}")
            
        elif response.status_code == 404:
            console.print(f"[red]Error:[/red] API key {key_id} not found.")
            raise click.Abort()
        else:
            console.print(f"[red]Error:[/red] Failed to rotate API key: {response.text}")
            raise click.Abort()
            
    except Exception as e:
        if not isinstance(e, click.Abort):
            console.print(f"[red]Error:[/red] {str(e)}")
            raise click.Abort()
        raise


@auth_group.command("validate")
@click.option("--key", help="API key to validate (defaults to HOKUSAI_API_KEY)")
def validate_key(key: Optional[str]):
    """Validate an API key."""
    config = get_auth_config()
    
    # Use provided key or fall back to environment
    api_key = key or config.get("api_key")
    if not api_key:
        console.print("[red]Error:[/red] No API key provided.")
        console.print("Set HOKUSAI_API_KEY environment variable or use --key option")
        raise click.Abort()
    
    try:
        # Don't use make_auth_request here since we're validating the key itself
        response = requests.post(
            f"{config['auth_service_url']}/api/v1/keys/validate",
            json={
                "api_key": api_key,
                "service_id": "ml-platform"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            
            console.print("\n[green]✓[/green] API key is valid!\n")
            
            console.print("[bold]Key Information:[/bold]")
            console.print(f"  User ID: {result.get('user_id', 'N/A')}")
            console.print(f"  Key ID: {result.get('key_id', 'N/A')}")
            console.print(f"  Service: {result.get('service_id', 'N/A')}")
            console.print(f"  Rate Limit: {result.get('rate_limit_per_hour', 'N/A')}/hour")
            
            if result.get('scopes'):
                console.print(f"  Scopes: {', '.join(result['scopes'])}")
            
        elif response.status_code == 401:
            console.print("[red]✗[/red] API key is invalid or expired.")
        elif response.status_code == 429:
            console.print("[red]✗[/red] Rate limit exceeded.")
        else:
            console.print(f"[red]Error:[/red] Validation failed: {response.text}")
            
    except requests.exceptions.ConnectionError:
        console.print(f"[red]Error:[/red] Could not connect to auth service at {config['auth_service_url']}")
    except requests.exceptions.Timeout:
        console.print("[red]Error:[/red] Auth service request timed out")
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")


# Add commands to CLI group
def add_auth_commands(cli):
    """Add auth commands to main CLI."""
    cli.add_command(auth_group, name="auth")