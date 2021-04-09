import boto3
import logging
import time
import os

stackset_name = os.environ.get('StackSetName')
child_account = os.environ.get('ChildAccountNumber')

# Initialize logger
logger = logging.getLogger( __name__ )
loglevel = 'INFO'
logging.basicConfig(level=loglevel)
logger.setLevel(loglevel)

try:
    logger.info(f"Removing temporary stackset {stackset_name} from account {child_account}")
    cfn = boto3.client('cloudformation')
    logger.info(f"Deleting stack instance")
    cfn_response = cfn.delete_stack_instances(StackSetName=stackset_name,Accounts=[child_account],Regions=['us-east-1'],RetainStacks=False)
    operation_id=cfn_response["OperationId"]

    logger.info("Waiting for stack set instance to be deleted")
    done = False
    checks = 0
    while not done and checks < 20:
        time.sleep(30)
        cfn_response = cfn.describe_stack_set_operation(StackSetName=stackset_name,OperationId=operation_id)
        status = cfn_response['StackSetOperation']['Status']
        logger.info(f"...status is {status}")
        if status == 'SUCCEEDED':
            done = True
    if not done:
        raise Exception("Timed out waiting for stack instance to delete")
    
    logger.info("Removing stackset")                                    
    cfn.delete_stack_set(StackSetName=stackset_name)
    logger.info("Done")
    exit(0)

except Exception as e:
    logger.info(f"Encountered error: {e}, exiting")
    exit(1)
