const CLOSED_STAGES = new Set(['GAGNE', 'PERDU', 'WON', 'LOST', 'CANCELLED', 'CLOSED']);

// The backend synchronizes the won stage on signature; a sale ID can be a draft quote.
export const isConvertedOpportunity = opportunity => (
    ['GAGNE', 'WON'].includes(String(opportunity.stage || '').toUpperCase())
);

export const isOpenOpportunity = opportunity => (
    !CLOSED_STAGES.has(String(opportunity.stage || '').toUpperCase())
);
