"""
AWS Secrets Manager integration for loading secrets at runtime.

Used in production (ECS) to fetch secrets from Secrets Manager.
This module is designed to be called before settings validation.
"""

import os
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def load_secret_from_aws(secret_name: str) -> Optional[str]:
    """
    Load a secret from AWS Secrets Manager.

    Args:
        secret_name: The secret ARN or name

    Returns:
        The secret string value or None if unavailable
    """
    # Only attempt AWS SDK usage if running in AWS environment
    if not os.getenv("AWS_EXECUTION_ENV"):
        return None

    try:
        import boto3
        client = boto3.client(
            'secretsmanager',
            region_name=os.getenv("AWS_REGION", "us-east-1")
        )
        response = client.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except ImportError:
        logger.warning("boto3 not available, cannot load AWS secrets")
        return None
    except Exception as e:
        logger.warning(f"Failed to load secret {secret_name} from AWS Secrets Manager: {e}")
        return None


def inject_secrets_from_aws(secret_mappings: Optional[Dict[str, str]] = None) -> None:
    """
    Inject secrets from AWS Secrets Manager into environment variables.

    Called at app startup before settings validation.
    Only runs in AWS ECS environment.

    Args:
        secret_mappings: Optional dict mapping env var names to secret ARN env vars.
                        Default mappings:
                        - DATABASE_URL <- DB_SECRET_ARN
                        - JWT_SECRET <- JWT_SECRET_ARN
    """
    if not os.getenv("AWS_EXECUTION_ENV"):
        # Not running in ECS, skip
        return

    # Default mappings - env var name to the env var containing the secret ARN
    if secret_mappings is None:
        secret_mappings = {
            "DATABASE_URL": os.getenv("DB_SECRET_ARN"),
            "JWT_SECRET": os.getenv("JWT_SECRET_ARN"),
        }

    for env_var, secret_arn in secret_mappings.items():
        if secret_arn and not os.getenv(env_var):
            # Secret ARN is set but env var not populated yet
            secret_value = load_secret_from_aws(secret_arn)
            if secret_value:
                os.environ[env_var] = secret_value
                logger.info(f"Loaded {env_var} from AWS Secrets Manager")
