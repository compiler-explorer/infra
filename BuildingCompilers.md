# Building compilers

Compiler Explorer builds its compilers using docker images. These images are each contained in their own [Git Repos](https://github.com/search?q=topic%3Adocker-images+org%3Acompiler-explorer&type=Repositories). The images are auto-built by [Docker Hub](https://hub.docker.com/u/compilerexplorer) on git checkins.

## Daily images

Compilers are built using a Github workflow, running on our own builders, in the [compiler-workflows](https://github.com/compiler-explorer/compiler-workflows/) repo.

Some legacy builds use a dedicated AWS instance (see `setup-builder.sh`) that is left shut down most of the time. These compilations are orchestrated via the admin node. It runs the `admin-daily-build.sh` on a daily
schedule via cron (see `crontab.admin`). This script fires up the builder node, runs the various builds on it, and shuts down.

## New compilers

New compilers can be built by triggering a Github action build - use the [Custom compiler build](https://github.com/compiler-explorer/infra/actions/workflows/bespoke-build.yaml) and then click "Run workflow".  A clang build takes around 20 minutes.

Remember that after building a compiler you'll need to update the [YAML configuration](bin/yaml)
to install it.
