import json
import boto3
import logging
import os
import urllib3
import datetime
import dateutil


from huit_public_compliance_utils import const_resource_type_ec2, get_handles
from huit_public_compliance_utils import const_resource_type_rds
from huit_public_compliance_utils import const_resource_type_unknown

# setup for eastern time zone
eastern = dateutil.tz.gettz('US/Eastern')

# get required boto3 resources
sns = boto3.client('sns')
dynamodb = boto3.resource('dynamodb')

# DynamoDB Table
tablename = os.environ.get('DynamoTable')
table = dynamodb.Table(tablename)

# Notification Information
sns_topic = os.environ.get('Topic')
slack_url = os.environ.get('SlackURL')
sendtoslack = os.environ.get('SendToSlack') in ['true', 'True', 'yes', 'Yes']
sendtosns = os.environ.get('SendToSNS') in ['true', 'True', 'yes', 'Yes']

# Setup logger
logger = logging.getLogger(__name__)
loglevel = os.environ.get('LogLevel', logging.INFO)
logging.basicConfig(level=loglevel)
logger.setLevel(loglevel)



def add_info_to_dynamo(params):
    
    # Log information to DynamoDB Table
    #
    # Input: Parameters related to public resource
    # Output: None

    table.put_item(Item= params)
    return


def add_tag_to_instance(instance_type, instance_arn, instance_id, client, instance, tag_params):

    if instance_type == const_resource_type_ec2:
        ec2 = instance.Instance(instance_id)
        ec2.create_tags(Tags=[{'Key': tag_params['Key'], 'Value': tag_params['Value']}])
    else:
        client.add_tags_to_resource(ResourceName=instance_arn, Tags=[{'Key': tag_params['Key'], 'Value': tag_params['Value']}])

    return


def stop_instance(instance_type, client, instance_id):

    if instance_type == const_resource_type_ec2:
        client.stop_instances(InstanceIds=[instance_id])
    else:
        try:
            client.stop_db_instance(DBInstanceIdentifier=instance_id)
        except Exception as e:
            # in a later version could perhaps find a better way to deal with this situation
            # we've already checked that it is in a 'stoppable' state, but may have changed
            # since that last check
            logger.info(f"Error trying to stop RDS instance {instance_id}: {e}")
            pass
                
    return


def is_instance_stoppable(instance_type, client, instance_id):

    stoppable = False
    if instance_type == const_resource_type_ec2:
        stoppable = True
    else:
        status = client.describe_db_instances(DBInstanceIdentifier= instance_id)['DBInstances'][0]['DBInstanceStatus']
        if status in ['available', 'stopped', 'stopping']:
            stoppable = True

    return stoppable



def update_parameters(notify_params, tag_params, db_params):

    dt = datetime.datetime.now(tz=eastern)

    # format current time for messages
    dt_msg = dt.strftime("%b-%d at %Hh%M")

    # format current time for db
    dt_db = dt.strftime("%Y-%m-%d %H:%M:%S.%f")

    # update parameters
    tag_params['Value'] = tag_params['Value'].replace('$currtime$', dt_msg)
    notify_params['Message'] = notify_params['Message'].replace('$currtime$', dt_msg)
    db_params['DateTime'] = db_params['DateTime'].replace('$currtime$', dt_db)



def remediate_and_notify(compliance_mode, is_exception, instance_params, notify_params, tag_params, db_params):

    # extract parameters
    account_id = instance_params['AccountId']
    instance_type = instance_params['ResourceType']
    instance_id = instance_params['InstanceId']
    instance_arn = instance_params['InstanceArn']

    # fix later
    client, instance = get_handles(account_id, instance_type)

    ok_to_proceed = True
    if compliance_mode and not is_exception:
        # If the instance is to be stopped, can only continue if it's in a stoppable state
        # This applies primarily to RDS instances
        logger.info("Check to see if instance can be stopped")
        ok_to_proceed = is_instance_stoppable(instance_type, client, instance_id)

    if ok_to_proceed:

        # update paramters with current time
        update_parameters(notify_params, tag_params, db_params)

        # Apply tags to resources
        logger.info("Adding tags to instance")
        add_tag_to_instance(instance_type, instance_arn, instance_id, client, instance, tag_params)

        # Stop the resource if necessary
        if compliance_mode and not is_exception:
            logger.info(f"Stopping {instance_type.upper()} instance {instance_id}")
            stop_instance(instance_type, client, instance_id)

        # Add info to DynamoDB Table
        logger.info("Logging data to DynamoDB")
        add_info_to_dynamo(db_params)

        # Send notifications as required
        message = notify_params['Message']
        subject = notify_params['Subject']
        logger.info(message)
        if sendtoslack:
            logger.info("Sending Slack message")
            slackmessage = json.dumps({'text':message})
            http = urllib3.PoolManager()
            http.request("POST", slack_url, body=slackmessage, headers={"Content-Type": "application/json"})
        if sendtosns:
            logger.info("Sending SNS message")
            sns.publish(TargetArn= sns_topic, Subject=subject, Message=message)

    else:
        logger.info("Instance cannot be stopped, going into wait-state")

    return ok_to_proceed



