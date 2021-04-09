import boto3
import os

# resource type constants
const_resource_type_unknown = 'unknown'
const_resource_type_ec2 = 'ec2'
const_resource_type_rds = 'rds'


# cross-account role name
role_name = os.environ.get('RoleName').strip()


def get_handles(accountid, resource_type):
    
    # Get resource and/or client handles
    #
    # Input: Account ID
    # Output: boto3 client, resource

    # get credentials for cross-account role
    sts_connection = boto3.client('sts')

    RoleArn= f"arn:aws:iam::{accountid}:role/{role_name}"
    acct = sts_connection.assume_role(
        RoleArn= RoleArn,
        RoleSessionName= f"huit_public_subnet_compliance" 
    )
    credentials=acct['Credentials']

    # get the client and resource
    client = boto3.client(
        resource_type,
        aws_access_key_id= credentials['AccessKeyId'],
        aws_secret_access_key= credentials['SecretAccessKey'],
        aws_session_token= credentials['SessionToken']
        )

    if resource_type == const_resource_type_ec2:
        resource = boto3.resource(
        resource_type,
        aws_access_key_id= credentials['AccessKeyId'],
        aws_secret_access_key= credentials['SecretAccessKey'],
        aws_session_token= credentials['SessionToken']
        )
    else:
        resource = None

    return client, resource
