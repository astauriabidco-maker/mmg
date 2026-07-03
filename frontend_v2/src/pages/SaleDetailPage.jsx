import React, { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, CheckCircle, Copy, FileText, Package, Send, Truck, Undo2, Wrench, X } from 'lucide-react';
import api from '../services/api';

export default function SaleDetailPage({ saleId: saleIdProp, embedded = false }) {
    const params = useParams();
    const saleId = saleIdProp || params.saleId;
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const [busyAction, setBusyAction] = useState(null);
    const pageShellClass = embedded
        ? 'min-h-full bg-slate-100 text-slate-900 font-sans -m-8'
        : 'min-h-screen bg-slate-100 text-slate-900 font-sans';

    const { data: sale, isLoading, refetch } = useQuery({
        queryKey: ['sale-detail', saleId],
        queryFn: async () => {
            const res = await api.get(`/v2/sales/${saleId}`);
            return res.data;
        },
        enabled: Boolean(saleId),
    });

    const formatMoney = (amount) => Number(amount || 0).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
    const formatDate = (value) => value ? new Date(value).toLocaleDateString('fr-FR') : '-';

    const isCreditNote = (invoice) => {
        const status = String(invoice?.status || '').toUpperCase();
        const invoiceType = String(invoice?.invoice_type || '').toUpperCase();
        const reference = String(invoice?.reference || '').toUpperCase();
        return status === 'AVOIR' || status === 'CREDIT_NOTE' || invoiceType === 'CREDIT_NOTE' || reference.startsWith('AV-') || Number(invoice?.total || 0) < 0;
    };
    const isDepositInvoice = (invoice) => String(invoice?.invoice_type || '').toUpperCase() === 'DEPOSIT';

    const trace = useMemo(() => {
        const reservations = sale?.reservations || [];
        const deliveryNotes = sale?.delivery_notes || [];
        const invoices = sale?.invoices || [];
        const billableInvoices = invoices.filter(invoice => !isCreditNote(invoice) && !['DRAFT', 'CANCELLED', 'VOID'].includes(invoice.status));
        const depositInvoices = billableInvoices.filter(isDepositInvoice);
        const finalInvoices = billableInvoices.filter(invoice => !isDepositInvoice(invoice));
        const creditNotes = [
            ...(sale?.credit_notes || []),
            ...(sale?.creditNotes || []),
            ...(sale?.avoirs || []),
            ...invoices.filter(isCreditNote),
        ].filter(Boolean);
        const activeReservations = reservations.filter(reservation => reservation.status === 'reserved');
        const returnedReservations = reservations.filter(reservation => reservation.status === 'returned');
        const returnedDeliveryNotes = deliveryNotes.filter(note => ['RETURNED', 'CANCELLED'].includes(note.status));
        const hasStockLines = (sale?.lines || []).some(line => line.line_type === 'STOCK_ITEM' || line.variant_id);
        const isSigned = Boolean(sale?.signed_at) || ['VALIDATED', 'IN_DESIGN', 'READY_FOR_PROD', 'IN_PRODUCTION', 'DELIVERED'].includes(sale?.status);
        const isReserved = activeReservations.length > 0 || (sale?.lines || []).some(line => Number(line.reserved_quantity || 0) > 0);
        const isReturned = returnedReservations.length > 0 || returnedDeliveryNotes.length > 0;
        const isDelivered = !isReturned && (sale?.status === 'DELIVERED' || deliveryNotes.some(note => note.status === 'DELIVERED' || note.signed_at));
        return {
            reservations,
            deliveryNotes,
            billableInvoices,
            depositInvoices,
            finalInvoices,
            creditNotes,
            activeReservations,
            returnedDeliveryNotes,
            hasStockLines,
            isSigned,
            isReserved,
            isReturned,
            isDelivered,
            hasDepositInvoice: depositInvoices.length > 0,
            isInvoiced: finalInvoices.length > 0,
            hasCreditNote: creditNotes.length > 0,
        };
    }, [sale]);

    const totalHT = useMemo(() => (
        (sale?.lines || []).reduce(
            (sum, line) => sum + (Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100)),
            0
        )
    ), [sale]);

    const activeReservedQty = trace.activeReservations.reduce(
        (sum, reservation) => sum + (reservation.lines || []).reduce((lineSum, line) => lineSum + Number(line.reserved_quantity || 0), 0),
        0
    );

    const workflowLabel = (workflowType) => {
        if (workflowType === 'FABRICATION_FROM_MEASURE') return 'Fabrication depuis métré';
        if (workflowType === 'FABRICATION_ESTIMATE') return 'Pré-devis fabrication';
        return 'Devis libre pièces/prestations';
    };

    const businessLabel = () => {
        if (!sale) return '-';
        if (sale.status === 'CANCELLED') return 'Annulé';
        if (trace.isReturned) return 'Retourné';
        if (trace.isInvoiced) return 'Facturé';
        if (trace.isDelivered) return 'Livré';
        if (trace.isReserved) return 'Réservé';
        if (trace.isSigned) return 'Signé';
        if (sale.status === 'SENT') return 'Envoyé';
        return 'Brouillon';
    };

    const refreshSale = async () => {
        await Promise.all([
            queryClient.invalidateQueries(['sales']),
            queryClient.invalidateQueries(['products']),
            queryClient.invalidateQueries(['quants']),
            queryClient.invalidateQueries(['transactions']),
        ]);
        await refetch();
    };

    const runAction = async (name, fn) => {
        setBusyAction(name);
        try {
            await fn();
            await refreshSale();
        } catch (err) {
            console.error(err);
            alert(err.response?.data?.detail || "Action impossible.");
        } finally {
            setBusyAction(null);
        }
    };

    const updateStatus = (status) => runAction('status', async () => {
        await api.put(`/v2/sales/${sale.id}/status?status=${status}`);
    });

    const deliverFreeSale = () => {
        if (!window.confirm("Confirmer la sortie client ? Le stock réservé sera débité définitivement.")) return;
        runAction('deliver', async () => {
            await api.post(`/v2/sales/${sale.id}/deliver-free-sale`);
        });
    };

    const returnFreeSale = () => {
        if (!window.confirm("Préparer un retour client pour ce devis livré ?")) return;
        runAction('return', async () => {
            await api.post(`/v2/sales/${sale.id}/return-free-sale`);
        });
    };

    const createCreditNote = () => {
        const invoice = trace.finalInvoices[0] || trace.billableInvoices[0];
        const deliveryNote = trace.returnedDeliveryNotes[0];
        if (!invoice) return;
        if (!window.confirm(`Créer un avoir pour la facture ${invoice.reference} ?`)) return;
        runAction('credit-note', async () => {
            await api.post(
                `/v2/accounting/invoices/${invoice.id}/credit-note-from-return`,
                deliveryNote?.id ? { delivery_note_id: deliveryNote.id } : undefined
            );
        });
    };

    const createFinalInvoice = () => {
        if (!window.confirm("Créer la facture finale / solde pour ce devis livré ?")) return;
        runAction('final-invoice', async () => {
            await api.post(`/v2/sales/${sale.id}/create-final-invoice`);
        });
    };

    if (!saleId) {
        return <div className="min-h-[50vh] bg-slate-50 flex items-center justify-center text-sm font-bold text-slate-500">Sélectionnez un devis.</div>;
    }

    if (isLoading) {
        return <div className="min-h-[50vh] bg-slate-50 flex items-center justify-center text-sm font-bold text-slate-500">Chargement du devis...</div>;
    }

    if (!sale) {
        return <div className="min-h-[50vh] bg-slate-50 flex items-center justify-center text-sm font-bold text-slate-500">Devis introuvable.</div>;
    }

    const isFreeSale = (sale.workflow_type || 'FREE_SALE') === 'FREE_SALE';
    const canDeliver = isFreeSale && sale.status === 'VALIDATED' && trace.activeReservations.length > 0;
    const canCreateFinalInvoice = trace.isDelivered && !trace.isInvoiced && !trace.isReturned;
    const canReturn = trace.isDelivered;
    const canCreditNote = trace.isReturned && trace.isInvoiced && !trace.hasCreditNote;
    const timeline = [
        { label: 'Brouillon', done: true, detail: formatDate(sale.created_at) },
        { label: 'Envoyé', done: ['SENT', 'VALIDATED', 'IN_DESIGN', 'READY_FOR_PROD', 'IN_PRODUCTION', 'DELIVERED'].includes(sale.status), detail: sale.status === 'DRAFT' ? 'À envoyer' : 'Client notifié' },
        { label: 'Signé', done: trace.isSigned, detail: sale.signed_at ? formatDate(sale.signed_at) : (trace.isSigned ? 'Validation interne' : 'En attente') },
        { label: 'Acompte', done: trace.hasDepositInvoice || isFreeSale, detail: trace.hasDepositInvoice ? `${trace.depositInvoices.length} facture(s)` : (isFreeSale ? 'Non requis' : 'À émettre') },
        { label: 'Réservé', done: trace.isReserved, detail: trace.isReserved ? `${activeReservedQty.toLocaleString('fr-FR')} réservé` : (trace.hasStockLines ? 'À réserver' : 'Sans stock') },
        { label: 'Livré', done: trace.isDelivered || trace.isReturned, detail: trace.isReturned ? 'Retourné' : (trace.isDelivered ? 'BL généré' : 'À livrer') },
        { label: 'Solde facturé', done: trace.isInvoiced, detail: trace.isInvoiced ? `${trace.finalInvoices.length} facture(s)` : 'À facturer' },
        { label: 'Avoir', done: trace.hasCreditNote, detail: trace.hasCreditNote ? `${trace.creditNotes.length} avoir(s)` : (trace.isReturned ? 'À décider' : 'Non requis') },
    ];

    return (
        <div className={pageShellClass}>
            <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
                <div className="flex items-center justify-between">
                    <button onClick={() => navigate('/manager?view=sales')} className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-slate-200 text-slate-700 font-black hover:bg-slate-50">
                        <ArrowLeft className="w-4 h-4" /> Retour au CRM
                    </button>
                    <div className="flex gap-2">
                        <a href={`${api.defaults.baseURL}/v2/pdf/quote/${sale.id}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-slate-200 text-slate-800 font-black hover:bg-slate-50">
                            <FileText className="w-4 h-4" /> PDF devis
                        </a>
                        {sale.signature_token && (
                            <button
                                onClick={() => {
                                    navigator.clipboard.writeText(`${window.location.origin}/portal/sign/${sale.signature_token}`);
                                    alert("Lien de signature copié.");
                                }}
                                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-indigo-200 text-indigo-700 font-black hover:bg-indigo-50"
                            >
                                <Copy className="w-4 h-4" /> Lien signature
                            </button>
                        )}
                    </div>
                </div>

                <section className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                    <div className="bg-slate-900 text-white px-8 py-7 flex items-start justify-between gap-8">
                        <div>
                            <div className="flex flex-wrap gap-2 mb-4">
                                <span className="px-3 py-1.5 rounded-lg bg-blue-100 text-blue-800 text-[10px] font-black uppercase tracking-widest">{businessLabel()}</span>
                                <span className="px-3 py-1.5 rounded-lg bg-white/90 text-slate-700 text-[10px] font-black uppercase tracking-widest">{workflowLabel(sale.workflow_type)}</span>
                            </div>
                            <h1 className="text-4xl font-black tracking-tight">{sale.client_name}</h1>
                            <div className="mt-4 flex flex-wrap gap-5 text-sm font-bold text-slate-300">
                                <span>{sale.reference}</span>
                                <span>{formatDate(sale.created_at)}</span>
                                <span>{sale.lines?.length || 0} ligne(s)</span>
                            </div>
                        </div>
                        <div className="text-right shrink-0">
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Total HT</p>
                            <p className="text-5xl font-black tracking-tight">{formatMoney(totalHT)}</p>
                            <p className="text-sm font-bold text-slate-400">TVA {sale.tax_rate || 0}% · {sale.currency || 'EUR'}</p>
                        </div>
                    </div>

                    <div className="px-8 py-5 bg-white border-b border-slate-200 flex flex-wrap items-center justify-between gap-4">
                        <div>
                            <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1">Prochaine action</p>
                            <p className="text-sm font-bold text-slate-700">
                                {sale.status === 'DRAFT' ? "Envoyer le devis au client."
                                    : sale.status === 'SENT' ? "Attendre la signature ou valider manuellement."
                                    : canDeliver ? "Sortir les articles réservés quand ils sont remis au client."
                                    : canCreateFinalInvoice ? "Livraison faite: générer la facture finale / solde."
                                    : canCreditNote ? "Retour facturé détecté: créer un avoir si la régularisation est confirmée."
                                    : canReturn ? "Le client a été livré. Un retour reste possible si erreur."
                                    : "Le devis est à jour. Consultez le cycle et les documents liés."}
                            </p>
                        </div>
                        <div className="flex flex-wrap gap-3">
                            {sale.status === 'DRAFT' && (
                                <button onClick={() => updateStatus('SENT')} disabled={busyAction === 'status'} className="px-5 py-3 rounded-xl bg-blue-600 text-white font-black hover:bg-blue-500 disabled:bg-slate-300 inline-flex items-center gap-2">
                                    <Send className="w-4 h-4" /> Envoyer
                                </button>
                            )}
                            {sale.status === 'SENT' && (
                                <button onClick={() => updateStatus('VALIDATED')} disabled={busyAction === 'status'} className="px-5 py-3 rounded-xl bg-emerald-600 text-white font-black hover:bg-emerald-500 disabled:bg-slate-300 inline-flex items-center gap-2">
                                    <CheckCircle className="w-4 h-4" /> Marquer signé
                                </button>
                            )}
                            {canDeliver && (
                                <button onClick={deliverFreeSale} disabled={busyAction === 'deliver'} className="px-5 py-3 rounded-xl bg-emerald-600 text-white font-black hover:bg-emerald-500 disabled:bg-slate-300 inline-flex items-center gap-2">
                                    <Truck className="w-4 h-4" /> Sortie client
                                </button>
                            )}
                            {canCreateFinalInvoice && (
                                <button onClick={createFinalInvoice} disabled={busyAction === 'final-invoice'} className="px-5 py-3 rounded-xl bg-blue-600 text-white font-black hover:bg-blue-500 disabled:bg-slate-300 inline-flex items-center gap-2">
                                    <FileText className="w-4 h-4" /> Facture finale
                                </button>
                            )}
                            {canReturn && (
                                <button onClick={returnFreeSale} disabled={busyAction === 'return'} className="px-5 py-3 rounded-xl bg-white border border-blue-200 text-blue-700 font-black hover:bg-blue-50 disabled:bg-slate-100 inline-flex items-center gap-2">
                                    <Undo2 className="w-4 h-4" /> Retour client
                                </button>
                            )}
                            {canCreditNote && (
                                <button onClick={createCreditNote} disabled={busyAction === 'credit-note'} className="px-5 py-3 rounded-xl bg-rose-600 text-white font-black hover:bg-rose-500 disabled:bg-slate-300 inline-flex items-center gap-2">
                                    <FileText className="w-4 h-4" /> Créer un avoir
                                </button>
                            )}
                            {!['CANCELLED', 'DELIVERED'].includes(sale.status) && (
                                <button onClick={() => updateStatus('CANCELLED')} disabled={busyAction === 'status'} className="px-5 py-3 rounded-xl bg-white border border-red-200 text-red-600 font-black hover:bg-red-50 disabled:bg-slate-100 inline-flex items-center gap-2">
                                    <X className="w-4 h-4" /> Refuser
                                </button>
                            )}
                        </div>
                    </div>
                </section>

                <section className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3">
                    {timeline.map((step, index) => (
                        <div key={step.label} className={`rounded-2xl border p-4 ${step.done ? 'bg-emerald-50 border-emerald-100' : 'bg-white border-slate-200'}`}>
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center mb-3 ${step.done ? 'bg-emerald-500 text-white' : 'bg-slate-200 text-slate-500'}`}>
                                {step.done ? <CheckCircle className="w-4 h-4" /> : <span className="text-xs font-black">{index + 1}</span>}
                            </div>
                            <p className="font-black text-slate-900">{step.label}</p>
                            <p className="text-xs font-bold text-slate-500 mt-1">{step.detail}</p>
                        </div>
                    ))}
                </section>

                <div className="grid grid-cols-[1fr_360px] gap-6 items-start">
                    <main className="space-y-6">
                        <section className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
                            <div className="px-5 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                                <h2 className="text-sm font-black uppercase tracking-widest text-slate-500">Lignes du devis</h2>
                                <span className="text-sm font-black text-slate-700">{sale.lines?.length || 0} ligne(s)</span>
                            </div>
                            <div className="divide-y divide-slate-100">
                                {(sale.lines || []).map((line, index) => {
                                    const lineTotal = Number(line.quantity || 0) * Number(line.unit_price || 0) * (1 - Number(line.discount_pct || 0) / 100);
                                    return (
                                        <div key={line.id || index} className="grid grid-cols-[1fr_150px_80px_140px] gap-4 p-5 items-center">
                                            <div>
                                                <p className="font-black text-slate-900">{line.description}</p>
                                                {line.variant?.reference && <p className="mt-1 text-xs font-mono font-black text-slate-400">{line.variant.reference}</p>}
                                            </div>
                                            <span className={`inline-flex items-center justify-center gap-1 px-3 py-2 rounded-xl border text-[10px] font-black uppercase tracking-widest ${line.line_type === 'STOCK_ITEM' ? 'bg-blue-50 text-blue-700 border-blue-100' : 'bg-emerald-50 text-emerald-700 border-emerald-100'}`}>
                                                {line.line_type === 'STOCK_ITEM' ? <Package className="w-3 h-3" /> : <Wrench className="w-3 h-3" />}
                                                {line.line_type === 'STOCK_ITEM' ? 'Article stock' : 'Prestation'}
                                            </span>
                                            <p className="text-center font-black text-blue-700">{line.quantity}</p>
                                            <p className="text-right font-black text-slate-900">{formatMoney(lineTotal)}</p>
                                        </div>
                                    );
                                })}
                            </div>
                        </section>

                        {sale.notes && (
                            <section className="bg-yellow-50 border border-yellow-100 rounded-2xl p-5">
                                <p className="text-sm font-bold text-yellow-900">{sale.notes}</p>
                            </section>
                        )}
                    </main>

                    <aside className="space-y-6">
                        <section className="bg-white border border-slate-200 rounded-2xl p-5">
                            <h2 className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4">Client</h2>
                            <div className="space-y-3 text-sm font-bold text-slate-700">
                                <p>{sale.client_contact || 'Contact non renseigné'}</p>
                                <p className="break-all">{sale.client_email || 'Email non renseigné'}</p>
                                <p>{sale.client_address || 'Adresse non renseignée'}</p>
                            </div>
                        </section>

                        <section className="bg-white border border-slate-200 rounded-2xl p-5">
                            <h2 className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4">Documents</h2>
                            <div className="space-y-2">
                                <a href={`${api.defaults.baseURL}/v2/pdf/quote/${sale.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-slate-50 p-3 text-sm font-black text-slate-800 hover:bg-slate-100">
                                    <span>Devis PDF</span><FileText className="w-4 h-4" />
                                </a>
                                {trace.depositInvoices.map(invoice => (
                                    <a key={invoice.id} href={`${api.defaults.baseURL}/v2/pdf/invoice/${invoice.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-amber-100 bg-amber-50 p-3 text-sm font-black text-amber-900 hover:bg-amber-100">
                                        <span>Acompte {invoice.reference} · {formatMoney(invoice.total)}</span><FileText className="w-4 h-4" />
                                    </a>
                                ))}
                                {trace.finalInvoices.map(invoice => (
                                    <a key={invoice.id} href={`${api.defaults.baseURL}/v2/pdf/invoice/${invoice.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm font-black text-blue-900 hover:bg-blue-100">
                                        <span>Facture finale {invoice.reference} · {formatMoney(invoice.total)}</span><FileText className="w-4 h-4" />
                                    </a>
                                ))}
                                {trace.creditNotes.map(creditNote => (
                                    <a key={creditNote.id || creditNote.reference} href={`${api.defaults.baseURL}/v2/pdf/invoice/${creditNote.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-rose-100 bg-rose-50 p-3 text-sm font-black text-rose-900 hover:bg-rose-100">
                                        <span>{creditNote.reference || 'Avoir'} · {formatMoney(creditNote.total)}</span><FileText className="w-4 h-4" />
                                    </a>
                                ))}
                                {trace.deliveryNotes.map(note => (
                                    <a key={note.id} href={`${api.defaults.baseURL}/v2/pdf/delivery-note/${note.id}`} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3 rounded-xl border border-emerald-100 bg-emerald-50 p-3 text-sm font-black text-emerald-900 hover:bg-emerald-100">
                                        <span>{note.reference} · {note.status}</span><Truck className="w-4 h-4" />
                                    </a>
                                ))}
                            </div>
                        </section>

                        <section className="bg-white border border-slate-200 rounded-2xl p-5">
                            <h2 className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4">Réservations</h2>
                            {trace.reservations.length > 0 ? (
                                <div className="space-y-3">
                                    {trace.reservations.map(reservation => {
                                        const quantity = (reservation.lines || []).reduce((sum, line) => sum + Number(line.reserved_quantity || 0), 0);
                                        return (
                                            <div key={reservation.id} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
                                                <div className="flex items-start justify-between gap-3">
                                                    <div>
                                                        <p className="text-sm font-black text-slate-900 break-all">{reservation.reference}</p>
                                                        <p className="text-xs font-bold text-slate-500">{formatDate(reservation.created_at)}</p>
                                                    </div>
                                                    <span className="shrink-0 text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-lg bg-white border border-slate-200 text-slate-600">
                                                        {reservation.status}
                                                    </span>
                                                </div>
                                                <p className="mt-2 text-xs font-black uppercase tracking-widest text-slate-500">{quantity.toLocaleString('fr-FR')} unité(s)</p>
                                            </div>
                                        );
                                    })}
                                </div>
                            ) : (
                                <p className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-4 text-sm font-bold text-slate-400">Aucune réservation rattachée.</p>
                            )}
                        </section>
                    </aside>
                </div>
            </div>
        </div>
    );
}
