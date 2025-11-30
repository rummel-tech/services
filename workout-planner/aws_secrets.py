"""
AWS Secrets Manager integration for loading secrets at runtime.
Used in production (ECS) to fetch DATABASE_URL and JWT_SECRET from Secrets Manager.
"""
import os
import json
from typing import Optional

def load_secret_from_aws(secret_name: str) -> Optional[str]:
    """
    Load a secret from AWS Secrets Manager.
    Returns the secret string value or None if unavailable.
    """
    # Only attempt AWS SDK usage if running in AWS environment
    if not os.getenv("AWS_EXECUTION_ENV"):
        return None
    
    try:
        import boto3
        client = boto3.client('secretsmanager', region_name=os.getenv("AWS_REGION", "us-east-1"))
        response = client.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except Exception as e:
        print(f"Warning: Failed to load secret {secret_name} from AWS Secrets Manager: {e}")
        return None

def inject_secrets_from_aws():
    """
    Inject secrets from AWS Secrets Manager into environment variables.
    Called at app startup before settings validation.
    Only runs in AWS ECS environment.
    """
    if not os.getenv("AWS_EXECUTION_ENV"):
        # Not running in ECS, skip
        return
    
    # Map of env var name to secret ARN/name (from ECS task definition)
    secret_mappings = {
        "DATABASE_URL": os.getenv("DB_SECRET_ARN"),
        "JWT_SECRET": os.getenv("JWT_SECRET_ARN"),
    }
    
    for env_var, secret_arn in secret_mappings.items():
        if secret_arn and not os.getenv(env_var):
            # Secret ARN is set but env var not populated yet
            # ECS should have already injected this via task definition secrets
            # This is a fallback in case direct secret fetch is needed
            secret_value = load_secret_from_aws(secret_arn)
            if secret_value:
                os.environ[env_var] = secret_value
                print(f"Loaded {env_var} from AWS Secrets Manager")
