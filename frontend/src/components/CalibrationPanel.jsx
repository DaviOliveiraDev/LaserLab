import React, { useState, useEffect } from 'react';

export default function CalibrationPanel({ calibration, onSaveCalibration }) {
  const [offsetX, setOffsetX] = useState(0.0);
  const [offsetY, setOffsetY] = useState(0.0);
  const [scaleX, setScaleX] = useState(1.0);
  const [scaleY, setScaleY] = useState(1.0);
  const [rotation, setRotation] = useState(0.0);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (calibration) {
      setOffsetX(calibration.offset_x);
      setOffsetY(calibration.offset_y);
      setScaleX(calibration.scale_x);
      setScaleY(calibration.scale_y);
      setRotation(calibration.rotation);
    }
  }, [calibration]);

  const handleSubmit = (e) => {
    e.preventDefault();
    setSaving(true);
    
    const updatedData = {
      offset_x: parseFloat(offsetX),
      offset_y: parseFloat(offsetY),
      scale_x: parseFloat(scaleX),
      scale_y: parseFloat(scaleY),
      rotation: parseFloat(rotation),
    };

    onSaveCalibration(updatedData).finally(() => {
      setSaving(false);
    });
  };

  return (
    <div className="panel-column glass-panel">
      <div className="panel-header">
        <span>Calibração do Laser (Offsets)</span>
      </div>
      <div className="panel-body">
        <form onSubmit={handleSubmit} className="calibration-form">
          <div className="form-group">
            <label>
              Deslocamento X (Offset X) <span>{offsetX} mm</span>
            </label>
            <input 
              type="number" 
              step="0.05"
              className="form-input" 
              value={offsetX}
              onChange={(e) => setOffsetX(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>
              Deslocamento Y (Offset Y) <span>{offsetY} mm</span>
            </label>
            <input 
              type="number" 
              step="0.05"
              className="form-input" 
              value={offsetY}
              onChange={(e) => setOffsetY(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>
              Fator de Escala X <span>{scaleX}x</span>
            </label>
            <input 
              type="number" 
              step="0.01"
              className="form-input" 
              value={scaleX}
              onChange={(e) => setScaleX(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>
              Fator de Escala Y <span>{scaleY}x</span>
            </label>
            <input 
              type="number" 
              step="0.01"
              className="form-input" 
              value={scaleY}
              onChange={(e) => setScaleY(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label>
              Rotação Sincronizada <span>{rotation}°</span>
            </label>
            <input 
              type="number" 
              step="0.1"
              className="form-input" 
              value={rotation}
              onChange={(e) => setRotation(e.target.value)}
            />
          </div>

          <button 
            type="submit" 
            className="btn btn-cyan" 
            style={{ width: '100%', marginTop: '12px' }}
            disabled={saving}
          >
            {saving ? 'Gravando...' : 'Salvar Calibração'}
          </button>
        </form>
      </div>
    </div>
  );
}
