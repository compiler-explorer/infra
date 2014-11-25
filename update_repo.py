#!/usr/bin/env python

import os
import boto.ec2
from boto.manage.cmdshell import sshclient_from_instance

THIS_DIR = os.path.dirname(os.path.realpath(__file__))


def update(repo):
    conn = boto.ec2.connect_to_region('us-east-1')
    reservations = conn.get_all_instances()
    for reservation in reservations:
        for instance in reservation.instances:
            if instance.state != 'running':
                print "Skipping {} instance {}".format(instance.state, instance.id)
                continue
            print "Connecting to", instance
            ssh_client = sshclient_from_instance(instance, "ec2-mattgodbolt.pem",
                    user_name='ubuntu')
            status, stdout, stderr = ssh_client.run('cd {} && git pull && make dist'.format(repo))
            if status:
	        print "Error"
                print stdout
		print stderr
		return False
            else:
                print "OK: " + stdout
    return True
          

if __name__ == '__main__':
    update("jsbeeb-beta")
