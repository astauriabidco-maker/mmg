import React from 'react';
import { ArrowRight, CheckCircle, Clock, MinusCircle, XCircle } from 'lucide-react';
import { buildSaleBusinessTimeline } from '../utils/saleBusinessTimeline';

const stateClasses = {
    done: 'bg-emerald-50 border-emerald-100 text-emerald-900',
    active: 'bg-blue-50 border-blue-200 text-blue-950 shadow-sm',
    todo: 'bg-slate-50 border-slate-200 text-slate-700',
    skipped: 'bg-slate-50 border-slate-200 text-slate-400',
    blocked: 'bg-red-50 border-red-100 text-red-900',
};

const dotClasses = {
    done: 'bg-emerald-500 text-white',
    active: 'bg-blue-600 text-white',
    todo: 'bg-slate-200 text-slate-500',
    skipped: 'bg-slate-100 text-slate-400',
    blocked: 'bg-red-500 text-white',
};

const stateLabels = {
    done: 'Fait',
    active: 'En cours',
    todo: 'À venir',
    skipped: 'Non requis',
    blocked: 'Arrêt',
};

function StepIcon({ state, index }) {
    if (state === 'done') return <CheckCircle className="h-3.5 w-3.5" />;
    if (state === 'active') return <Clock className="h-3.5 w-3.5" />;
    if (state === 'skipped') return <MinusCircle className="h-3.5 w-3.5" />;
    if (state === 'blocked') return <XCircle className="h-3.5 w-3.5" />;
    return <span className="text-[10px] font-black">{index + 1}</span>;
}

export default function BusinessTimeline({
    sale,
    compact = false,
    title = 'Timeline métier',
    subtitle = 'De la signature client au paiement final.',
    actions = {},
    busyAction = null,
}) {
    const timeline = buildSaleBusinessTimeline(sale);
    const activeStep = timeline.steps[timeline.activeIndex] || timeline.steps[0];

    if (compact) {
        return (
            <div className="mt-3">
                <div className="flex items-center gap-1.5">
                    {timeline.steps.map((step, index) => (
                        <div
                            key={step.key}
                            title={`${step.label} · ${step.detail}`}
                            className={`h-1.5 flex-1 rounded-full ${step.state === 'done' ? 'bg-emerald-400' : step.state === 'active' ? 'bg-blue-600' : step.state === 'blocked' ? 'bg-red-300' : 'bg-slate-200'}`}
                        />
                    ))}
                </div>
                <p className={`mt-1 text-[10px] font-black uppercase tracking-widest ${activeStep?.state === 'blocked' ? 'text-red-500' : 'text-slate-400'}`}>
                    {activeStep?.label || 'Timeline'}
                </p>
            </div>
        );
    }

    return (
        <section className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">{title}</p>
                <p className="mt-1 text-sm font-bold text-slate-600">{subtitle}</p>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-9 gap-2 p-4">
                {timeline.steps.map((step, index) => {
                    const rawAction = step.actionKey ? actions[step.actionKey] : null;
                    const action = typeof rawAction === 'function'
                        ? { onClick: rawAction, label: step.actionLabel || 'Traiter' }
                        : rawAction;
                    const showAction = action && typeof action.onClick === 'function';
                    return (
                    <div key={step.key} className={`rounded-2xl border p-3 min-h-[92px] flex flex-col ${stateClasses[step.state] || stateClasses.todo}`}>
                        <div className="mb-2 flex items-center gap-2">
                            <span className={`flex h-6 w-6 items-center justify-center rounded-full ${dotClasses[step.state] || dotClasses.todo}`}>
                                <StepIcon state={step.state} index={index} />
                            </span>
                            <span className="text-[10px] font-black uppercase tracking-widest opacity-70">{stateLabels[step.state] || 'À venir'}</span>
                        </div>
                        <p className="text-sm font-black leading-tight text-slate-900">{step.label}</p>
                        <p className="mt-1 text-xs font-bold text-slate-500">{step.detail}</p>
                        {showAction && (
                            <button
                                type="button"
                                onClick={action.onClick}
                                disabled={action.disabled || busyAction === step.actionKey}
                                className="mt-3 inline-flex items-center justify-center gap-1.5 rounded-xl bg-slate-900 px-3 py-2 text-[11px] font-black text-white hover:bg-slate-700 disabled:bg-slate-300 disabled:text-slate-500"
                            >
                                {busyAction === step.actionKey ? 'Traitement...' : action.label}
                                <ArrowRight className="h-3 w-3" />
                            </button>
                        )}
                    </div>
                    );
                })}
            </div>
        </section>
    );
}
