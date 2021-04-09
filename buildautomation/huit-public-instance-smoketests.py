import boto3
import logging
from time import sleep
import sys
import datetime
import os

logger = logging.getLogger(__name__)
loglevel = 'INFO'
logging.basicConfig(level=loglevel)
logger.setLevel(loglevel)


remote_account = os.environ.get('ChildAccountNumber')
remote_role = 'AWSCloudFormationStackSetExecutionRole'

private_subnet_id = os.environ.get('private_subnet_id')
public_subnet_id = os.environ.get('public_subnet_id')

private_db_subnet = os.environ.get('private_db_subnet_group')
public_db_subnet = os.environ.get('public_db_subnet_group')

exception_tag = 'Exception'

lambda_function_name = 'huit_public_instance_compliance'


def get_client(service_name):
    
    # get credentials for cross-account role
    sts_connection = boto3.client('sts')

    RoleArn= f"arn:aws:iam::{remote_account}:role/{remote_role}"
    acct = sts_connection.assume_role(RoleArn= RoleArn, RoleSessionName= "SmokeTests")
    credentials=acct['Credentials']

    # get the client and resource
    client = boto3.client(
        service_name,
        aws_access_key_id= credentials['AccessKeyId'],
        aws_secret_access_key= credentials['SecretAccessKey'],
        aws_session_token= credentials['SessionToken']
        )

    return client


def set_compliance_mode(compliance_mode):

    lmda = boto3.client('lambda')
    lmda_response = lmda.get_function_configuration(FunctionName=lambda_function_name)
    lmda_vars = lmda_response['Environment']['Variables']
    lmda_vars['ComplianceMode'] = str(compliance_mode).lower()
    lmda.update_function_configuration(FunctionName=lambda_function_name, Environment={'Variables': lmda_vars})
    return



def run_test(test):

    try:

        name = test['Name']
        desc = test['Description']
        instance_type = test['Type']
        subnet_type = test['Subnet']
        compliance = test['Compliance']
        desired_tag = test['Tag']
        exception = test['Exception']
        delay = test['Delay']

        logger.info(f"Starting {name}: {desc}")

        instance_client = get_client(instance_type)

        if instance_type == 'ec2':
            ssm = get_client('ssm')
            ssm_response = ssm.get_parameter(Name='/aws/service/ami-amazon-linux-latest/amzn2-ami-hvm-x86_64-gp2')
            image_id = ssm_response['Parameter']['Value']
        else:
            image_id = 'mysql'

        # create tags
        instance_tags = []
        identifier = f"SmokeTest-{name}-{datetime.datetime.now().strftime('%H%M%S')}"
        instance_tags.append({'Key': 'Name', 'Value': identifier})
        if exception:
            instance_tags.append({'Key': exception_tag, 'Value': 'True'})

        # assign subnet / subnet group
        if instance_type == 'ec2':
            if subnet_type == 'Public':
                subnet_id = public_subnet_id
            else:
                subnet_id = private_subnet_id
        else:
            if subnet_type == 'Public':
                subnet_id = public_db_subnet
            else:
                subnet_id = private_db_subnet


        # set compliance mode
        logger.info(f"...set compliance mode to {compliance}")
        set_compliance_mode(compliance)

        # fire-up instance
        logger.info(f"...start up {instance_type} instance")
        if instance_type == 'ec2':
            instance_response = instance_client.run_instances(ImageId=image_id, InstanceType='t3.micro',MinCount=1,MaxCount=1,SubnetId=subnet_id,
                TagSpecifications=[{'ResourceType': 'instance', 'Tags': instance_tags}])
            instance_id = instance_response['Instances'][0]['InstanceId']
        else:
            public = (subnet_type == 'Public')
            instance_response = instance_client.create_db_instance(DBInstanceIdentifier=identifier, DBInstanceClass='db.t3.micro', Engine=image_id,
                MasterUsername='admin', MasterUserPassword='admin123123',AllocatedStorage=20,BackupRetentionPeriod=0,MultiAZ=False,
                AutoMinorVersionUpgrade=False,PubliclyAccessible=public,DBSubnetGroupName=subnet_id,Tags=instance_tags,MonitoringInterval=0)
            instance_id = instance_response['DBInstance']['DBInstanceIdentifier']

        # check for instance state and compliance tag
        logger.info("...Checking instance state and compliance tag")
        valid_states = ('running', 'stopping', 'stopped', 'available' )

        state = 'unknown'
        while state.lower() not in valid_states:
            logger.info(f"...waiting for {delay} seconds to reach stable state, instance still in ({state}) state")
            sleep(delay)
            if instance_type == 'ec2':
                instance_response = instance_client.describe_instances(InstanceIds=[instance_id])
                state = instance_response['Reservations'][0]['Instances'][0]['State']['Name']
            else:
                instance_response = instance_client.describe_db_instances(DBInstanceIdentifier=instance_id)
                state = instance_response['DBInstances'][0]['DBInstanceStatus']

        logger.info(f"...instance is in {state} state; waiting another {delay} seconds to allow compliance function to take action")
        sleep(delay)

        if instance_type == 'ec2':
            tags = instance_response['Reservations'][0]['Instances'][0]['Tags']
        else:
            arn = instance_response['DBInstances'][0]['DBInstanceArn']
            tags = instance_client.list_tags_for_resource(ResourceName=arn)['TagList']

        if exception or subnet_type == 'Private' or not compliance:
            desired_state = ('running', 'available')
        else:
            desired_state = ('stopped', 'stopping')

        success = False
        logger.info("...checking instance state")


        if state.lower() not in desired_state:
            logger.info(f"...instance is in {state} state...FAIL")
        else:
            logger.info(f"...instance is in {state} state...PASS")
            logger.info("...checking tag")
            tag_found = False
            wrong_tag = False
            if len(tags) > 0:
                for tag in tags:
                    if tag['Key'] == 'HUIT Compliance':
                        if desired_tag == None:
                            tag_found = True
                            logger.info("...found compliance tag...FAIL")
                            break
                        elif tag['Value'].startswith(desired_tag):
                            tag_found = True
                            logger.info("...found correct compliance tag...PASS")
                            break
                        else:
                            logger.info("...found incorrect compliance tag...FAIL")
                            wrong_tag = True
                            break
            if len(tags) == 0 or (not tag_found and not wrong_tag):
                logger.info(f"...no tag found...{'PASS' if desired_tag is None else 'FAIL'}")

            if ((tag_found and desired_tag is not None) or (not tag_found and desired_tag is None)):
                success = True

        # terminate instance
        logger.info("...terminating instance")
        if instance_type == 'ec2':
            instance_client.terminate_instances(InstanceIds=[instance_id])        
        else:
            instance_client.delete_db_instance(DBInstanceIdentifier=instance_id,SkipFinalSnapshot=True)

        # put Lambda back into audit mode
        logger.info("...put lambda back in audit mode")
        set_compliance_mode(False)

        logger.info(f"{name} {'PASSED' if success else 'FAILED'}")
        return success

    except Exception as e:
        logger.info(f"Unexpected error in test: {e}")
        sys.exit(1)



