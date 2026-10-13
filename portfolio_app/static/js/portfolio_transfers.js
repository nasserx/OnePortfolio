// Transfer forms transport raw decimal text. Financial policy lives on the server.
(() => {
    const source = document.getElementById('transfer_source_portfolio_id');
    const destination = document.getElementById('transfer_destination_portfolio_id');
    function updateDestinations(selected = destination.value) {
        destination.replaceChildren(...Array.from(source.options)
            .filter(option => !option.value || option.value !== source.value)
            .map(option => option.cloneNode(true)));
        destination.value = selected === source.value ? '' : selected;
    }
    source.addEventListener('change', () => updateDestinations());

    function openTransfer(data, restoring = false) {
        window.OnePortfolioForms.prepare('transferModal');
        const editing = Boolean(data.id);
        document.getElementById('transferForm').action = data.id
            ? `/portfolios/transfers/edit/${data.id}` : '/portfolios/transfers/add';
        document.getElementById('transferModalTitle').textContent = data.id ? 'Edit Transfer' : 'Transfer';
        for (const field of ['source_portfolio_id', 'destination_portfolio_id', 'amount', 'notes']) {
            document.getElementById(`transfer_${field}`).value = data[field] ?? '';
        }
        source.disabled = !editing;
        document.getElementById('transfer_source_picker').hidden = !editing;
        document.getElementById('transfer_source_context').hidden = editing;
        const contextualSource = document.getElementById('transfer_context_source');
        contextualSource.disabled = editing;
        contextualSource.value = source.value;
        document.getElementById('transfer_source_name').value = source.selectedOptions[0]?.textContent || '';
        updateDestinations(String(data.destination_portfolio_id ?? ''));
        const now = new Date();
        const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
        const date = document.getElementById('transfer_date');
        date.value = restoring ? (data.date ?? '') : (data.date || today);
        if (date._flatpickr && !restoring) date._flatpickr.setDate(date.value, false);
        window.OnePortfolioDialogs.show(document.getElementById('transferModal'));
    }
    const restored = document.getElementById('transferForm').dataset?.restoredTransfer;
    if (restored) {
        document.addEventListener('DOMContentLoaded', () => openTransfer(JSON.parse(restored), true));
    }
    document.addEventListener('click', event => {
        const button = event.target.closest('[data-transfer-action]');
        if (!button) return;
        event.preventDefault();
        event.stopPropagation();
        const data = JSON.parse(button.dataset.transfer || '{}');
        if (button.dataset.transferAction === 'delete') {
            window.OnePortfolioForms.prepare('deleteTransferModal');
            document.getElementById('deleteTransferForm').action = `/portfolios/transfers/delete/${data.id}`;
            window.OnePortfolioDialogs.show(document.getElementById('deleteTransferModal'));
        } else {
            openTransfer(data);
        }
    });
})();
