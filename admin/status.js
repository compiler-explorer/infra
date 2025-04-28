class StatusViewModel {
    constructor() {
        this.isLoading = ko.observable(true);
        this.hasError = ko.observable(false);
        this.errorMessage = ko.observable('');
        this.lastUpdated = ko.observable('');
        this.items = ko.observableArray([]);
        this.autoRefreshEnabled = ko.observable(this.loadAutoRefreshSetting());

        // Subscribe to changes of autoRefreshEnabled to save to localStorage
        this.autoRefreshEnabled.subscribe((newValue) => {
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

        // Using the ALB endpoint
        fetch('https://compiler-explorer.com/api/status')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                this.lastUpdated(new Date(data.timestamp).toLocaleString());
                this.items.removeAll();

                data.environments.forEach(env => {
                    const versionInfo = env.version_info || {
                        type: 'Unknown',
                        version: env.version || 'Unknown',
                        version_num: 'unknown',
                        hash_short: 'unknown',
                        hash_url: null
                    };

                    // Create a formatted version display with commit link
                    let versionDisplay;

                    if (versionInfo.hash_url) {
                        // Make entire version text a clickable link to the GitHub commit
                        versionDisplay = `<a href="${versionInfo.hash_url}" target="_blank" title="View commit ${versionInfo.hash}" class="version-link">${versionInfo.version} (${versionInfo.hash_short})</a>`;
                    } else {
                        versionDisplay = versionInfo.version || 'Unknown';
                    }

                    this.items.push({
                        name: env.name,
                        description: env.description,
                        version: env.version || 'Unknown',
                        versionInfo: versionInfo,
                        versionDisplay: versionDisplay,
                        status: env.health ? env.health.status : 'Unknown',
                        statusBadge: this.getStatusBadge(env.health ? env.health.status : 'Unknown'),
                        instances: env.health ?
                            `${env.health.healthy_targets}/${env.health.total_targets}` :
                            'N/A',
                        url: `<a href="https://${env.url}" target="_blank">${env.url}</a>`,
                    });
                });

                this.isLoading(false);
            })
            .catch(error => {
                console.error('Error fetching status:', error);
                this.errorMessage(`Error loading status data: ${error.message}`);
                this.hasError(true);
                this.isLoading(false);
            });
    }

    getStatusBadge(status) {
        let badgeClass = '';
        switch (status) {
            case 'Online':
                badgeClass = 'badge-success';
                break;
            case 'Offline':
                badgeClass = 'badge-danger';
                break;
            default:
                badgeClass = 'badge-secondary';
        }
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
