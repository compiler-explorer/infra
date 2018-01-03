#!/bin/bash

set -ex

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [[ ! -f /updated ]]; then
    apt-get -y update
    apt-get -y upgrade --force-yes
    apt-get -y install unzip libwww-perl libdatetime-perl nfs-common jq python-pip wget cachefilesd
    apt-get -y autoremove
    pip install --upgrade pip
    pip install --upgrade awscli
    wget -qO- https://get.docker.com/ | sh
    curl -sL http://aws-cloudwatch.s3.amazonaws.com/downloads/CloudWatchMonitoringScripts-1.2.1.zip -o /tmp/cwm.zip
    cd /root
    unzip /tmp/cwm.zip
    rm /tmp/cwm.zip
    echo '*/5 * * * * root /root/aws-scripts-mon/mon-put-instance-data.pl ' \
         '--mem-util --disk-space-util --disk-path=/ --auto-scaling --from-cron' >> /etc/crontab
    touch /updated
fi

if [[ ! -f /root/.aws ]]; then
    mkdir -p /root/.aws /home/ubuntu/.aws
    echo -e "[default]\nregion=us-east-1" | tee /root/.aws/config /home/ubuntu/.aws/config
    chown -R ubuntu /home/ubuntu/.aws
fi

get_conf() {
    aws ssm get-parameter --name $1 | jq -r .Parameter.Value
}

if [[ ! -f /etc/newrelic-infra.yml ]]; then
    NEW_RELIC_LICENSE="$(get_conf /compiler-explorer/newRelicLicense)"
    if [[ -z $"{NEW_RELIC_LICENSE}" ]]; then
        echo "Problem getting new relic license"
        exit 1
    fi
    echo "license_key: ${NEW_RELIC_LICENSE}" > /etc/newrelic-infra.yml
    chmod 600 /etc/newrelic-infra.yml
    curl https://download.newrelic.com/infrastructure_agent/gpg/newrelic-infra.gpg | apt-key add -
    printf "deb [arch=amd64] http://download.newrelic.com/infrastructure_agent/linux/apt xenial main" > /etc/apt/sources.list.d/newrelic-infra.list
    apt-get update
    apt-get install newrelic-infra -y
fi

PTRAIL='/etc/rsyslog.d/99-papertrail.conf'
if [[ ! -f "${PTRAIL}" ]]; then
    echo '*.*          @logs2.papertrailapp.com:34474' > "${PTRAIL}"
    service rsyslog restart
    pushd /tmp
    curl -sL 'https://github.com/papertrail/remote_syslog2/releases/download/v0.17/remote_syslog_linux_amd64.tar.gz' | tar zxf -
    cp remote_syslog/remote_syslog /usr/local/bin/
    docker pull gliderlabs/logspout:latest
    popd
fi

killall remote_syslog || true
cat > /etc/log_files.yml << EOF
files:
    - /var/log/nginx/xania.*
destination:
    host: logs2.papertrailapp.com
    port: 34474
    protocol: tls
EOF
remote_syslog

docker stop logspout || true
docker rm logspout || true
docker run --name logspout -d -v=/var/run/docker.sock:/tmp/docker.sock -h $(hostname) gliderlabs/logspout syslog://logs2.papertrailapp.com:34474

####### GROTESQUE HACK BEGIN #########
/etc/init.d/cachefilesd stop
sleep 3
perl -pi -e 's/^#RUN/RUN/' /etc/default/cachefilesd
sleep 3
/etc/init.d/cachefilesd start || true # maybe ? ugly!
sleep 3
/etc/init.d/cachefilesd start || true
####### GROTESQUE HACK END #########
# TODO ideally we would mount this readonly but the rsync operation to the versioned directory requires it :/
# TODO temporarily disabling fsc to see if this "fixes" issues. NB we _will_ start chewing through EFS burst credits...
mountpoint -q /opt || mount -t nfs4 -o nfsvers=4.1,rsize=1048576,wsize=1048576,hard,timeo=600,retrans=2,noatime,nodiratime $(curl -s http://169.254.169.254/latest/meta-data/placement/availability-zone).fs-db4c8192.efs.us-east-1.amazonaws.com:/ /opt

cd /home/ubuntu/

mkdir -p /home/ubuntu/.ssh
mkdir -p /tmp/auth_keys
aws s3 sync s3://compiler-explorer/authorized_keys /tmp/auth_keys
cat /tmp/auth_keys/* >> /home/ubuntu/.ssh/authorized_keys
rm -rf /tmp/auth_keys
chown -R ubuntu /home/ubuntu/.ssh

if ! egrep '^DOCKER_OPTS' /etc/default/docker.io >/dev/null; then
    echo 'DOCKER_OPTS="--restart=false"' >> /etc/default/docker.io
fi
