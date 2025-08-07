const { v4: uuidv4 } = require('uuid');

// Regular expression to trim leading and trailing slashes
const TRIM_SLASHES_REGEX = /^\/+|\/+$/g;

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
        const pathParts = path.replace(TRIM_SLASHES_REGEX, '').split('/');
        
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
            'Access-Control-Allow-Headers': 'Content-Type'
        },
        body: JSON.stringify({ error: message })
    };
}

/**
 * Create an ALB-compatible success response
 * Response format depends on Accept header
 */
function createSuccessResponse(result, acceptHeader) {
    // Determine response format based on Accept header
    if (acceptHeader && acceptHeader.toLowerCase().includes('text/plain')) {
        // Plain text response - typically just the assembly output
        let body = '';
        if (result.asm) {
            // Join assembly lines
            body = result.asm.map(line => line.text || '').join('\n');
        } else if (result.stdout) {
            // Fallback to stdout if no asm
            body = result.stdout.join('\n');
        }
        
        return {
            statusCode: 200,
            headers: {
                'Content-Type': 'text/plain; charset=utf-8',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST',
                'Access-Control-Allow-Headers': 'Content-Type, Accept'
            },
            body
        };
    } else {
        // Default to JSON response
        return {
            statusCode: 200,
            headers: {
                'Content-Type': 'application/json; charset=utf-8',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST',
                'Access-Control-Allow-Headers': 'Content-Type, Accept'
            },
            body: JSON.stringify(result)
        };
    }
}

module.exports = {
    generateGuid,
    extractCompilerId,
    isCmakeRequest,
    createErrorResponse,
    createSuccessResponse
};