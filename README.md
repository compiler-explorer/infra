# Compiler Explorer Infrastructure

A whole bag of scripts and AWS config to run [Compiler Explorer](https://gcc.godbolt.org).

Of most use to the casual observer is probably the code in `bin/ce_install` - a tool to install the
Compiler Explorer compilers to `/opt/compiler-explorer`. In particular, the open source compilers can be
installed by anyone by running:

```bash
$ make ce  # this installs python modules etc
$ ./bin/ce_install install compilers
```

This will grab all the open source compilers and put them in `/opt/compiler-explorer` (which must be writable by
the current user).  To get the beta and nightly-built latest compilers, add the parameter `--enable nightly` to the command.

To list installation candidates, use `./bin/ce_install list`. A single installation can be installed by name.

More info can be found [here](https://github.com/compiler-explorer/infra/blob/main/docs/installing_compilers.md)

# Built compilers

Status page to our daily built compilers https://compiler-explorer.github.io/compiler-workflows/build-status


# Cleaning up old AMIs

Something like:

```bash
$ npx aws-amicleaner --region 'us-east-1' \
    --exclude-in-use --verbose \
    --exclude-newest=2 --exclude-days 7 \
    --include-name 'compiler-explorer*'
```

# Deploying the admin site and associated lambda

- If you had to change the lambda code:
  - `make upload-lambda` - uploads the lambda code to S3 (NOT idempotent unfortunately so only do this if you change the code)
  - `make terraform-apply` - updates the endpoints/balancer config to point at the new lambda zip
- `make update-admin` - deploys the admin site HTML and CSS etc
