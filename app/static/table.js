class Table {
    constructor(selector, apiUrl, headers, keys) {
        this.table = document.querySelector(selector);
        this.apiUrl = apiUrl;
        this.headers = headers;
        this.keys = keys;
        this.tbody = this.table.querySelector('tbody');
        this.prevButton = document.getElementById('prev-button');
        this.nextButton = document.getElementById('next-button');
        this.pageInfo = document.getElementById('page-info');
        this.currentPage = 1;

        this.prevButton.addEventListener('click', () => this.changePage(this.currentPage - 1));
        this.nextButton.addEventListener('click', () => this.changePage(this.currentPage + 1));
    }

    fetchData() {
        fetch(`${this.apiUrl}?page=${this.currentPage}`)
            .then(response => response.json())
            .then(data => {
                this.renderTable(data.items);
                this.renderPagination(data._meta, data._links);
            });
    }

    renderTable(items) {
        this.tbody.innerHTML = '';
        items.forEach(item => {
            const row = document.createElement('tr');
            this.keys.forEach(key => {
                const cell = document.createElement('td');
                let value = key.split('.').reduce((o, i) => o[i], item);
                if (typeof value === 'object' && value !== null) {
                    value = Object.values(value).join(', ');
                }
                cell.textContent = value;
                row.appendChild(cell);
            });
            this.tbody.appendChild(row);
        });
    }

    renderPagination(meta, links) {
        this.currentPage = meta.page;
        this.pageInfo.textContent = `Page ${meta.page} of ${meta.total_pages}`;
        this.prevButton.disabled = !links.prev;
        this.nextButton.disabled = !links.next;
    }

    changePage(page) {
        this.currentPage = page;
        this.fetchData();
    }
}