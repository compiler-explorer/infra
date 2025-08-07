const axios = require('axios');

/**
 * Forward compilation request directly to environment URL
 */
async function forwardToEnvironmentUrl(compilerId, url, body, isCmake, headers) {
    try {
        // Adjust URL for cmake vs compile endpoint
        if (isCmake && !url.endsWith('/cmake')) {
            if (url.endsWith('/compile')) {
                url = url.slice(0, -8) + '/cmake'; // Replace only the ending '/compile'
            } else {
                url = url.endsWith('/') ? `${url}cmake` : `${url}/cmake`;
            }
        } else if (!isCmake && !url.endsWith('/compile')) {
            if (url.endsWith('/cmake')) {
                url = url.slice(0, -6) + '/compile'; // Replace only the ending '/cmake'
            } else {
                url = url.endsWith('/') ? `${url}compile` : `${url}/compile`;
            }
        }
        
        // Prepare headers for forwarding (filter out ALB-specific headers)
        const forwardHeaders = {};
        for (const [key, value] of Object.entries(headers)) {
            const lowerKey = key.toLowerCase();
            if (!['host', 'x-forwarded-for', 'x-forwarded-proto', 'x-forwarded-port'].includes(lowerKey)) {
                forwardHeaders[key] = value;
            }
        }
        
        // Set appropriate content type if not already set
        if (!forwardHeaders['content-type'] && !forwardHeaders['Content-Type']) {
            try {
                // Try to parse as JSON first
                JSON.parse(body);
                forwardHeaders['Content-Type'] = 'application/json';
            } catch {
                // Fallback to plain text
                forwardHeaders['Content-Type'] = 'text/plain';
            }
        }
        
        console.info(`Forwarding request to ${url}`);
        
        // Make the HTTP request to the target environment
        const response = await axios.post(url, body, {
            headers: forwardHeaders,
            timeout: 60000, // 60 second timeout
            validateStatus: null // Don't throw on HTTP error status
        });
        
        // Return the response content and headers
        return {
            statusCode: response.status,
            headers: response.headers,
            body: response.data
        };
        
    } catch (error) {
        if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
            console.error(`Timeout forwarding to ${url}:`, error);
            throw new Error(`Request timeout: ${error.message}`);
        }
        console.error(`Request error forwarding to ${url}:`, error);
        throw new Error(`Request failed: ${error.message}`);
    }
}

module.exports = {
    forwardToEnvironmentUrl
};