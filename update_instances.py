#!/usr/bin/env python

import boto.ec2
from boto.manage.cmdshell import sshclient_from_instance

if __name__ == '__main__':
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
            print "Connected. Running command"
            status, stdout, stderr = ssh_client.run('sudo -u gcc-user bash -c "cd /home/gcc-user/gcc-explorer; git pull && make prereqs GDC=/usr/bin/gdc-4.8" && sudo service gcc-explorer restart; sudo service d-explorer restart; sudo service rust-explorer restart')
            print "Status", status
            print "Stdout", stdout
            print "Stderr", stderr
            print "Done"
