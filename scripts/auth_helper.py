#!/usr/bin/env python3
"""Helper script for API authentication - generate API keys or test ETH signatures."""

import secrets
import sys
from datetime import datetime

import boto3
from eth_account import Account
from eth_account.messages import encode_defunct


def generate_api_key():
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def store_api_key_in_aws(user_id: str, api_key: str):
    """Store API key in AWS Secrets Manager."""
    secrets_client = boto3.client("secretsmanager", region_name="us-east-1")
    secret_name = f"hokusai/api-keys/{user_id}"
    
    try:
        # Try to create the secret
        secrets_client.create_secret(
            Name=secret_name,
            SecretString=api_key,
            Description=f"API key for user {user_id}"
        )
        print(f"✅ Created new secret: {secret_name}")
    except secrets_client.exceptions.ResourceExistsException:
        # Update existing secret
        secrets_client.update_secret(
            SecretId=secret_name,
            SecretString=api_key
        )
        print(f"✅ Updated existing secret: {secret_name}")


def create_eth_signature(private_key: str, message: str):
    """Create an Ethereum signature for authentication."""
    # Create account from private key
    account = Account.from_key(private_key)
    
    # Sign the message
    message_hash = encode_defunct(text=message)
    signed = account.sign_message(message_hash)
    
    return {
        "address": account.address,
        "message": message,
        "signature": signed.signature.hex()
    }


def test_eth_auth(address: str, message: str, signature: str):
    """Test ETH signature verification."""
    try:
        message_hash = encode_defunct(text=message)
        recovered_address = Account.recover_message(message_hash, signature=signature)
        is_valid = recovered_address.lower() == address.lower()
        print(f"✅ Signature valid: {is_valid}")
        print(f"   Provided address: {address}")
        print(f"   Recovered address: {recovered_address}")
        return is_valid
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


def main():
    print("Hokusai API Authentication Helper")
    print("=================================\n")
    
    choice = input("Choose an option:\n1. Generate new API key\n2. Create ETH signature\n3. Test ETH signature\n\nEnter choice (1-3): ")
    
    if choice == "1":
        user_id = input("\nEnter user ID (e.g., 'test_user'): ")
        api_key = generate_api_key()
        print(f"\n📋 Generated API Key: {api_key}")
        
        store = input("\nStore in AWS Secrets Manager? (y/n): ")
        if store.lower() == 'y':
            store_api_key_in_aws(user_id, api_key)
        
        print(f"\n🔐 To use this API key:")
        print(f"   curl -H 'Authorization: Bearer {api_key}' http://registry.hokus.ai/api/health")
    
    elif choice == "2":
        print("\n⚠️  WARNING: Never share your private key!")
        private_key = input("Enter your Ethereum private key (with or without 0x prefix): ")
        if not private_key.startswith('0x'):
            private_key = '0x' + private_key
        
        # Create a timestamped message
        message = f"Hokusai API Access - {datetime.utcnow().isoformat()}"
        
        try:
            result = create_eth_signature(private_key, message)
            print(f"\n✅ Signature created successfully!")
            print(f"\n📋 ETH Address: {result['address']}")
            print(f"📋 Message: {result['message']}")
            print(f"📋 Signature: {result['signature']}")
            
            print(f"\n🔐 To use ETH authentication:")
            print(f"   curl -H 'X-ETH-Address: {result['address']}' \\")
            print(f"        -H 'X-ETH-Message: {result['message']}' \\")
            print(f"        -H 'X-ETH-Signature: {result['signature']}' \\")
            print(f"        http://registry.hokus.ai/api/health")
        except Exception as e:
            print(f"❌ Error creating signature: {e}")
    
    elif choice == "3":
        address = input("\nEnter ETH address: ")
        message = input("Enter message: ")
        signature = input("Enter signature: ")
        test_eth_auth(address, message, signature)
    
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()