def run_smoke_tests(tests):

    result = True
    for test in tests:
        result = result and run_test(test)

    return result



def create_tests():

    tests = []

    # test = {}
    # test['Name'] = 'EC2Test1'
    # test['Description'] = 'Audit Mode, Public Subnet'
    # test['Type'] = 'ec2'
    # test['Subnet'] = 'Public'
    # test['Compliance'] = False
    # test['Tag'] = 'Out of Compliance'
    # test['Exception'] = False
    # test['Delay'] = 30
    # tests.append(test)

    # test = {}
    # test['Name'] = 'EC2Test2'
    # test['Description'] = 'Compliance Mode, Public Subnet'
    # test['Type'] = 'ec2'
    # test['Subnet'] = 'Public'
    # test['Compliance'] = True
    # test['Tag'] = 'Stopped on'
    # test['Exception'] = False
    # test['Delay'] = 30
    # tests.append(test)

    # test = {}
    # test['Name'] = 'EC2Test3'
    # test['Description'] = 'Compliance Mode, Public Subnet, Exception'
    # test['Type'] = 'ec2'
    # test['Subnet'] = 'Public'
    # test['Compliance'] = True
    # test['Tag'] = 'Out of Compliance'
    # test['Exception'] = True
    # test['Delay'] = 30
    # tests.append(test)

    # test = {}
    # test['Name'] = 'EC2Test4'
    # test['Description'] = 'Compliance Mode, Private Subnet'
    # test['Type'] = 'ec2'
    # test['Subnet'] = 'Private'
    # test['Compliance'] = True
    # test['Tag'] = None
    # test['Exception'] = False
    # test['Delay'] = 30
    # tests.append(test)

    # test = {}
    # test['Name'] = 'RDSTest1'
    # test['Description'] = 'Audit Mode, Public Subnet'
    # test['Type'] = 'rds'
    # test['Subnet'] = 'Public'
    # test['Compliance'] = False
    # test['Tag'] = 'Out of Compliance'
    # test['Exception'] = False
    # test['Delay'] = 30
    # tests.append(test)

    # test = {}
    # test['Name'] = 'RDSTest2'
    # test['Description'] = 'Compliance Mode, Public Subnet'
    # test['Type'] = 'rds'
    # test['Subnet'] = 'Public'
    # test['Compliance'] = True
    # test['Tag'] = 'Stopped on'
    # test['Exception'] = False
    # test['Delay'] = 30
    # tests.append(test)

    # test = {}
    # test['Name'] = 'RDSTest3'
    # test['Description'] = 'Compliance Mode, Public Subnet, Exception'
    # test['Type'] = 'rds'
    # test['Subnet'] = 'Public'
    # test['Compliance'] = True
    # test['Tag'] = 'Out of Compliance'
    # test['Exception'] = True
    # test['Delay'] = 30
    # tests.append(test)

    test = {}
    test['Name'] = 'RDSTest4'
    test['Description'] = 'Compliance Mode, Private Subnet'
    test['Type'] = 'rds'
    test['Subnet'] = 'Private'
    test['Compliance'] = True
    test['Tag'] = None
    test['Exception'] = False
    test['Delay'] = 30
    tests.append(test)

    return tests



if __name__ == "__main__":

    logger.info("Building test data")
    tests = create_tests()
    logger.info(f"Starting smoke tests. Total of {len(tests)} will be run.")
    results = run_smoke_tests(tests)
    if results:
        logger.info("All smoke tests PASSED!")
    else:
        logger.info("Some smoke tests have FAILED")
    if results:
        sys.exit()
    else:
        sys.exit(1)
