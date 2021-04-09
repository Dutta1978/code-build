import os
os.environ['ComplianceMode'] = 'True'
os.environ['SendToSlack'] = 'True'
os.environ['SendToSNS'] = 'True'
os.environ['RoleName'] = 'HUITPublicResourceCompliance-us-east-1'
os.environ['LogLevel'] = 'INFO'
os.environ['Topic'] = 'arn:aws:sns:us-east-1:077179288803:dynamodb'
os.environ['SlackURL'] = 'https://hooks.slack.com/services/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'
os.environ['DynamoTable'] = 'HUITPublicResourceCheck'
# org-id o-xukgm413dr

from aws_lambda_context import LambdaContext
from huit_public_compliance import lambda_handler


# event = {
#   "version": "0",
#   "id": "ee376907-2647-4179-9203-343cfb3017a4",
#   "detail-type": "EC2 Instance State-change Notification",
#   "source": "aws.ec2",
#   "account": "929976461491",
#   "time": "2021-03-10T12:52:00Z",
#   "region": "us-east-1",
#   "resources": [
#     "arn:aws:ec2:us-east-1:929976461491:instance/i-010fc37020416ca41"
#   ],
#   "detail": {
#     "instance-id": "i-010fc37020416ca41",
#     "state": "running"
#   }
# }


# event = {
#   "version": "0",
#   "id": "ee376907-2647-4179-9203-343cfb3017a4",
#   "detail-type": "EC2 Instance State-change Notification",
#   "source": "aws.ec2",
#   "account": "459273849936",
#   "time": "2021-02-02T21:30:34Z",
#   "region": "us-east-1",
#   "resources": [
#     "arn:aws:ec2:us-east-1:459273849936:instance/i-011996651ee44c891"
#   ],
#   "detail": {
#     "instance-id": "i-011996651ee44c891",
#     "state": "running"
#   }
# }

event = {
    "version":"0",
    "id":"b921dc29-8bce-8330-6fe6-a5aaed8619d4",
    "detail-type":"RDS DB Instance Event",
    "source":"aws.rds",
    "account":"929976461491",
    "time":"2021-03-15T17:43:35Z",
    "region":"us-east-1",
    "resources":[
        "arn:aws:rds:us-east-1:929976461491:db:database-2"
    ],
    "detail":{
        "EventCategories":[
            "empty"
        ],
        "SourceType":"DB_INSTANCE",
        "SourceArn":"arn:aws:rds:us-east-1:929976461491:db:database-2",
        "Date":"2021-03-15T17:43:35.870Z",
        "Message":"Finished moving DB instance to target VPC",
        "SourceIdentifier":"database-2",
        "EventID":null
    }
}

event = {
    "version":"0",
    "id":"9dbdce5f-29f1-1e4a-119e-08ea62e15ce4",
    "detail-type":"RDS DB Instance Event",
    "source":"aws.rds",
    "account":"929976461491",
    "time":"2021-03-10T01:21:29Z",
    "region":"us-east-1",
    "resources":[
        "arn:aws:rds:us-east-1:929976461491:db:database-4"
    ],
    "detail":{
        "EventCategories":[
            "creation"
        ],
        "SourceType":"DB_INSTANCE",
        "SourceArn":"arn:aws:rds:us-east-1:929976461491:db:database-4",
        "Date":"2021-03-10T01:21:29.548Z",
        "Message":"DB instance created",
        "SourceIdentifier":"database-4",
        "EventID":"RDS-EVENT-0005"
    }
}


context = LambdaContext()


response = lambda_handler(event, context)


