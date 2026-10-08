// Transfer forms transport raw decimal text. Financial policy lives on the server.
(() => {
    function openTransfer(data) {
        document.getElementById('transferForm').action = data.id
            ? `/portfolios/transfers/edit/${data.id}` : '/portfolios/transfers/add';
        document.getElementById('transferModalTitle').textContent = data.id ? 'Edit Transfer' : 'Transfer';
        for (const field of ['source_portfolio_id', 'destination_portfolio_id', 'amount', 'notes']) {
            document.getElementById(`transfer_${field}`).value = data[field] ?? '';
        }
        const now = new Date();
        const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
        const date = document.getElementById('transfer_date');
        date.value = data.date || today;
        if (date._flatpickr) date._flatpickr.setDate(date.value, false);
        bootstrap.Modal.getOrCreateInstance(document.getElementById('transferModal')).show();
    }
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-transfer-action]');
        if (!button) return;
        event.preventDefault();
        event.stopPropagation();
        const data = JSON.parse(button.dataset.transfer || '{}');
        if (button.dataset.transferAction === 'delete') {
            document.getElementById('deleteTransferForm').action = `/portfolios/transfers/delete/${data.id}`;
            bootstrap.Modal.getOrCreateInstance(document.getElementById('deleteTransferModal')).show();
        } else {
            openTransfer(data);
        }
    });
})();
