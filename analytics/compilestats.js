// Copyright (c) 2018, Compiler Explorer Team
// All rights reserved.
//
// Redistribution and use in source and binary forms, with or without
// modification, are permitted provided that the following conditions are met:
//
//     * Redistributions of source code must retain the above copyright notice,
//       this list of conditions and the following disclaimer.
//     * Redistributions in binary form must reproduce the above copyright
//       notice, this list of conditions and the following disclaimer in the
//       documentation and/or other materials provided with the distribution.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
// AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
// IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
// ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
// LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
// CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
// SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
// INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
// CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
// ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
// POSSIBILITY OF SUCH DAMAGE.

const
    nopt = require('nopt'),
    logger = require('./lib/logger').logger,
    CompilerArgumentsWriter = require('./lib/compiler-arguments-writer');

const opts = nopt({
    region: [String],
    bucket: [String],
    accesstoken: [String]
});

function explainRequirementsAndExit() {
    logger.error("usage: yarn start --region us-east-1 --bucket storage.godbolt.org --accesstoken googleapi1234");
    process.exit(1);
}

function checkCommandLineParams() {
    if (!opts) explainRequirementsAndExit();
    if (!opts.region) explainRequirementsAndExit();
    if (!opts.bucket) explainRequirementsAndExit();
    if (!opts.accesstoken) explainRequirementsAndExit();
}

checkCommandLineParams();

const baseUrl =
    "https://www.googleapis.com/analytics/v3/data/ga" +
    "?ids=ga:60096530" +
    "&dimensions=ga:eventAction,ga:eventLabel" +
    "&metrics=ga:totalEvents" +
    "&sort=-ga:totalEvents" +
    "&filters=ga:eventCategory%3D%3DCompile;ga:eventLabel!%3D(not+set)" +
    "&start-date=128daysAgo" +
    "&end-date=yesterday";

const writer = new CompilerArgumentsWriter();
writer.loadStatisticsFromGoogleStatsURL(baseUrl, opts.accesstoken).then(() => {
    writer.save(opts.region, opts.bucket).then(() => {
        logger.info("Done");
    });
});
