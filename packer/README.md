# Debugging packer builds.

It can be useful to debug what's going on in the packer build.

You can push to a branch and then run the packer build on your branch with debug output which will ask before each
operation and also let you `ssh` into the remote machine. Once the Step "Wating for instance to be ready" is reached you
can `ssh` into the machine and debug what's going on.

Run the packer with something like like:

```bash
git:mg/gpu $ git commit -am "WIP" && \
  git push -u && \
  make packer-gpu-node EXTRA_ARGS="-debug -var BRANCH='mg/gpu'"
```

Then you can `ssh` with
```bash
git:mg/gpu $ ssh -i ec2_jammy.pem ubuntu@44.202.28.62
```

where `44.202.28.62` is the "Public IP" of the instance.

### Debugging CE on the remote packer instance

If you want to test out CE running on the in-progress packer image, once the install is done but before it shuts down,
log in with something like:

```bash
git:mg/gpu $ ssh -i ec2_jammy.pem ubuntu@44.202.28.62 -L10240:127.0.0.1:10240
44.202.28.62: $ sudo service compiler-explorer start
```

that is, forward local port 10240 to the remote port, and then start the service. You can then play around with the
remote CE on localhost:10240

To make it run in a different environment, you'll need to hack the `/infra/start-support.sh` to override the ENV it
picks up from AWS node config. Edit the ENV directly, and then restart the service.
