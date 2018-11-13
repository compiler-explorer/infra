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
"use strict";

const
    _ = require('underscore'),
    quote = require('shell-quote'),
    logger = require('./logger').logger,
    https = require('https'),
    AWS = require('aws-sdk'),
    S3Bucket = require('./s3-handler');

class CompilerArgumentsWriter {
    constructor() {
        this.arguments = {};
        this.prefix = "compargs";

        this.promiseList = [];
    }

    addOptionsToStatistics(compilerId, args, times) {
        try {
            times = Number.parseInt(times, 10);
            if (times === NaN) times = Number.MAX_SAFE_INTEGER;
        } catch(e) {
            times = Number.MAX_SAFE_INTEGER;
        }

        _.each(args, (arg) => {
            if (arg === "-") return;

            if (!this.arguments[compilerId]) {
                this.arguments[compilerId] = {};
            }

            if (!this.arguments[compilerId][arg]) {
                this.arguments[compilerId][arg] = times
            } else {
                this.arguments[compilerId][arg] += times;
            }
        });
    }

    saveToStorage(s3, compilerId, stats) {
        return s3.put(compilerId + ".json", stats, this.prefix, {});
    }

    save(region, bucket) {
        AWS.config.update({ region: region });
        const s3 = new S3Bucket(bucket, region);

        return new Promise((resolve) => {
            const list = _.keys(this.arguments).map((compilerId) => {
                this.saveToStorage(s3, compilerId, this.arguments[compilerId]);
            });

            resolve(Promise.all(list));
        }, this);
    }

    loadStatisticsFromGoogleStatsURL(url, accesstoken) {
        return new Promise((resolve, reject) => {
            https.get(url + "&access_token=" + accesstoken, (res) => {
                const { statusCode } = res;

                let error;
                if (statusCode !== 200) {
                    error = new Error(
                        `Request Failed (GET ${url}).\n` +
                        `Status Code: ${statusCode}`);
                }

                if (error) {
                    logger.error(error.message);
                    res.resume();
                    reject(error.message);
                    return;
                }

                let rawdata = "";

                res.on('data', (chunk) => rawdata += chunk);
                res.on('end', () => {
                    const data = JSON.parse(rawdata);

                    data.rows.forEach(row => {
                        try {
                            const args = _.chain(quote.parse(row[1] || '')
                                .map(x => typeof (x) === "string" ? x : x.pattern))
                                .compact()
                                .value();
                            this.addOptionsToStatistics(row[0], args, row[2]);
                        } catch(e) {
                            // ignore
                        }
                    }, this);

                    if (data.nextLink) {
                        logger.info("Found more data...");
                        resolve(data.nextLink);
                    } else {
                        logger.info("That was all she wrote");
                        resolve(false);
                    }
                }, this);
            }, this).on('error', (e) => {
                logger.error(e);
                reject(e);
            });
        }).then((nextLink) => {
            if (nextLink) {
                return this.loadStatisticsFromGoogleStatsURL(nextLink, accesstoken);
            } else {
                return false;
            }
        }, this);
    }
}

module.exports = CompilerArgumentsWriter;
