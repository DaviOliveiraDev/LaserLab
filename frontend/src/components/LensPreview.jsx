import React, { useState, useEffect, useMemo } from 'react';

export default function LensPreview({ selectedJob, backendUrl, machineStatus }) {
  const [svgContent, setSvgContent] = useState('');
  const [gcodeText, setGcodeText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  // Fetch live SVG calculation from backend
  useEffect(() => {
    if (!selectedJob) {
      setSvgContent('');
      return;
    }

    let active = true;
    setLoading(true);
    setError(false);

    fetch(`${backendUrl}/api/jobs/${selectedJob.id}/preview`)
      .then((res) => {
        if (!res.ok) throw new Error('Preview not ready');
        return res.text();
      })
      .then((data) => {
        if (active) {
          setSvgContent(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (active) {
          console.error(err);
          setSvgContent('');
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [selectedJob?.id, selectedJob?.status, selectedJob?.updated_at, backendUrl]);

  // Fetch G-code file text if job is selected
  useEffect(() => {
    if (!selectedJob) {
      setGcodeText('');
      return;
    }

    let active = true;
    fetch(`${backendUrl}/api/jobs/${selectedJob.id}/gcode`)
      .then((res) => {
        if (res.ok) return res.text();
        return '';
      })
      .then((data) => {
        if (active) {
          setGcodeText(data);
        }
      })
      .catch((err) => {
        if (active) {
          console.error('Error fetching G-code:', err);
        }
      });

    return () => {
      active = false;
    };
  }, [selectedJob?.id, backendUrl]);

  // Dimensions of SVG based on geometry bounding box
  const svgDimensions = useMemo(() => {
    if (!selectedJob?.geometry_json?.bbox) return { width: 90, height: 80, cx: 45, cy: 40 };
    const bbox = selectedJob.geometry_json.bbox;
    const width = Math.ceil(bbox.width + 20);
    const height = Math.ceil(bbox.height + 20);
    return {
      width,
      height,
      cx: width / 2.0,
      cy: height / 2.0
    };
  }, [selectedJob]);

  // Parse G-code into coordinate points
  const gcodePoints = useMemo(() => {
    if (!gcodeText) return [];
    
    let currentX = 0;
    let currentY = 0;
    let laserOn = false;
    const points = [];
    
    gcodeText.split('\n').forEach((line) => {
      const trimLine = line.trim().toUpperCase();
      
      if (trimLine.startsWith('M3') || trimLine.startsWith('M4') || trimLine.includes('S')) {
        laserOn = true;
      } else if (trimLine.startsWith('M5')) {
        laserOn = false;
      }
      
      const mx = /X(-?\d+\.?\d*)/i.exec(trimLine);
      const my = /Y(-?\d+\.?\d*)/i.exec(trimLine);
      
      if (mx) currentX = parseFloat(mx[1]);
      if (my) currentY = parseFloat(my[1]);
      
      if (mx || my) {
        points.push({ x: currentX, y: currentY, laserOn });
      }
    });
    
    return points;
  }, [gcodeText]);

  // Find active coordinates based on machine telemetry status
  const laserStatus = useMemo(() => {
    if (!machineStatus || machineStatus.status !== 'PROCESSING' || gcodePoints.length === 0) {
      return null;
    }

    const { current_gcode_index } = machineStatus;
    // index from telemetry is 1-indexed, match it to points array
    const activeIdx = Math.min(Math.max(0, current_gcode_index - 1), gcodePoints.length - 1);
    const activePoint = gcodePoints[activeIdx];

    if (!activePoint) return null;

    // Convert physical physical centers (0,0 is typical center) to SVG coordinates
    // SVG positive Y is down, physical positive Y is up
    const svgX = svgDimensions.cx + activePoint.x;
    const svgY = svgDimensions.cy - activePoint.y;

    // Build fading trails (take last 20 segments)
    const trails = [];
    const trailSize = 25;
    for (let i = 0; i < trailSize; i++) {
      const idx = activeIdx - i;
      if (idx >= 0 && gcodePoints[idx]) {
        const pt = gcodePoints[idx];
        trails.push({
          x: svgDimensions.cx + pt.x,
          y: svgDimensions.cy - pt.y,
          laserOn: pt.laserOn,
          opacity: 1.0 - (i / trailSize)
        });
      }
    }

    return {
      x: svgX,
      y: svgY,
      laserOn: activePoint.laserOn,
      trails
    };
  }, [machineStatus, gcodePoints, svgDimensions]);

  if (!selectedJob) {
    return (
      <div className="empty-state">
        <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M8 12h8" />
        </svg>
        <h3>Nenhum Pedido Selecionado</h3>
        <p>Selecione um pedido na fila lateral para visualizar a geometria e marcações.</p>
      </div>
    );
  }

  const isStreaming = machineStatus?.status === 'PROCESSING' && machineStatus?.current_job_id === selectedJob.id;

  return (
    <div className="preview-panel relative-position">
      {loading && <div className="empty-state"><h3>Carregando Preview...</h3></div>}
      
      {error && (
        <div className="empty-state">
          <h3 style={{ color: 'var(--red-glow)' }}>Erro de Visualização</h3>
          <p>O arquivo SVG não pôde ser gerado ou o pedido está com falhas.</p>
        </div>
      )}

      {!loading && !error && svgContent && (
        <div className="lens-viewport-container">
          {/* Main Background CAD outline SVG */}
          <div 
            className="svg-viewport" 
            dangerouslySetInnerHTML={{ __html: svgContent }} 
          />

          {/* Glowing Galvo Laser overlays if actively engraving */}
          {isStreaming && laserStatus && (
            <svg 
              className="laser-overlay-svg"
              viewBox={`0 0 ${svgDimensions.width} ${svgDimensions.height}`}
              width="100%"
              height="100%"
            >
              <defs>
                {/* Cyan Glow Filter */}
                <filter id="cyan-laser-glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="0.8" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                
                {/* Thermal Orange Glow Filter */}
                <filter id="orange-burn-glow" x="-20%" y="-20%" width="140%" height="140%">
                  <feGaussianBlur stdDeviation="0.4" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>

              {/* Fading Thermal Heat Trail (fading orange/red strokes) */}
              {laserStatus.trails.map((pt, i) => {
                if (i === 0 || !pt.laserOn) return null;
                const prevPt = laserStatus.trails[i - 1];
                if (!prevPt || !prevPt.laserOn) return null;

                return (
                  <line
                    key={i}
                    x1={prevPt.x}
                    y1={prevPt.y}
                    x2={pt.x}
                    y2={pt.y}
                    stroke={`rgba(249, 115, 22, ${pt.opacity})`}
                    strokeWidth="0.85"
                    strokeLinecap="round"
                    filter="url(#orange-burn-glow)"
                  />
                );
              })}

              {/* Active Galvo Laser Mirror Scan Beam Projection */}
              {laserStatus.laserOn && (
                <line
                  x1={svgDimensions.cx}
                  y1={0}
                  x2={laserStatus.x}
                  y2={laserStatus.y}
                  stroke="rgba(34, 211, 238, 0.45)"
                  strokeWidth="0.3"
                  strokeDasharray="2, 1"
                  filter="url(#cyan-laser-glow)"
                />
              )}

              {/* Glowing Laser Spot contact point */}
              {laserStatus.laserOn && (
                <circle
                  cx={laserStatus.x}
                  cy={laserStatus.y}
                  r="0.9"
                  fill="#22d3ee"
                  filter="url(#cyan-laser-glow)"
                />
              )}
            </svg>
          )}
        </div>
      )}

      {/* Floating Metadata Overlay */}
      {selectedJob.geometry_json && (
        <div className="lens-metadata-overlay">
          <div className="meta-pill">
            Olho: <strong>{selectedJob.eye === 'R' ? 'Direito (OD)' : 'Esquerdo (OS)'}</strong>
          </div>
          <div className="meta-pill">
            Eixo: <strong>{selectedJob.axis}°</strong>
          </div>
          <div className="meta-pill">
            Adição: <strong>+{selectedJob.addition.toFixed(2)}</strong>
          </div>
          <div className="meta-pill">
            Diâmetro: <strong>{selectedJob.diameter} mm</strong>
          </div>
          {selectedJob.geometry_json.parameters && (
            <div className="meta-pill">
              Base: <strong>{selectedJob.geometry_json.parameters.base_curve.toFixed(1)} D</strong>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
