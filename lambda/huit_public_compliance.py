import boto3
import logging
import os
import json

from huit_public_compliance_utils import get_handles
from huit_public_compliance_remediate import remediate_and_notify

from huit_public_compliance_utils import const_resource_type_ec2
from huit_public_compliance_utils import const_resource_type_rds
from huit_public_compliance_utils import const_resource_type_unknown


# define global logger
logger = logging.getLogger(__name__)

# flags set as environment variables
trueval = ['true', 'True', 'yes', 'Yes']
compliancemode = os.environ.get('ComplianceMode') in trueval
exception = os.environ.get('ExceptionTag')
step_function_arn = os.environ.get('StepFunctionArn')




def check_if_public(client, vpcid, subnets):
    
  # Check if instance is in public subnet
  #
  # Input: EC2 client, vpcid and subnetid
  # Output: True if in public subnet, false otherwise

  logger.info("Checking route tables for public egress")

  # specifically for RDS instances:
  # The subnets in a DB subnet group are either public or private. They can't be a mix of both public and private subnets.
  # so, only need to test one subnet
  # https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.WorkingWithRDSInstanceinaVPC.html
  #
  # HOWEVER, after testing, this is not the case; can actually mix private and public subnets in a subnet group
  # so we'll cycle through all the subnets

  # cycle through route tables to see if an igw is attached
  found = False
  n = 0
  while n < len(subnets) and not found:
    subnetid = subnets[n]
    vpcroutetable = False
    rt = client.describe_route_tables(Filters=[{'Name':'association.subnet-id','Values': [subnetid]}])
    if len(rt['RouteTables']) == 0:
      # this subnet is associated with the main VPC route table
      logger.info("Instance is using the default VPC route table")
      vpcroutetable = True
      rt = client.describe_route_tables(Filters=[{'Name':'vpc-id','Values': [vpcid]}])

    logger.info("Iterating through route tables")
    # Iterate through the route tables looking for an igw
    for ra in rt['RouteTables']:
      if found:
        break
      if vpcroutetable == False or (ra['Associations'][0]['Main'] == True):
        route = ra['Routes']
        for i in route:
          gid = i.get('GatewayId', '')
          destinationcidr = i.get('DestinationCidrBlock', '')
          if gid.startswith('igw-') and destinationcidr == '0.0.0.0/0':
            # Found igw attached - this is a public subnet
            logger.info(f"Found igw connected to subnet for route {i}")
            found = True
            break
          else:
            logger.info(f"No public path for route {i}")

  if found:
    logger.info("Instance IS in public subnet")
  else:
    logger.info("Instance NOT in Public Subnet")

  return found

    


