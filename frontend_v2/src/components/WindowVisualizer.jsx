import React from 'react';

export default function WindowVisualizer({ 
    type = "window_1L", // window_1L, window_2L, door_1L, sliding_2L
    width = 1000, // in mm
    height = 1200, // in mm
    color = "#475569", // Frame color (slate-600)
    scale = 0.1, // SVG scaling factor to fit in UI
    hasRollerShutter = false, // Volet roulant intégré
    openingDirection = "left", // left, right, tilt_turn (oscillo)
    glassType = "clear", // clear, frosted
    hasMuntins = false, // croisillons
    bottomPanelHeight = 0 // hauteur soubassement en mm
}) {
    // Basic scaling to fit standard sizes in a reasonable view box
    // 1000mm * 0.1 = 100px
    const svgWidth = width * scale;
    const svgHeight = height * scale;
    const frameThickness = 50 * scale; // 50mm frame
    const mullionThickness = 40 * scale; // 40mm mullion
    const shutterHeight = hasRollerShutter ? 200 * scale : 0; // 200mm coffre volet roulant
    
    // Glass styling
    const glassFill = glassType === 'frosted' ? "rgba(226, 232, 240, 0.9)" : "rgba(14, 165, 233, 0.15)";
    
    // Helper to draw opening lines (dashed triangle pointing to the handle)
    const renderOpeningLines = (x, y, w, h, direction) => {
        if (!direction) return null;
        
        // standard left/right opening: lines point from hinge corners to handle center
        if (direction === 'left') {
            // Hinges on left, Handle on right (pointing to right)
            return (
                <polyline points={`${x},${y} ${x+w},${y+h/2} ${x},${y+h}`} fill="none" stroke="rgba(0,0,0,0.3)" strokeWidth="1" strokeDasharray="4 4" />
            );
        } else if (direction === 'right') {
            // Hinges on right, Handle on left
            return (
                <polyline points={`${x+w},${y} ${x},${y+h/2} ${x+w},${y+h}`} fill="none" stroke="rgba(0,0,0,0.3)" strokeWidth="1" strokeDasharray="4 4" />
            );
        } else if (direction === 'tilt_turn') {
            // Oscillo-battant: both side opening + bottom opening
            return (
                <g>
                    <polyline points={`${x},${y} ${x+w},${y+h/2} ${x},${y+h}`} fill="none" stroke="rgba(0,0,0,0.3)" strokeWidth="1" strokeDasharray="4 4" />
                    <polyline points={`${x},${y+h} ${x+w/2},${y} ${x+w},${y+h}`} fill="none" stroke="rgba(0,0,0,0.3)" strokeWidth="1" strokeDasharray="4 4" />
                </g>
            );
        }
        return null;
    };
    
    // Helper to draw sash content (glass, panel, muntins)
    const renderSashContent = (x, y, w, h) => {
        const panelH = bottomPanelHeight * scale;
        const actualGlassH = h - panelH;
        
        return (
            <g>
                {/* Glass */}
                <rect x={x} y={y} width={w} height={actualGlassH} fill={glassFill} />
                
                {/* Muntins (Croisillons) - simple cross */}
                {hasMuntins && actualGlassH > 0 && (
                    <g>
                        <line x1={x + w/2} y1={y} x2={x + w/2} y2={y + actualGlassH} stroke={color} strokeWidth={4 * scale} />
                        <line x1={x} y1={y + actualGlassH/2} x2={x + w} y2={y + actualGlassH/2} stroke={color} strokeWidth={4 * scale} />
                    </g>
                )}
                
                {/* Bottom Solid Panel (Soubassement) */}
                {panelH > 0 && (
                    <g>
                        <rect x={x} y={y + actualGlassH} width={w} height={panelH} fill="#f1f5f9" stroke={color} strokeWidth={2 * scale} />
                        {/* Panel decorative inner frame */}
                        <rect x={x + 10} y={y + actualGlassH + 10} width={w - 20} height={panelH - 20} fill="none" stroke={color} strokeWidth={1 * scale} />
                    </g>
                )}
                
                {/* Sash Frame (Over everything to keep border clean) */}
                <rect x={x} y={y} width={w} height={h} fill="none" stroke={color} strokeWidth={frameThickness*0.6} />
            </g>
        );
    };

    const renderDrawing = () => {
        switch (type) {
            case 'window_1L':
                return (
                    <g>
                        {/* Roller Shutter */}
                        {hasRollerShutter && <rect x="0" y={-shutterHeight} width={svgWidth} height={shutterHeight} fill="#e2e8f0" stroke="#94a3b8" />}
                        {/* Outer Frame */}
                        <rect x="0" y="0" width={svgWidth} height={svgHeight} fill="none" stroke={color} strokeWidth={frameThickness} />
                        {/* Sash Content */}
                        {renderSashContent(frameThickness, frameThickness, svgWidth - frameThickness*2, svgHeight - frameThickness*2)}
                        {/* Opening lines */}
                        {renderOpeningLines(frameThickness, frameThickness, svgWidth - frameThickness*2, svgHeight - frameThickness*2, openingDirection)}
                        {/* Handle */}
                        <rect x={openingDirection === 'right' ? frameThickness + 5 : svgWidth - frameThickness - 9} y={svgHeight/2 - 10} width={4} height={20} fill="#94a3b8" />
                    </g>
                );
            case 'window_2L':
                return (
                    <g>
                        {/* Roller Shutter */}
                        {hasRollerShutter && <rect x="0" y={-shutterHeight} width={svgWidth} height={shutterHeight} fill="#e2e8f0" stroke="#94a3b8" />}
                        {/* Outer Frame */}
                        <rect x="0" y="0" width={svgWidth} height={svgHeight} fill="none" stroke={color} strokeWidth={frameThickness} />
                        {/* Center Mullion */}
                        <rect x={svgWidth/2 - mullionThickness/2} y={0} width={mullionThickness} height={svgHeight} fill={color} />
                        {/* Left Sash Content */}
                        {renderSashContent(frameThickness, frameThickness, svgWidth/2 - frameThickness - mullionThickness/2, svgHeight - frameThickness*2)}
                        {renderOpeningLines(frameThickness, frameThickness, svgWidth/2 - frameThickness - mullionThickness/2, svgHeight - frameThickness*2, 'right')}
                        {/* Right Sash Content */}
                        {renderSashContent(svgWidth/2 + mullionThickness/2, frameThickness, svgWidth/2 - frameThickness - mullionThickness/2, svgHeight - frameThickness*2)}
                        {renderOpeningLines(svgWidth/2 + mullionThickness/2, frameThickness, svgWidth/2 - frameThickness - mullionThickness/2, svgHeight - frameThickness*2, openingDirection === 'tilt_turn' ? 'tilt_turn' : 'left')}
                        {/* Handles */}
                        <rect x={svgWidth/2 - mullionThickness/2 - 10} y={svgHeight/2 - 10} width={4} height={20} fill="#94a3b8" />
                        <rect x={svgWidth/2 + mullionThickness/2 + 6} y={svgHeight/2 - 10} width={4} height={20} fill="#94a3b8" />
                    </g>
                );
            case 'sliding_2L':
                return (
                    <g>
                        {/* Roller Shutter */}
                        {hasRollerShutter && <rect x="0" y={-shutterHeight} width={svgWidth} height={shutterHeight} fill="#e2e8f0" stroke="#94a3b8" />}
                        {/* Outer Frame */}
                        <rect x="0" y="0" width={svgWidth} height={svgHeight} fill="none" stroke={color} strokeWidth={frameThickness} />
                        {/* Left Sliding Sash Content (Back) */}
                        {renderSashContent(frameThickness, frameThickness, svgWidth/2 - frameThickness/2, svgHeight - frameThickness*2)}
                        {/* Right Sliding Sash Content (Front) */}
                        {renderSashContent(svgWidth/2, frameThickness, svgWidth/2 - frameThickness, svgHeight - frameThickness*2)}
                        <line x1={svgWidth/2} y1={frameThickness} x2={svgWidth/2} y2={svgHeight - frameThickness} stroke="rgba(0,0,0,0.3)" strokeWidth="2" />
                    </g>
                );
            case 'door_1L':
                return (
                    <g>
                        {/* Outer Frame (Bottom open) */}
                        <polyline points={`0,${svgHeight} 0,0 ${svgWidth},0 ${svgWidth},${svgHeight}`} fill="none" stroke={color} strokeWidth={frameThickness} />
                        {/* Door Leaf Content */}
                        {renderSashContent(frameThickness, frameThickness, svgWidth - frameThickness*2, svgHeight - frameThickness)}
                        {/* Handle */}
                        <circle cx={svgWidth - frameThickness - 15} cy={svgHeight/2} r={4} fill="#94a3b8" />
                        <rect x={svgWidth - frameThickness - 20} y={svgHeight/2} width={15} height={4} fill="#94a3b8" />
                    </g>
                );
            default:
                return <rect x="0" y="0" width={svgWidth} height={svgHeight} fill="#f1f5f9" stroke="#cbd5e1" />;
        }
    };

    return (
        <div className="flex flex-col items-center justify-center p-4">
            <div className="relative inline-block" style={{ width: svgWidth + 40, height: svgHeight + shutterHeight + 40 }}>
                {/* SVG Drawing */}
                <svg width={svgWidth} height={svgHeight + shutterHeight} style={{ position: 'absolute', top: 20, left: 20, overflow: 'visible' }}>
                    <g transform={`translate(0, ${shutterHeight})`}>
                        {renderDrawing()}
                    </g>
                </svg>
                
                {/* Top Dimension (Width) */}
                <div className="absolute top-0 left-[20px] h-[20px] border-b border-slate-400 flex items-center justify-center text-[10px] font-mono text-slate-500" style={{ width: svgWidth }}>
                    <div className="bg-white px-1 -mb-5">{width} mm</div>
                    {/* Arrows */}
                    <div className="absolute left-0 -mb-5 border-l border-slate-400 h-2"></div>
                    <div className="absolute right-0 -mb-5 border-r border-slate-400 h-2"></div>
                </div>

                {/* Left Dimension (Height includes shutter) */}
                <div className="absolute left-0 w-[20px] border-r border-slate-400 flex flex-col items-center justify-center text-[10px] font-mono text-slate-500" style={{ top: 20, height: svgHeight + shutterHeight }}>
                    <div className="bg-white py-1 -mr-6 rotate-[-90deg] whitespace-nowrap">{height} mm</div>
                    {/* Arrows */}
                    <div className="absolute top-0 -mr-5 border-t border-slate-400 w-2"></div>
                    <div className="absolute bottom-0 -mr-5 border-b border-slate-400 w-2"></div>
                </div>
            </div>
        </div>
    );
}
