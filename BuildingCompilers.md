# Building compilers

Compiler Explorer builds its compilers using docker images. These images are each contained in their own [Git Repos](https://github.com/search?q=topic%3Adocker-images+org%3Acompiler-explorer&type=Repositories). The images are auto-built by [Docker Hub](https://hub.docker.com/u/compilerexplorer) on git checkins.

## Daily images

There's an AWS instance (see `setup-builder.sh`) that is left shut down most of the time. It's used to build new
compilers. Daily compilations are orchestrated via the admin node. It runs the `admin-daily-build.sh` on a daily
schedule via cron (see `crontab.admin`). This script fires up the builder node, runs the various builds on it, and shuts down.
The same crontab also updates the symlinks in `/opt/compiler-explorer` daily to point at the newest builds.

## New compilers

New compilers are built by logging into the admin node (with `ce admin`), and then manually starting the build node (`ce builder start`).

Then compilations can be run with commands like:

```bash
ce builder exec -- \
  sudo docker run --rm --name clang.build \
    -v/home/ubuntu/.s3cfg:/root/.s3cfg:ro compilerexplorer/clang-builder \
    bash build.sh 6.0.0 s3://compiler-explorer/opt/
```

A clang build takes around 20 minutes.

**Don't forget to shut the build node down with `ce builder stop` when you've finished!**

Remember that after building a compiler you'll need to update the `update_compilers/install_compilers.sh` script
to install it. And if you're updating an existing compiler, you'll need to do something like unpacking the
compiler to the admin drive's `/tmp/` and then `rsync --delete-after -avz /tmp/compiler/ /opt/compiler-explorer/compiler/`.
