#!/usr/bin/env python

import boto.ec2
from boto.manage.cmdshell import sshclient_from_instance
from config import S3_ACCESS_KEY, S3_SECRET_KEY

def do_this_one(name):
    while True:
        res = raw_input("Update {}? ".format(name))
        if res == 'y':
            return True
        elif res == 'n':
            return False


if __name__ == '__main__':
    conn = boto.ec2.connect_to_region('us-east-1')
    reservations = conn.get_all_instances()
    for reservation in reservations:
        for instance in reservation.instances:
            if instance.state != 'running':
                print "Skipping {} instance {}".format(instance.state, instance.id)
                continue
            if not do_this_one(instance.id):
                continue

            print "Connecting to", instance
            ssh_client = sshclient_from_instance(instance, "ec2-mattgodbolt.pem",
                    user_name='ubuntu')
            print "Connected. Running command"
            status, stdout, stderr = ssh_client.run('sudo bash -c "export S3_ACCESS_KEY={}; export S3_SECRET_KEY={}; cd /compiler-explorer-image; git pull && bash setup.sh"'.format(
                S3_ACCESS_KEY, S3_SECRET_KEY))
            print "Status", status
            print "Stdout", stdout
            print "Stderr", stderr
            print "Done"
