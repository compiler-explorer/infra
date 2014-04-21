#!/usr/bin/python

from string import Template
from config import S3_ACCESS_KEY, S3_SECRET_KEY

import boto.ec2


def get_script(filename='user-data-script.sh'):
    template = open(filename).read()
    return Template(template).substitute(
            S3_ACCESS_KEY=S3_ACCESS_KEY,
            S3_SECRET_KEY=S3_SECRET_KEY)


def launch():
    connection = boto.ec2.connect_to_region('us-east-1')
    return connection.run_instances(
            image_id = 'ami-59a4a230',
            instance_type = 't1.micro',
            key_name = 'mattgodbolt',
            security_groups = ['quick-start-1'],
            user_data=get_script()
            )


if __name__ == '__main__':
    print launch()
