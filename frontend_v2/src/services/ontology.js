import { useQuery } from '@tanstack/react-query';
import api from './api';

export function useMMGOntology() {
    return useQuery({
        queryKey: ['mmg-business-ontology'],
        queryFn: async () => (await api.get('/v2/mmg/ontology')).data,
        staleTime: 5 * 60 * 1000,
        retry: 1,
    });
}

export const ontologyEntity = (ontology, code) => ontology?.entities?.[code] || null;

export const ontologyStatuses = (ontology, code) => ontology?.entity_statuses?.[code] || [];

export const ontologyPermissions = (ontology, entityCode) => (
    ontology?.step_rbac || []
).filter(permission => permission.entity === entityCode);

export const ontologyEvents = (ontology, codes = []) => {
    const allEvents = ontology?.business_events || [];
    return codes.length
        ? allEvents.filter(event => codes.includes(event.code))
        : allEvents;
};

export const ontologyDocumentMapping = (ontology, sourceSystem, documentType) => {
    const normalizedSource = String(sourceSystem || '').toUpperCase();
    const normalizedType = String(documentType || '').toUpperCase();
    if (!normalizedSource || normalizedSource === 'AUTO' || !normalizedType) return null;
    return (ontology?.external_document_mappings || []).find(mapping => (
        mapping.source_system === normalizedSource && mapping.document_type === normalizedType
    )) || null;
};