def lambda_handler(event, context):
    
  # Lambda handler to manage events from CloudWatch
  #
  # Input: AWS event, context objects
  # Output: None

  try:

    # set log level according to environment variable
    loglevel = os.environ.get('LogLevel', logging.INFO)
    logging.basicConfig(level=loglevel)
    logger.setLevel(loglevel)

    # get information from event object
    logger.info('Event: ' + str(event))

    # first check if it is a callback from step function
    if 'InstanceParameters' in event:
      # Callback from stepfunction
      logger.info(f"Processing input from step function: {json.dumps(event)}")
      instance_params = event['InstanceParameters']
      notify_params = event['NotificationParameters']
      tag_params = event['TagParameters']
      db_params = event['DBParameters']

      stopped = remediate_and_notify(True, False, instance_params, notify_params, tag_params, db_params)
      response = {'InstanceStopped': stopped}
      logger.info(f"Response: {json.dumps(response)}")
      return response

    # Otherwise, continue and process AWS events
    accountid = event['account']
    detail = event['detail']
    etime = event['time']

    # define global flags
    is_public = False
    is_exception = False

    # only need to process a limited set of events, for now only EC2 and RDS
    resource_type = const_resource_type_unknown
    if event['source'] == 'aws.ec2' and event['detail-type'] == 'EC2 Instance State-change Notification':
      resource_type = const_resource_type_ec2
    elif event['source'] == 'aws.rds' and event['detail-type'] == 'RDS DB Instance Event':
      rds_events = ['RDS-EVENT-0005', 'RDS-EVENT-0088', 'RDS-EVENT-0154']
      rds_event = event['detail']['EventID']
      if rds_event in rds_events:
        resource_type = const_resource_type_rds
        if rds_event == 'RDS-EVENT-0005':
          logger.info("Processing RDS Created event")
        elif rds_event == 'RDS-EVENT-0088':
          logger.info("Processing RDS Started event")
        elif rds_event == 'RDS-EVENT-0154':
          logger.info("Processing RDS Started Due to Exceeding Allowed Time to be Stopped event")
      elif event['detail']['Message'] == 'Finished moving DB instance to target VPC':
        # Not sure why AWS is sending this without an event ID
        resource_type = const_resource_type_rds
        logger.info("Processing RDS moved VPC event")


    if resource_type == const_resource_type_unknown:
      logger.info('Invalid event. Exiting.')
      response = {'InstanceStopped': False}      
      return response

    
    # re-read compliance mode in case it changes
    compliancemode = os.environ.get('ComplianceMode') in trueval

    # set default values
    autoscalegroupname = 'None'


    if resource_type == const_resource_type_ec2:
      # get EC2 information
      instanceid = detail['instance-id']
      instance_arn = event['resources'][0]
      logger.info(f"Processing EC2 state change notification for instance {instanceid} in account {accountid}")
      ec2_client, ec2 = get_handles(accountid, const_resource_type_ec2)
      instance = ec2.Instance(instanceid)
      subnets = [instance.subnet_id]
      vpcid = instance.vpc_id
      instancetags = instance.tags
      instancename = instanceid
      subnetname = subnets[0]
      subnet = ec2_client.describe_subnets(SubnetIds=subnets)['Subnets'][0]
      if 'Tags' in subnet:
        subnettags = subnet['Tags']
        for tag in subnettags:
          if tag['Key'] == 'Name':
            subnetname = tag['Value']
            break


    else:
      # get RDS information
      instanceid = detail['SourceIdentifier']
      logger.info(f"Processing RDS event notification for DB identifier {instanceid} in account {accountid}")
      rds_client, rds = get_handles(accountid, const_resource_type_rds)
      ec2_client, ec2 = get_handles(accountid, const_resource_type_ec2)
      db_instance = rds_client.describe_db_instances(DBInstanceIdentifier=instanceid)['DBInstances'][0]
      vpcid = db_instance['DBSubnetGroup']['VpcId']
      subnet_details = db_instance['DBSubnetGroup']['Subnets']
      subnets = []
      for detail in subnet_details:
        subnets.append(detail['SubnetIdentifier'])
      subnetname = db_instance['DBSubnetGroup']['DBSubnetGroupName']
      instance_arn = db_instance['DBInstanceArn']
      tag_list = rds_client.list_tags_for_resource(ResourceName=instance_arn)
      instancetags = tag_list['TagList']
      instancename = instanceid

    logger.info("Processing tags")
    if instancetags is not None:
      for tag in instancetags:
        if tag['Key'] == 'Name':
          instancename = tag['Value']
        if tag['Key'] == exception:
          is_exception = True
        if tag['Key'] == 'aws:autoscaling:groupName':
          autoscalegroupname = tag['Value']
      
    logger.info("Getting VPC information")
    vpcname = vpcid
    vpc = ec2_client.describe_vpcs(VpcIds=[vpcid])['Vpcs'][0]
    if 'Tags' in vpc:
      vpctags = vpc['Tags']
      for tag in vpctags:
        if tag['Key'] == 'Name':
          vpcname = tag['Value']
          break

    logger.info(f"Instance is in VPC {vpcname}, subnet {subnetname}")

    is_public = check_if_public(ec2_client, vpcid, subnets)

    if not is_public:
      logger.info(f"{resource_type.upper()} instance is not in public subnet")
      response = {'InstanceStopped': False}      
      return response


    # Initialize info to send to DynamoDB
    db_params = {}
    db_params['AccountId'] = accountid
    db_params['DateTime'] = "$currtime$"
    db_params['VpcName'] = vpcname
    db_params['SubnetName'] = subnetname
    db_params['InstanceId'] = instanceid
    db_params['InstanceName'] = instancename
    db_params['AutoScaleGroupName'] = autoscalegroupname
    db_params['ResourceType'] = resource_type.upper()


    # Create sub-messages
    if resource_type == const_resource_type_ec2:
      instance_msg = f"instance {instancename} ({instanceid})"
    else:
      instance_msg = f"instance {instancename}"

    if autoscalegroupname == 'None':
      asg_msg = ""
    else:
      asg_msg = f" in autoscalinggroup {autoscalegroupname}"

    if is_exception:
      exception_tag_msg = " with an exception tag"
    else:
      exception_tag_msg = ""

    # Create the messages, tags, etc...
    if is_exception or not compliancemode:
      # System is in audit mode OR instance has an exception tag - just tag
      logger.info(f"Found {resource_type.upper()} instance in public subnet{exception_tag_msg}")
      tag_value = f"Out of Compliance on $currtime$ because instance is in public subnet. {'Exception applied.' if is_exception else ''}"
      subject = f"WARNING: {resource_type.upper()} detected in public subnet{exception_tag_msg}."
      message = f"{resource_type.upper()} {instance_msg}{asg_msg} in account {accountid} was detected running in public subnet {subnetname}, VPC {vpcname} on $currtime${exception_tag_msg}."
      if is_exception:
        db_params['Action'] = "None, exception tag found"
      else:
        db_params['Action'] = "None, in audit mode"

    else:
      # Running in compliance mode and found instance in public subnet
      logger.info(f"In compliance mode. Adding tag and stopping {resource_type.upper()} instance.")
      tag_value = f"Stopped on $currtime$ because instance is in public subnet"
      subject = f"{resource_type.upper()} instance in public subnet STOPPED"
      message = f"{resource_type.upper()} {instance_msg}{asg_msg} in account {accountid} was stopped because it was running in public subnet {subnetname}, VPC {vpcname} on $currtime$"
      db_params['Action'] = "Instance stopped"

    tag_params = {}
    tag_params['Key'] = 'HUIT Compliance'
    tag_params['Value'] = tag_value

    notify_params = {}
    notify_params['Subject'] = subject
    notify_params['Message'] = message

    instance_params = {}
    instance_params['AccountId'] = accountid
    instance_params['InstanceId'] = instanceid
    instance_params['InstanceArn'] = instance_arn
    instance_params['ResourceType'] = resource_type


    done = remediate_and_notify(compliancemode, is_exception, instance_params, notify_params, tag_params, db_params)
    if not done:
      logger.info("Triggering step function")
      client = boto3.client('stepfunctions')
      stepFunctionInput = {'InstanceParameters': instance_params, 'NotificationParameters': notify_params, 'TagParameters': tag_params, 'DBParameters': db_params}
      client.start_execution(stateMachineArn = step_function_arn, input = json.dumps(stepFunctionInput))
      logger.info("Waiting")
    else:
      logger.info("Done")


  except Exception as e:
    done = False
    message = f"Lambda checking for public resources failed: {e}"
    logger.error(message)


  response = {'InstanceStopped': done}
  return response

