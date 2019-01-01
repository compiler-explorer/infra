
Compiler Argument Statistics based on Google Analytics
======================================================

This little script will gather Analytics data from Google
for Compilation events and which compiler arguments were used.

Based on the amount of times the arguments were used, this
data will be stored in an Compiler Explorer S3 bucket for later usage.

We can use this data to suggest commonly used Compiler arguments to users.


How to run
==========

First we need a temporary API token. The Google documentation and examples on this
are a little fuzzy and complicated.

What you can do to get the token is to use the webpage https://ga-dev-tools.appspot.com/query-explorer/
to do 1 test request for GCC explorer id `ga:60096530`, supplying at least the metric `ga:totalEvents`
and let the query run. If I scroll down on this webpage, it will mention the Access Token used for this request in
the API Query URI box. It is this token that we can use for this script for about 60 minutes.

And then we can run:

`yarn start --region us-east-1 --bucket storage.godbolt.org --accesstoken ouraccesstoken123`
