class StatusViewModel {
    constructor() {
        this.isLoading = ko.observable(true);
        this.hasError = ko.observable(false);
        this.errorMessage = ko.observable('');
        this.lastUpdated = ko.observable('');
        this.items = ko.observableArray([]);
        this.autoRefreshEnabled = ko.observable(this.loadAutoRefreshSetting());
        this.autoRefreshInterval = null;

        // Subscribe to changes of autoRefreshEnabled to save to localStorage
        this.autoRefreshEnabled.subscribe(newValue => {
            this.saveAutoRefreshSetting(newValue);
            this.setupAutoRefresh(newValue);
        });

        this.gridViewModel = new ko.simpleGrid.viewModel({
            data: this.items,
            columns: [
                {
                    headerText: "Environment",
                    rowText: "description"
                },
                {
                    headerText: "Status",
                    rowText: "statusBadge"
                },
                {
                    headerText: "Version",
                    rowText: "versionDisplay"
                },
                {
                    headerText: "Instances",
                    headerTitle: "Format: Healthy instances / Total instances",
                    rowText: "instances"
                },
                {
                    headerText: "URL",
                    rowText: "url"
                }
            ],
            pageSize: 20
        });

        this.refreshData();

        // Setup initial auto-refresh if enabled
        this.setupAutoRefresh(this.autoRefreshEnabled());
    }

    refreshData() {
        this.isLoading(true);
        this.hasError(false);

        // Using the ALB endpoint with timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 10000); // 10 second timeout

        fetch('https://compiler-explorer.com/api/status', { signal: controller.signal })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                clearTimeout(timeoutId);

                // Format the date with explicit UTC indicator
                const timestamp = new Date(data.timestamp);
                this.lastUpdated(`${timestamp.toLocaleString()} UTC`);

                // Process and sort environments
                const updatedItems = data.environments.map(env => {
                    // Use nullish coalescing for default values
                    const versionInfo = env.version_info ?? {
                        type: 'Unknown',
                        version: env.version ?? 'Unknown',
                        version_num: 'unknown',
                        branch: 'unknown',
                        hash_short: 'unknown',
                        hash_url: null
                    };

                    // Use nullish coalescing for defaults
                    const branch = versionInfo.branch ?? 'unknown';

                    // Create a formatted version display with commit link and branch
                    const versionDisplay = versionInfo.hash_url
                        ? `<a href="${versionInfo.hash_url}" target="_blank"
                            title="View commit ${versionInfo.hash}" class="version-link">
                            ${versionInfo.version} [${branch}] (${versionInfo.hash_short})</a>`
                        : `${versionInfo.version ?? 'Unknown'} [${branch}]`;

                    // Use optional chaining for cleaner property access
                    const healthStatus = env.health?.status ?? 'Unknown';

                    // Use optional chaining and template literals
                    const instancesDisplay = env.health
                        ? `<span title="Healthy instances / Total instances">${env.health.healthy_targets}/${env.health.total_targets}</span>`
                        : 'N/A';

                    return {
                        name: env.name,
                        description: env.description,
                        version: env.version ?? 'Unknown',
                        versionInfo,
                        versionDisplay,
                        status: healthStatus,
                        statusBadge: this.getStatusBadge(healthStatus),
                        instances: instancesDisplay,
                        url: `<a href="https://${env.url}" target="_blank">${env.url}</a>`,
                        is_production: env.is_production ?? false
                    };
                });

                // Sort environments: production first, then alphabetically by description
                updatedItems.sort((a, b) => {
                    if (a.is_production !== b.is_production) {
                        return b.is_production ? 1 : -1; // Production environments first
                    }
                    return a.description.localeCompare(b.description); // Then alphabetically
                });

                // Update the observable array
                this.items(updatedItems);
                this.isLoading(false);
            })
            .catch(error => {
                clearTimeout(timeoutId);
                console.error('Error fetching status:', error);

                // Improved error message for timeouts and connection issues
                const errorMsg = error.name === 'AbortError'
                    ? 'Request timed out'
                    : `Error loading status data: ${error.message}`;

                this.errorMessage(errorMsg);
                this.hasError(true);
                this.isLoading(false);
            });
    }

    getStatusBadge(status) {
        // Use object literal instead of switch statement
        const badgeClasses = {
            'Online': 'badge-success',
            'Offline': 'badge-danger'
        };

        const badgeClass = badgeClasses[status] ?? 'badge-secondary';
        return `<span class="badge ${badgeClass}">${status}</span>`;
    }

    toggleAutoRefresh() {
        this.autoRefreshEnabled(!this.autoRefreshEnabled());
    }

    // Load auto-refresh setting from localStorage
    loadAutoRefreshSetting() {
        const savedSetting = localStorage.getItem('ce_status_autorefresh');
        return savedSetting === null ? true : savedSetting === 'true';
    }

    // Save auto-refresh setting to localStorage
    saveAutoRefreshSetting(value) {
        localStorage.setItem('ce_status_autorefresh', value.toString());
    }

    // Setup or clear the auto-refresh interval
    setupAutoRefresh(enabled) {
        // Clear any existing interval
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }

        // Setup new interval if enabled
        if (enabled) {
            this.autoRefreshInterval = setInterval(() => this.refreshData(), 15000);
        }
    }
}
