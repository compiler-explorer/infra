Compiler Explorer Image
------------------

A whole bag of scripts and Dockerfiles and AWS config to run [Compiler Explorer](https://gcc.godbolt.org).

Of most use to the casual observer is probably the code in `update_compilers` - scripts to install all the
Compiler Explorer compilers to `/opt/compiler-explorer`. In particular, the open source compilers can be
installed by anyone by running:

```bash
$ ./update_compilers/install_compilers.sh
```

This will grab all the open source compilers and put them in `/opt/compiler-explorer` (which must be writable by
the current user).  To get the beta and nightly-built latest compilers, add the parameter `nightly` to the script.

