function formatDate(date) {
    const minutes = date.getUTCMinutes() < 10 ? `0${date.getUTCMinutes()}` : date.getUTCMinutes();
    return `${date.getUTCHours()}:${minutes}  ${date.getUTCDate()}/${date.toLocaleString("en-us", {month: "short"})}`
}

function formatStartDate(item) {
    return formatDate(item.start);
}

function formatEndDate(item) {
    return formatDate(item.end);
}

function styleStatus(item) {
    const style = {
        color: 'black'
    };
    if (item.status === 'OK') {
        style.color = 'green';
    } else if (item.status === 'FAILED') {
        style.color = 'red';
    } else if (item.status === 'SKIPPED') {
        style.color = 'blue';
    }
    return style;
}

function formatDuration(item) {
    let millis = item.duration;

    millis /= 1000;
    let s = Math.floor(millis % 60);
    millis /= 60;
    let m = Math.floor(millis % 60);
    millis /= 60;
    let h = Math.floor(millis);

    h = h < 10 ? ("0" + h) : h;
    m = m < 10 ? ("0" + m) : m;
    s = s < 10 ? ("0" + s) : s;
    return `${h}:${m}:${s}`;
}

function formatLastSuccess(item) {
    if (item.last_success)
        return formatDate(item.last_success);
    return 'UNKNOWN';
}

function styleHeaderSortables() {
    return {cursor: 'pointer'};
}

class BuildsViewModel {
    constructor() {
        this.sortField = ko.observable('name');
        this.sortOrder = ko.observable(1);
        this.intervalId = null;
        this.updateInterval = 1000 * 60;
        this.isLogVisible = ko.observable(false);
        this.lastUpdate = ko.observable();
        this.nextUpdate = ko.observable();
        this.items = ko.observableArray([]);
        this.sortedItems = ko.pureComputed(() => {
            const items = this.items();
            const field = this.sortField();
            const order = this.sortOrder();
            items.sort((lhi, rhi) => {
                return order * (lhi[field] < rhi[field] ? -1 : 1);
            });
            return items;
        });
        this.selectedLog = ko.observable();
        this.gridViewModel = new ko.simpleGrid.viewModel({
            data: this.sortedItems,
            columns: [
                {
                    headerText: "Name",
                    rowText: "name",
                    headerClick: () => this.changeSortOrder('name'),
                    headerStyle: styleHeaderSortables
                },
                {
                    headerText: "Start (UTC)",
                    rowText: formatStartDate,
                    headerClick: () => this.changeSortOrder('start'),
                    headerStyle: styleHeaderSortables
                },
                {
                    headerText: "End (UTC)",
                    rowText: formatEndDate,
                    headerClick: () => this.changeSortOrder('end'),
                    headerStyle: styleHeaderSortables
                },
                {
                    headerText: "Duration (HH:MM:SS)",
                    rowText: formatDuration,
                    headerClick: () => this.changeSortOrder('duration'),
                    headerStyle: styleHeaderSortables
                },
                {
                    headerText: "Last OK",
                    rowText: formatLastSuccess,
                    headerClick: () => this.changeSortOrder('last_success'),
                    headerStyle: styleHeaderSortables
                },
                {
                    headerText: "Status",
                    rowText: "status",
                    headerClick: () => this.changeSortOrder('status'),
                    headerStyle: styleHeaderSortables,
                    style: styleStatus
                },
                {
                    headerText: "Log", rowText: () => "&#x1f4f0;",
                    style: () => {
                        return {cursor: 'pointer'}
                    },
                    click: (item) => {
                        this.selectedLog("Loading...");
                        this.isLogVisible(true);
                        const xhr = new XMLHttpRequest();
                        xhr.open('GET', item.log);
                        xhr.onload = () => {
                            this.selectedLog(xhr.responseText);
                        };
                        xhr.send();
                    }
                }
            ],
            pageSize: 40,
            update: () => this.update()
        });
    }

    clear() {
        this.items.removeAll();
    }

    addItem(item) {
        this.items.push(item);
    }

    update() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
        }
        this.intervalId = setInterval(() => this.update(), this.updateInterval);
        this.nextUpdate(new Date(Date.now() + this.updateInterval).toString());
        const xhr = new XMLHttpRequest();
        xhr.open('GET', 'buildStatus.json');
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.onload = () => {
            this.lastUpdate(new Date().toString());
            const info = JSON.parse(xhr.responseText);
            this.clear();
            Object.keys(info).map(buildKey => {
                const build = info[buildKey];
                this.addItem({
                    name: buildKey,
                    start: new Date(build.begin),
                    end: new Date(build.end),
                    duration: new Date(build.end) - new Date(build.begin),
                    last_success: build.last_success ? new Date(build.last_success) : null,
                    status: build.status.endsWith('\n') ?
                        build.status.substring(0, build.status.length - 1) :
                        build.status,
                    log: build.log,
                    icon: ''
                });
            });
        };
        xhr.send();
    }

    changeSortOrder(name) {
        if (this.sortField() === name)
            this.sortOrder(this.sortOrder() * -1);
        else
            this.sortField(name);
    }
}

function init() {
    const buildsView = new BuildsViewModel();
    ko.applyBindings(buildsView);

    buildsView.update();
}