# Contributing to Compiler Explorer (image repo)

First of, if you're reading this: thank you! Even considering contributing to
 **Compiler Explorer** is very much appreciated!
Before we go too far, an apology: **Compiler Explorer** grew out of a bit of
 hacky JavaScript into a pretty large and well-used project pretty quickly.
Not all the code was originally well-written or well-tested.
Please be forgiving of that, and be ready to help in improving that.

This is the image repo: it contains build scripts and administration tools
used in running the site at https://godbolt.org/

The **Compiler Explorer** project follows a [Code of Conduct](CODE_OF_CONDUCT.md) which
 aims to foster an open and welcoming environment.

The code here is a mismash of languages, scripts and tools. Unlike the main project
there's a lot less test script, there's a lot of dead or dying code, and the layout
is a mess. Hopefully this will change with time, and ideas to improve it are welcomed.

## In brief
* Make your changes, trying to stick to the style and format where possible.
* Test what you can locally. For example, if adding new compilers try running
  the update scripts yourself and make sure the relevant compilers get installed
  to `/opt/compiler-explorer/...`.
* Submit a Pull Request.

If you have any questions, don't hesitate: [Contact us](https://github.com/mattgodbolt/compiler-explorer/blob/main/README.md#contact-us).
