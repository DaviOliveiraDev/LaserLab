import React, { useState, useEffect } from 'react';

export default function TemplateEditor({ template, backendUrl, onSave, onCancel }) {
  const [name, setName] = useState('');
  const [manufacturer, setManufacturer] = useState('');
  const [lensType, setLensType] = useState('Progressive');
  const [offsetX, setOffsetX] = useState(0.0);
  const [offsetY, setOffsetY] = useState(0.0);
  const [rotation, setRotation] = useState(0.0);
  const [fittingCrossDist, setFittingCrossDist] = useState(4.0);
  const [referencePoint, setReferencePoint] = useState('PRP');
  const [technicalNotes, setTechnicalNotes] = useState('');
  const [isActive, setIsActive] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [validationError, setValidationError] = useState('');

  useEffect(() => {
    if (template) {
      setName(template.name || '');
      setManufacturer(template.manufacturer || '');
      setLensType(template.lens_type || 'Progressive');
      setOffsetX(template.offset_x ?? 0.0);
      setOffsetY(template.offset_y ?? 0.0);
      setRotation(template.rotation ?? 0.0);
      setFittingCrossDist(template.fitting_cross_dist ?? 4.0);
      setReferencePoint(template.reference_point || 'PRP');
      setTechnicalNotes(template.technical_notes || '');
      setIsActive(template.is_active ?? 1);
    } else {
      // Clear form for creation
      setName('');
      setManufacturer('');
      setLensType('Progressive');
      setOffsetX(0.0);
      setOffsetY(0.0);
      setRotation(0.0);
      setFittingCrossDist(4.0);
      setReferencePoint('PRP');
      setTechnicalNotes('');
      setIsActive(1);
    }
    setValidationError('');
  }, [template]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setValidationError('O nome do modelo é obrigatório.');
      return;
    }
    if (!manufacturer.trim()) {
      setValidationError('O fabricante é obrigatório.');
      return;
    }

    setIsSubmitting(true);
    setValidationError('');

    const payload = {
      name: name.trim(),
      manufacturer: manufacturer.trim(),
      lens_type: lensType,
      offset_x: parseFloat(offsetX),
      offset_y: parseFloat(offsetY),
      rotation: parseFloat(rotation),
      fitting_cross_dist: parseFloat(fittingCrossDist),
      reference_point: referencePoint,
      technical_notes: technicalNotes.trim(),
      is_active: parseInt(isActive)
    };

    const method = template ? 'PUT' : 'POST';
    const url = template 
      ? `${backendUrl}/api/templates/${template.id}` 
      : `${backendUrl}/api/templates`;

    fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then((res) => {
        if (!res.ok) {
          return res.json().then(data => {
            throw new Error(data.detail || 'Falha ao salvar template.');
          });
        }
        return res.json();
      })
      .then((data) => {
        setIsSubmitting(false);
        onSave(data);
      })
      .catch((err) => {
        console.error(err);
        setValidationError(err.message);
        setIsSubmitting(false);
      });
  };

  return (
    <div className="glass-panel" style={{ maxWidth: '640px', margin: '0 auto', display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="panel-header">
        <span>{template ? '📝 CONFIGURAÇÃO DE TEMPLATE CAD' : '➕ REGISTRO DE NOVO MODELO'}</span>
        <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>PRECISE PARAMETERS DIAL</span>
      </div>

      <form onSubmit={handleSubmit} style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {validationError && (
          <div style={{ background: 'var(--red-fade)', border: '1px solid rgba(239, 68, 68, 0.4)', padding: '10px 14px', borderRadius: '6px', fontSize: '0.75rem', color: '#fca5a5', fontFamily: 'monospace' }}>
            ⚠️ ERRO DE VALIDAÇÃO: {validationError}
          </div>
        )}

        {/* Basic information */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div className="form-group">
            <label>Modelo da Lente (LNAM OMA) <span>*</span></label>
            <input 
              type="text" 
              className="form-input" 
              placeholder="Ex: Zeiss Progressive HD" 
              value={name} 
              onChange={(e) => setName(e.target.value)} 
              required
            />
          </div>

          <div className="form-group">
            <label>Fabricante <span>*</span></label>
            <input 
              type="text" 
              className="form-input" 
              placeholder="Ex: Zeiss, Essilor, Hoya" 
              value={manufacturer} 
              onChange={(e) => setManufacturer(e.target.value)} 
              required
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div className="form-group">
            <label>Tipo da Lente</label>
            <select 
              className="form-input" 
              value={lensType} 
              onChange={(e) => setLensType(e.target.value)}
              style={{ background: '#090d16' }}
            >
              <option value="Progressive">Progressivo (Freeform)</option>
              <option value="Single Vision">Visão Simples</option>
              <option value="Office">Regressivo / Office</option>
              <option value="Bifocal">Bifocal</option>
            </select>
          </div>

          <div className="form-group">
            <label>Ponto de Referência (Alinhamento Origin)</label>
            <select 
              className="form-input" 
              value={referencePoint} 
              onChange={(e) => setReferencePoint(e.target.value)}
              style={{ background: '#090d16' }}
            >
              <option value="PRP">PRP (Prism Reference Point / 0,0)</option>
              <option value="DRP">DRP (Distance Reference Point / +6mm)</option>
              <option value="MRP">MRP (Major Reference Point)</option>
              <option value="GEOMETRIC_CENTER">GC (Geometric Center of Outer Shape)</option>
            </select>
          </div>
        </div>

        <hr style={{ border: 'none', borderBottom: '1px solid var(--border-glass)' }} />

        {/* Offsets inputs */}
        <div style={{ background: 'rgba(9, 13, 22, 0.4)', padding: '16px', borderRadius: '8px', border: '1px solid var(--border-glass)' }}>
          <h4 style={{ fontSize: '0.8rem', color: 'var(--cyan-glow)', marginBottom: '12px', fontFamily: 'monospace', letterSpacing: '0.5px' }}>
            REGULAGEM GEOMÉTRICA DE PRECISÃO (mm / graus)
          </h4>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            
            {/* Offset X slider */}
            <div className="form-group">
              <label>
                Offset X (Deslocamento Horizontal) 
                <span>{offsetX > 0 ? `+${parseFloat(offsetX).toFixed(2)}` : parseFloat(offsetX).toFixed(2)} mm</span>
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input 
                  type="range" 
                  min="-8.0" 
                  max="8.0" 
                  step="0.05" 
                  value={offsetX} 
                  onChange={(e) => setOffsetX(parseFloat(e.target.value))} 
                  style={{ flex: 1, accentColor: 'var(--cyan-glow)' }}
                />
                <input 
                  type="number" 
                  step="0.05"
                  className="form-input" 
                  value={offsetX} 
                  onChange={(e) => setOffsetX(parseFloat(e.target.value) || 0.0)} 
                  style={{ width: '80px', textAlign: 'center', background: '#05070a', padding: '4px' }}
                />
              </div>
            </div>

            {/* Offset Y slider */}
            <div className="form-group">
              <label>
                Offset Y (Deslocamento Vertical) 
                <span>{offsetY > 0 ? `+${parseFloat(offsetY).toFixed(2)}` : parseFloat(offsetY).toFixed(2)} mm</span>
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input 
                  type="range" 
                  min="-8.0" 
                  max="8.0" 
                  step="0.05" 
                  value={offsetY} 
                  onChange={(e) => setOffsetY(parseFloat(e.target.value))} 
                  style={{ flex: 1, accentColor: 'var(--cyan-glow)' }}
                />
                <input 
                  type="number" 
                  step="0.05"
                  className="form-input" 
                  value={offsetY} 
                  onChange={(e) => setOffsetY(parseFloat(e.target.value) || 0.0)} 
                  style={{ width: '80px', textAlign: 'center', background: '#05070a', padding: '4px' }}
                />
              </div>
            </div>

            {/* Rotation slider */}
            <div className="form-group">
              <label>
                Compensação Rotacional (Skew)
                <span>{rotation > 0 ? `+${parseFloat(rotation).toFixed(1)}` : parseFloat(rotation).toFixed(1)}°</span>
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input 
                  type="range" 
                  min="-20.0" 
                  max="20.0" 
                  step="0.1" 
                  value={rotation} 
                  onChange={(e) => setRotation(parseFloat(e.target.value))} 
                  style={{ flex: 1, accentColor: 'var(--orange-glow)' }}
                />
                <input 
                  type="number" 
                  step="0.1"
                  className="form-input" 
                  value={rotation} 
                  onChange={(e) => setRotation(parseFloat(e.target.value) || 0.0)} 
                  style={{ width: '80px', textAlign: 'center', background: '#05070a', padding: '4px' }}
                />
              </div>
            </div>

            {/* Fitting Cross Distance slider */}
            <div className="form-group">
              <label>
                Distância da Cruz de Montagem (Vertical do Ref) 
                <span>+{parseFloat(fittingCrossDist).toFixed(1)} mm</span>
              </label>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input 
                  type="range" 
                  min="0.0" 
                  max="12.0" 
                  step="0.5" 
                  value={fittingCrossDist} 
                  onChange={(e) => setFittingCrossDist(parseFloat(e.target.value))} 
                  style={{ flex: 1, accentColor: '#eab308' }}
                />
                <input 
                  type="number" 
                  step="0.5"
                  className="form-input" 
                  value={fittingCrossDist} 
                  onChange={(e) => setFittingCrossDist(parseFloat(e.target.value) || 0.0)} 
                  style={{ width: '80px', textAlign: 'center', background: '#05070a', padding: '4px' }}
                />
              </div>
            </div>

          </div>
        </div>

        {/* Technical notes */}
        <div className="form-group">
          <label>Observações Técnicas / Notas do Operador</label>
          <textarea 
            className="form-input" 
            placeholder="Registre aqui informações adicionais de processos ou gravações..." 
            value={technicalNotes} 
            onChange={(e) => setTechnicalNotes(e.target.value)} 
            rows="3"
            style={{ resize: 'none', background: '#090d16' }}
          />
        </div>

        {/* Status Toggle */}
        <div className="form-group" style={{ flexDirection: 'row', alignItems: 'center', gap: '12px', padding: '4px 0' }}>
          <input 
            type="checkbox" 
            id="is-active-checkbox"
            checked={isActive === 1} 
            onChange={(e) => setIsActive(e.target.checked ? 1 : 0)}
            style={{ width: '18px', height: '18px', cursor: 'pointer', accentColor: 'var(--green-glow)' }}
          />
          <label htmlFor="is-active-checkbox" style={{ cursor: 'pointer', fontSize: '0.8rem', fontWeight: 'bold' }}>
            Habilitar este template para correspondência automática (LNAM OMA)
          </label>
        </div>

        {/* Form controls */}
        <div style={{ display: 'flex', gap: '12px', marginTop: '12px' }}>
          <button type="button" className="btn btn-glass" onClick={onCancel} disabled={isSubmitting}>
            Voltar
          </button>
          <button type="submit" className="btn btn-cyan" disabled={isSubmitting} style={{ color: '#000' }}>
            {isSubmitting ? 'Salvando...' : 'Salvar Parâmetros'}
          </button>
        </div>
      </form>
    </div>
  );
}
