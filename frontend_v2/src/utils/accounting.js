// Use the backend's derived balance; original fiscal totals/status stay intact.
export function invoiceAccounting(invoice) {
    const isNote = invoice.status === 'AVOIR' || invoice.invoice_type === 'CREDIT_NOTE';
    const ready = invoice.balance_due != null && invoice.accounting_status != null;
    return {
        status: invoice.accounting_status || invoice.status,
        due: ready ? Number(invoice.balance_due) : 0,
        credit: ready ? Number(invoice.customer_credit || 0) : 0,
        refund: ready ? Number(invoice.refund_due || 0) : 0,
        canPay: ready && !isNote && invoice.can_pay === true,
        canRemind: ready && !isNote && invoice.can_remind === true,
        canCredit: ready && !isNote && invoice.can_credit === true,
    };
}

export function accountingTotals(invoices) {
    return invoices.reduce((totals, invoice) => {
        const balance = invoiceAccounting(invoice);
        if (!['DRAFT', 'CANCELLED', 'VOID'].includes(invoice.status)) {
            totals.revenue += Number(invoice.total || 0);
            if (invoice.status !== 'AVOIR' && invoice.invoice_type !== 'CREDIT_NOTE') {
                totals.paid += Number(invoice.total_paid ?? invoice.payments?.reduce((sum, payment) => sum + Number(payment.amount || 0), 0) ?? 0);
            }
            totals.due += balance.due;
            totals.credit += balance.credit;
            totals.refund += balance.refund;
        }
        return totals;
    }, { revenue: 0, paid: 0, due: 0, credit: 0, refund: 0 });
}
