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

function formatHowLongAgo(date) {
    let difference = new Date() - date;
    let text = '';

    // More than a day?
    if (difference > 86400000) {
        const days = Math.floor(difference / 86400000);
        text += `${days}day `;
        difference = difference % 86400000;
    }
    // More than an hour?
    if (difference > 3600000) {
        const hours = Math.floor(difference / 3600000);
        text += `${hours}h `;
        difference = difference % 3600000;
    }
    // minutes
    text += `${Math.floor(difference / 60000)}min ago`;

    return text;
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

function formatStatus(item) {
    let millis = (item.end - item.start);
    let text = '';
    const hours = Math.floor(millis / 1000 / 60 / 60);
    millis -= hours * 1000 * 60 * 60;
    if (hours > 0) {
        text += `${hours}h `;
    }
    const mins = Math.floor(millis / 1000 / 60);
    millis -= mins * 1000 * 60;
    if (mins > 0 || hours > 0) {
        text += `${mins < 10 ? `0${mins}` : mins}min `;
    }
    const seconds = Math.floor(millis / 1000);
    text += `${seconds < 10 ? `0${seconds}` : seconds}sec`;

    // TODO: Once last_success is fixed, uncomment this to report when the compiler was last built
    // Right now it shows the same day for skipped ones, and it's missing for failed ones
    /*
    if (item.status === 'SKIPPED' && item.last_success) {
        return `${item.status} (${text}) | LAST ${formatDate(item.last_success)}`
    }*/
    return `${item.status} (${text})`
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
                    headerText: "Build Name",
                    rowText: "name",
                    headerClick: () => this.changeSortOrder('name'),
                    headerStyle: styleHeaderSortables
                },
                {
                    headerText: "Build Start (UTC)",
                    rowText: formatStartDate,
                    headerClick: () => this.changeSortOrder('start'),
                    headerStyle: styleHeaderSortables
                },
                {
                    headerText: "Build End (UTC)",
                    rowText: formatEndDate,
                    headerClick: () => this.changeSortOrder('end'),
                    headerStyle: styleHeaderSortables
                },
                {
                    headerText: "Build Status",
                    rowText: formatStatus,
                    style: styleStatus
                },
                {
                    headerText: "Build Log", rowText: () => "&#x1f4f0;",
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
                    status: build.status.endsWith('\n') ?
                        build.status.substring(0, build.status.length - 1) :
                        build.status,
                    log: build.log,
                    icon: '',
                    last_success: new Date(build.last_success)
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