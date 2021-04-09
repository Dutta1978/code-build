Public Instance compliance check for HUIT
2021-03-31 V2.0

Updates to include:
- check all subnets in subnet group

A. SUMMARY
==========
Contains the components necessary to deploy a solution which detects EC2 and RDS instances that are triggered to run in public subnets as well as a CI/CD pipeline to build and test the stack anytime there is a pull request.  

For EC2, when the instance moves into the "Running" state, a CloudWatch Alarm is triggered in the specific account and then delivered to the master account over a EventBridge event bus. This event is passed to a Lambda function which evaluates whether or not the instance is in a public subnet. If it is, the Lambda function will either: do nothing (if in audit mode OR instance has an exception tag) or stop the instance (if in compliance mode). The instance will also be tagged indicating that it is out of compliance. Lambda will record each event in a DynamoDB table.

For RDS, a number of CloudWatch events are used to detect when an instance is created or restarted. When the Lambda function recieves one of these events, and the system is in audit mode, it will immediately tag and notify that the instance is out of compliance.  When the system is in compliance mode however, the Lambda function will continuously trigger a step function that acts as a wait state until the RDS instance is in a stoppable state.  The instance will be tagged and stopped; the event will be recorded in the DynamoDB.

The CICD pipeline is triggered whenever there is a pull request created.  It first builds the master account stack, then builds a stackset instance in a child account.  It then runs a number of smoke tests to verify the functionality of the public instance solution.  The master and child stacks are subsequently deleted.


B. PACKAGE CONTENTS
===================
a. CloudFormation Templates (cft/)
    i.      huit-public-resources-child-account.yml
    ii.     huit-public-resources-master-account.yml
b. Lambda (lambda/)
    i.      huit_public_compliance.py
    ii.     huit_public_compliance_remediate.py
    iii.    huit_public_compliance_utils.py
    iv.     testlambda.py
    v.      huit_public_compliance.zip
c. Step Function (sfn/)
    i.      huit_public_compliance_sfn.json
d. Build Automation / CICD (buildautomation/)
    i.      huit-public-compliance-pipeline.yml
    ii.     params-master-stack.json
    iii.    params-child-stack.json
    iv.     buildspec-artifacts-params.yml
    v.      buildspec-delete-stackset.yml
    vi.     buildspec-validate-cft.yml (for future use)
    vii.    huit_delete_temp_stackset.py
    viii.   huit-public-instance-smoketests.py



C. DEPLOY MASTER ACCOUNT RESOURCES
==================================
1. Create an s3 bucket that will contain the lambda code, referred to as <s3bucket>.

2. Upload the file huit_public_compliance.zip and huit_public_compliance_sfn.json to <s3bucket> created above.  You can use folders for versioning.  e.g. <s3bucket>/v1/huit_public_compliance.zip

3. Deploy the huit-public-resources-master-account.yml file using cloud formation.  Specify the following parameters:
    a. pComplianceMode - if this is True, instances will be stopped if in public subnet.
    b. pExceptionTag - if an instance contains this tag with the value "True", it will not be stopped, even if in a public subnet.
    c. pLogLevel - lambda loglevel to use; can be DEBUG, INFO, WARNING, CRITICAL, and any other valid logger log level.
    d. pROLENAME - the cross account role name used to stop instances.
    e. pS3Bucket - name of <s3bucket> created above.
    f. pS3Key - should be /subfolder/huit_public_compliance.zip unless a different filename was used above.
    g. pSNSTopicArn - ARN of the SNS topic that will be notified of any alerts.
    h. pSendToSNS - True or False. Whether to send alerts to an SNS topic (specified above).
    i. pSendToSlack - True or False. Whether to send alerts to a Slack Channel.
    j. pSlackURL - URL for Slack webhook. Can be obtained by adding a Slack App and creating a webhook.
    k. pTableName - Name of the DynamoDB Table to use
    l. pOrgId - Organization ID, which can be retrieved from the AWS Organizations console
    m. pS3SfnKey - should be /subfolder/huit_public_compliance_sfn.json unless a different filename was used above.


4. Note the following parameters can be changed at anytime in the lambda function environment variables section:
    - pComplianceMode
    - pExceptionTag
    - pLogLevel
    - pROLENAME
    - pSNSTopicArn
    - pSendToSNS
    - pSendToSlack
    - pSlackURL
    - The variable pTableName is also available but should not be modified.


D. DEPLOY SUB-ACCOUNT RESOURCES
===============================
1. This is done ideally using stacksets.

2. Deploy the huit-public-resources-child-account.yml CFT to the sub-accounts, ideally using stacksets.  Specify the following paramters:
    a. pEventBusName - should be HUITEventBus unless the master account template was changed
    b. pMasterAccountId - account number for the master account
    c. pCrossAccountRoleName - cross account role that will be used to stop instances


E. BUILD AUTOMATION
===================
1. All of the build automation files are under the /buildautomation folder

2. Deploy the stack using huit-public-compliance-pipeline.yml in the "test" master account (this CANNOT be the same place where you are running the production stack).  Specify the following parameters:
    a. ApplicationName - use default (huit-public-instance-compliance)
    b. GitHubUser - GitHub user name for repo
    c. GitHubRepository - GitHub repo name
    d. GitHubRepositoryUrl - GitHub repo URL
    e. GitHubBranch - Branch where the code to be tested lives (typically "development" or "dev")
    f. GitHubOAuthToken - GitHub token
    g. ChildStackSetName - use default (huit-build-test-public-compliance-child-account)
    h. ChildAccountNumber - account where child stack will be deployed and instances created for testing
    i. MasterStackName - use default (huit-build-test-public-compliance-master-account)
    j. PublicSubnetId - Subnet ID of a PUBLIC subnet where EC2 instances will be created
    k. PrivateSubnetId - Subnet ID of a PRIVATE subnet where EC2 instances will be created
    l. PublicDBSubnetGroup - DB Subnet Group name of a PUBLIC subnet group where RDS instances will be created
    m. PrivateDBSubnetGroup - DB Subnet Group name of a PRIVATE subnet group where RDS instances will be created
    n. MasterTemplateName - use default (huit-public-resources-master-account.yml)
    o. ChildTemplateName - use default (huit-public-resources-child-account.yml)


3. Update the params-master-stack.json file as follows:
    a. pComplianceMode - use the default 'false'
    b. pExceptionTag - use the default 'Exception'
	c. pLogLevel - use the default 'INFO'
    d. pOrgId - enter your org ID in the format o-xxxxxxxxx
    e. pROLENAME - use the default 'HUITPublicResourceCompliance'
    f. pS3Bucket - enter a bucket that already exists where the lambda code will be copied
	g. pS3Key - version_folder/huit_public_compliance.zip (e.g. v1.0/huit_public_compliance.zip)
    h. pS3SfnKey - version_folder/huit_public_compliance_sfn_v3.json
    i. pSNSTopicArn - ARN of an existing SNS topic where alerts will be sent
    j. pSendToSlack - true
    k. pSendToSns - true
    l. pSlackURL - Slack URL
    m. pTableName - use the default 'huit_public_compliance'


4. Ensure all the code is checked in and pushed to the development branch

5. Create a pull request from the development branch to the main branch

6. The tests should start; you can track activity under CodePipeline


