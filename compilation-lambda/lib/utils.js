const {v4: uuidv4} = require('uuid');

// Regular expression to trim leading and trailing slashes
const TRIM_SLASHES_REGEX = /^\/+|\/+$/g;
const textBanner = 'Compilation provided by Compiler Explorer at https://godbolt.org/';

/**
 * Generate a unique GUID for request tracking
 */
function generateGuid() {
    return uuidv4();
}

/**
 * Extract compiler ID from ALB request path
 * Expected paths:
 * - Production: /api/compiler/{compiler_id}/compile or /api/compiler/{compiler_id}/cmake
 * - Other envs: /{env}/api/compiler/{compiler_id}/compile or /{env}/api/compiler/{compiler_id}/cmake
 */
function extractCompilerId(path) {
    try {
        const pathParts = path.replaceAll(TRIM_SLASHES_REGEX, '').split('/');

        // Production format: /api/compiler/{compiler_id}/compile
        if (pathParts.length >= 4 && pathParts[0] === 'api' && pathParts[1] === 'compiler') {
            return pathParts[2];
        }

        // Other environments format: /{env}/api/compiler/{compiler_id}/compile
        if (pathParts.length >= 5 && pathParts[1] === 'api' && pathParts[2] === 'compiler') {
            return pathParts[3];
        }
    } catch (error) {
        // Ignore parse errors
    }
    return null;
}

/**
 * Check if the request is for cmake compilation
 */
function isCmakeRequest(path) {
    return path.endsWith('/cmake');
}

/**
 * Create an ALB-compatible error response
 */
function createErrorResponse(statusCode, message) {
    return {
        statusCode,
        headers: {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
        },
        body: JSON.stringify({error: message}),
    };
}

function textify(array, filterAnsi) {
    const text = (array || []).map(line => line.text).join('\n');
    if (filterAnsi) {
        // Remove ANSI escape sequences
        // Ref: https://stackoverflow.com/questions/14693701
        return text.replaceAll(/(\x9B|\x1B\[)[\d:;<=>?]*[ -/]*[@-~]/g, '');
    }
    return text;
}

function isEmpty(value) {
    return (
        value === null ||
        value === undefined ||
        (typeof value === 'string' && value.trim() === '') ||
        (Array.isArray(value) && value.length === 0) ||
        (typeof value === 'object' && Object.keys(value).length === 0)
    );
}

/**
 * Create an ALB-compatible success response
 * Response format depends on Accept header
 */
function createSuccessResponse(result, filterAnsi, acceptHeader) {
    delete result.guid;
    delete result.s3Key;

    // Determine response format based on Accept header
    if (acceptHeader && acceptHeader.toLowerCase().includes('text/plain')) {
        // Plain text response - typically just the assembly output
        let body = '';

        try {
            if (!isEmpty(textBanner)) body += '# ' + textBanner + '\n';
            body += textify(result.asm, filterAnsi);
            if (result.code !== 0) body += '\n# Compiler exited with result code ' + result.code;
            if (!isEmpty(result.stdout)) body += '\nStandard out:\n' + textify(result.stdout, filterAnsi);
            if (!isEmpty(result.stderr)) body += '\nStandard error:\n' + textify(result.stderr, filterAnsi);

            if (result.execResult) {
                body += '\n\n# Execution result with exit code ' + result.execResult.code + '\n';
                if (!isEmpty(result.execResult.stdout)) {
                    body += '# Standard out:\n' + textify(result.execResult.stdout, filterAnsi);
                }
                if (!isEmpty(result.execResult.stderr)) {
                    body += '\n# Standard error:\n' + textify(result.execResult.stderr, filterAnsi);
                }
            }
        } catch (ex) {
            body += `Error handling request: ${ex}`;
        }
        body += '\n';

        return {
            statusCode: 200,
            headers: {
                'Content-Type': 'text/plain; charset=utf-8',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST',
                'Access-Control-Allow-Headers': 'Content-Type, Accept',
            },
            body,
        };
    } else {
        // Default to JSON response
        return {
            statusCode: 200,
            headers: {
                'Content-Type': 'application/json; charset=utf-8',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST',
                'Access-Control-Allow-Headers': 'Content-Type, Accept',
            },
            body: JSON.stringify(result),
        };
    }
}

module.exports = {
    generateGuid,
    extractCompilerId,
    isCmakeRequest,
    createErrorResponse,
    createSuccessResponse,
};
