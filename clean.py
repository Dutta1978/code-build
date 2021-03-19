import boto3
import json

ec2 = boto3.client('ec2')
ec2resource = boto3.resource('ec2')

#def handler(event, context):
    #print('event')

def deletevolumes(_volumes):
    for vol in _volumes["Volumes"]:
      print(f"volume: {vol['VolumeId']}")
      volumetags = ec2resource.Volume(vol['VolumeId']).tags
      print(volumetags)
      res = ec2.delete_volume(VolumeId=vol['VolumeId'])
      print(volumetags)    

filter = [
      {
          'Name': 'status',
          'Values': [
              'available',
          ]
      },
    ]  
filter= [
      {
          'Name': 'tag:dr-test-pl',
          'Values': [
              'yes',
          ]
      },
    ]
volumes = ec2.describe_volumes(Filters= filter)
NextToken = volumes.get("NextToken", None)
print(volumes)
deletevolumes(volumes)

# if NextToken is not None:
#   volumes = ec2.describe_volumes(Filters= filter, NextToken = NextToken)
#   NextToken = volumes.get("NextToken", None) 
#   print(volumes)
#   deletevolumes(volumes)



                      
