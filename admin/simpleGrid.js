/**
 * SimpleGrid for Knockout.js
 * Based on the example Knockout SimpleGrid, modified for Compiler Explorer admin pages
 * Original source: https://knockoutjs.com/examples/grid.html
 */
(function () {
    // Private function
    function getColumnsForScaffolding(data) {
        if ((typeof data.length !== 'number') || data.length === 0) {
            return [];
        }

        const columns = [];
        for (const propertyName in data[0]) {
            columns.push({ headerText: propertyName, rowText: propertyName });
        }
        return columns;
    }

    ko.simpleGrid = {
        // Defines a view model class you can use to populate a grid
        viewModel: function (configuration) {
            this.data = configuration.data;
            this.currentPageIndex = ko.observable(0);
            this.pageSize = configuration.pageSize || 5;
            this.update = configuration.update;
            // If you don't specify columns configuration, we'll use scaffolding
            this.columns = configuration.columns || getColumnsForScaffolding(ko.unwrap(this.data));

            this.itemsOnCurrentPage = ko.computed(() => {
                const startIndex = this.pageSize * this.currentPageIndex();
                return ko.unwrap(this.data).slice(startIndex, startIndex + this.pageSize);
            }, this);

            this.maxPageIndex = ko.computed(() => {
                return Math.ceil(ko.unwrap(this.data).length / this.pageSize) - 1;
            }, this);
        }
    };

    // Templates used to render the grid
    const templateEngine = new ko.nativeTemplateEngine();

    // Improved template adding without using document.write
    templateEngine.addTemplate = function(templateName, templateMarkup) {
        // Create the script element properly
        const script = document.createElement('script');
        script.type = 'text/html';
        script.id = templateName;
        script.textContent = templateMarkup;

        // Add to document head or body
        if (document.head) {
            document.head.appendChild(script);
        } else if (document.body) {
            document.body.appendChild(script);
        } else {
            // Fallback for older browsers
            document.write(`<script type='text/html' id='${templateName}'>${templateMarkup}<\/script>`);
        }
    };

    templateEngine.addTemplate("ko_simpleGrid_grid", `
        <table class="ko-grid" cellspacing="0">
            <thead>
                <tr data-bind="foreach: columns">
                   <th data-bind="text: headerText,
                    attr: { title: typeof headerTitle !== 'undefined' ? headerTitle : '' },
                    click: typeof headerClick === 'function' ? function () { headerClick($root) }: {},
                    style: typeof headerStyle === 'function' ? headerStyle($root) : {}"></th>
                </tr>
            </thead>
            <tbody data-bind="foreach: itemsOnCurrentPage">
               <tr data-bind="foreach: $parent.columns">
                   <td data-bind="html: typeof rowText === 'function' ? rowText($parent) : $parent[rowText],
                    style: typeof style === 'function' ? style($parent) : {},
                    click: typeof click === 'function' ? function () { click($parent) } : undefined"></td>
                </tr>
            </tbody>
        </table>`);

    templateEngine.addTemplate("ko_simpleGrid_pageLinks", `
        <div class="ko-grid-pageLinks">
            <span data-bind="click: update">&#8635;</span>
            <span>Page:</span>
            <!-- ko foreach: ko.utils.range(0, maxPageIndex) -->
                   <a href="#" data-bind="text: $data + 1, click: function() { $root.currentPageIndex($data) }, css: { selected: $data == $root.currentPageIndex() }">
                </a>
            <!-- /ko -->
        </div>`);

    // The "simpleGrid" binding
    ko.bindingHandlers.simpleGrid = {
        init: function() {
            return { 'controlsDescendantBindings': true };
        },
        // This method is called to initialize the node, and will also be called again if you change what the grid is bound to
        update: function (element, viewModelAccessor, allBindings) {
            const viewModel = viewModelAccessor();

            // Empty the element
            while(element.firstChild) {
                ko.removeNode(element.firstChild);
            }

            // Allow the default templates to be overridden
            const gridTemplateName = allBindings.get('simpleGridTemplate') || "ko_simpleGrid_grid";
            const pageLinksTemplateName = allBindings.get('simpleGridPagerTemplate') || "ko_simpleGrid_pageLinks";

            // Render the main grid
            const gridContainer = element.appendChild(document.createElement("div"));
            ko.renderTemplate(gridTemplateName, viewModel, { templateEngine: templateEngine }, gridContainer, "replaceNode");

            // Render the page links
            const pageLinksContainer = element.appendChild(document.createElement("div"));
            ko.renderTemplate(pageLinksTemplateName, viewModel, { templateEngine: templateEngine }, pageLinksContainer, "replaceNode");
        }
    };
})();
