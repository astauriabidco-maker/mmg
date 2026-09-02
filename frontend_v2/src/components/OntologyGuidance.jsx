import React from 'react';
import {
    ontologyDocumentMapping,
    ontologyEntity,
    ontologyEvents,
    ontologyPermissions,
    ontologyStatuses,
} from '../services/ontology';

const moduleClass = {
    CRM: 'border-blue-200 bg-blue-50 text-blue-800',
    BE: 'border-indigo-200 bg-indigo-50 text-indigo-800',
    DEVIS: 'border-cyan-200 bg-cyan-50 text-cyan-800',
    COMMANDE: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    FABRICATION: 'border-orange-200 bg-orange-50 text-orange-800',
    STOCK: 'border-lime-200 bg-lime-50 text-lime-800',
    DEBIT: 'border-red-200 bg-red-50 text-red-800',
};

function EntityBadge({ entity }) {
    if (!entity) return null;
    return (
        <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${moduleClass[entity.module] || 'border-slate-200 bg-slate-50 text-slate-700'}`}>
            {entity.module}
            <span className="text-slate-400">·</span>
            {entity.label}
        </span>
    );
}

function PermissionPills({ permissions }) {
    if (!permissions.length) return null;
    return (
        <div className="flex flex-wrap gap-1.5">
            {permissions.map(permission => (
                <span key={`${permission.entity}-${permission.action}-${permission.permission}`} className="rounded-md border border-slate-200 bg-white px-2 py-1 text-[9px] font-black uppercase tracking-wider text-slate-600" title={permission.description}>
                    {permission.action} · {permission.permission}
                </span>
            ))}
        </div>
    );
}

export default function OntologyGuidance({
    ontology,
    title = 'Repère métier MMG',
    subtitle,
    entityCodes = [],
    permissionEntities = [],
    eventCodes = [],
    sourceSystem,
    documentType,
    compact = false,
    className = '',
}) {
    if (!ontology) return null;

    const entities = entityCodes.map(code => ontologyEntity(ontology, code)).filter(Boolean);
    const permissions = permissionEntities.flatMap(code => ontologyPermissions(ontology, code));
    const events = ontologyEvents(ontology, eventCodes);
    const mapping = ontologyDocumentMapping(ontology, sourceSystem, documentType);

    return (
        <aside className={`rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm ${className}`}>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400">Ontologie active</p>
                    <h4 className="mt-1 text-sm font-black text-slate-950">{title}</h4>
                    {subtitle && <p className="mt-1 text-xs font-bold leading-5 text-slate-500">{subtitle}</p>}
                </div>
                <PermissionPills permissions={permissions} />
            </div>

            {!!entities.length && (
                <div className="mt-3 flex flex-wrap gap-2">
                    {entities.map(entity => <EntityBadge key={entity.id} entity={entity} />)}
                </div>
            )}

            {!compact && !!entities.length && (
                <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {entities.slice(0, 4).map(entity => (
                        <div key={entity.id} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2">
                            <p className="text-[10px] font-black uppercase tracking-wider text-slate-500">{entity.label}</p>
                            <p className="mt-1 text-xs font-semibold leading-5 text-slate-600">{entity.definition}</p>
                            {!!ontologyStatuses(ontology, entity.id).length && (
                                <p className="mt-1 text-[10px] font-bold text-slate-400">
                                    Statuts : {ontologyStatuses(ontology, entity.id).slice(0, 4).map(status => status.label).join(' → ')}
                                </p>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {mapping && (
                <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2">
                    <p className="text-[10px] font-black uppercase tracking-wider text-amber-700">
                        Classification import · {mapping.source_system}/{mapping.document_type}
                    </p>
                    <p className="mt-1 text-xs font-bold leading-5 text-amber-900">{mapping.label} — {mapping.definition}</p>
                    {!!mapping.forbidden_confusions?.length && (
                        <p className="mt-1 text-[10px] font-black uppercase tracking-wider text-amber-700">
                            À ne pas confondre avec : {mapping.forbidden_confusions.join(', ')}
                        </p>
                    )}
                </div>
            )}

            {!compact && !!events.length && (
                <div className="mt-3 flex flex-wrap gap-2">
                    {events.slice(0, 4).map(event => (
                        <span key={event.code} className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[10px] font-black uppercase tracking-wider text-slate-600" title={event.description}>
                            {event.label}
                        </span>
                    ))}
                </div>
            )}
        </aside>
    );
}
